"""
GLPI Sync Module für Phase 2

Abgleich zwischen Netzwerk-Scan-Ergebnissen und GLPI-Geräten.
Kann neue Geräte in GLPI anlegen, bestehende aktualisieren
und nicht mehr vorhandene Geräte markieren.
"""

import logging
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """GLPI-Sync spezifische Fehler"""
    pass


@dataclass
class GLPIComputer:
    """Repräsentiert einen Computer in GLPI"""
    glpi_id: int
    name: str
    serial: Optional[str] = None
    otherserial: Optional[str] = None  # meistens Asset-Tag
    is_dynamic: bool = False
    entities_id: int = 0  # GLPI Entity ID (Kunde/Organisation)
    locations_id: Optional[int] = None
    users_id: Optional[int] = None
    groups_id: Optional[int] = None
    computertypes_id: Optional[int] = None
    computermodels_id: Optional[int] = None
    autoupdatesystems_id: Optional[int] = None
    operating_systems_id: Optional[int] = None
    operating_system_versions_id: Optional[int] = None
    operating_system_service_packs_id: Optional[int] = None
    operating_system_kernel_versions_id: Optional[int] = None
    operating_system_editions_id: Optional[int] = None
    operating_system_architecture_id: Optional[int] = None
    networks_id: Optional[int] = None
    domain: Optional[str] = None
    last_inventory_update: Optional[datetime] = None
    last_boot: Optional[datetime] = None
    is_deleted: bool = False
    is_template: bool = False
    comment: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert den Computer in ein Dictionary"""
        return {
            "glpi_id": self.glpi_id,
            "name": self.name,
            "serial": self.serial,
            "otherserial": self.otherserial,
            "is_dynamic": self.is_dynamic,
            "entities_id": self.entities_id,
            "locations_id": self.locations_id,
            "users_id": self.users_id,
            "groups_id": self.groups_id,
            "computertypes_id": self.computertypes_id,
            "computermodels_id": self.computermodels_id,
            "autoupdatesystems_id": self.autoupdatesystems_id,
            "operating_systems_id": self.operating_systems_id,
            "operating_system_versions_id": self.operating_system_versions_id,
            "operating_system_service_packs_id": self.operating_system_service_packs_id,
            "operating_system_kernel_versions_id": self.operating_system_kernel_versions_id,
            "operating_system_editions_id": self.operating_system_editions_id,
            "operating_system_architecture_id": self.operating_system_architecture_id,
            "networks_id": self.networks_id,
            "domain": self.domain,
            "last_inventory_update": self.last_inventory_update.isoformat() if self.last_inventory_update else None,
            "last_boot": self.last_boot.isoformat() if self.last_boot else None,
            "is_deleted": self.is_deleted,
            "is_template": self.is_template,
            "comment": self.comment,
            "custom_fields": self.custom_fields
        }


@dataclass
class NetworkDeviceForSync:
    """Gerät aus Netzwerk-Scan für GLPI-Sync"""
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    device_type: Optional[str] = None  # computer, printer, switch, etc.
    serial_number: Optional[str] = None
    domain: Optional[str] = None
    is_domain_controller: bool = False
    open_ports: List[int] = field(default_factory=list)
    scan_timestamp: datetime = field(default_factory=datetime.now)
    customer_id: Optional[int] = None  # Entspricht GLPI entities_id
    location_id: Optional[int] = None  # Entspricht GLPI locations_id
    user_id: Optional[int] = None  # Entspricht GLPI users_id
    glpi_computer_id: Optional[int] = None  # Falls bereits in GLPI
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Gerät in ein Dictionary"""
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "mac_address": self.mac_address,
            "vendor": self.vendor,
            "os_type": self.os_type,
            "os_version": self.os_version,
            "device_type": self.device_type,
            "serial_number": self.serial_number,
            "domain": self.domain,
            "is_domain_controller": self.is_domain_controller,
            "open_ports": self.open_ports,
            "scan_timestamp": self.scan_timestamp.isoformat(),
            "customer_id": self.customer_id,
            "location_id": self.location_id,
            "user_id": self.user_id,
            "glpi_computer_id": self.glpi_computer_id
        }
    
    def to_glpi_computer_dict(self) -> Dict[str, Any]:
        """Konvertiert für GLPI-API Format"""
        # Generiere Name aus Hostname oder IP
        name = self.hostname or f"Device-{self.ip_address.replace('.', '-')}"
        
        return {
            "input": {
                "name": name,
                "serial": self.serial_number or "",
                "otherserial": f"Auto-Discovered-{datetime.now().strftime('%Y%m%d')}",
                "is_dynamic": 1,  # Als dynamic markieren
                "entities_id": self.customer_id or 0,
                "locations_id": self.location_id or 0,
                "computertypes_id": self._map_device_type_to_glpi(),
                "comment": self._generate_comment(),
                "domain": self.domain or "",
                "users_id": self.user_id or 0
            }
        }
    
    def _map_device_type_to_glpi(self) -> Optional[int]:
        """Mappt device_type auf GLPI computertypes_id"""
        type_mapping = {
            "computer": 1,  # Standard Desktop
            "server": 2,    # Server
            "printer": 3,   # Drucker
            "network_device": 4,  # Netzwerkgerät
            "mobile": 5,    # Mobile Device  
            "other": 6      # Sonstiges
        }
        
        if self.device_type in type_mapping:
            return type_mapping[self.device_type]
        
        # OS-basierte Heuristik
        if self.os_type == "windows" and self.device_type != "server":
            return 1  # Desktop
        elif self.os_type == "linux" and "server" in (self.hostname or "").lower():
            return 2  # Server
        elif self.os_type == "printer":
            return 3  # Drucker
        
        return 6  # Sonstiges
    
    def _generate_comment(self) -> str:
        """Generiert Kommentar für GLPI-Eintrag"""
        comment_lines = []
        
        if self.ip_address:
            comment_lines.append(f"IP: {self.ip_address}")
        if self.mac_address:
            comment_lines.append(f"MAC: {self.mac_address}")
        if self.vendor:
            comment_lines.append(f"Hersteller: {self.vendor}")
        if self.os_type:
            comment_lines.append(f"OS: {self.os_type}")
        if self.os_version:
            comment_lines.append(f"OS Version: {self.os_version}")
        if self.open_ports:
            comment_lines.append(f"Offene Ports: {', '.join(map(str, self.open_ports))}")
        if self.domain:
            comment_lines.append(f"Domain: {self.domain}")
        if self.is_domain_controller:
            comment_lines.append("Domain Controller: Ja")
        
        comment_lines.append(f"Entdeckt am: {self.scan_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        comment_lines.append(f"Automatisch erfasst durch Device Management System")
        
        return "\n".join(comment_lines)


@dataclass
class SyncResult:
    """Ergebnis eines GLPI-Sync-Vorgangs"""
    sync_id: str
    scan_result_id: Optional[str] = None
    customer_id: Optional[int] = None
    sync_start_time: datetime = field(default_factory=datetime.now)
    sync_end_time: Optional[datetime] = None
    new_devices: List[GLPIComputer] = field(default_factory=list)
    updated_devices: List[GLPIComputer] = field(default_factory=list)
    removed_devices: List[GLPIComputer] = field(default_factory=list)
    failed_devices: List[Dict[str, Any]] = field(default_factory=list)
    total_processed: int = 0
    sync_duration: Optional[float] = None
    sync_status: str = "pending"  # pending, running, completed, failed
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Sync-Ergebnis in ein Dictionary"""
        return {
            "sync_id": self.sync_id,
            "scan_result_id": self.scan_result_id,
            "customer_id": self.customer_id,
            "sync_start_time": self.sync_start_time.isoformat(),
            "sync_end_time": self.scan_end_time.isoformat() if self.scan_end_time else None,
            "new_devices": [d.to_dict() for d in self.new_devices],
            "updated_devices": [d.to_dict() for d in self.updated_devices],
            "removed_devices": [d.to_dict() for d in self.removed_devices],
            "failed_devices": self.failed_devices,
            "total_processed": self.total_processed,
            "sync_duration": self.sync_duration,
            "sync_status": self.sync_status,
            "error_message": self.error_message
        }


class GLPIAPIClient:
    """
    Client für GLPI-API
    
    Kommuniziert mit GLPI REST API (GLPI 10.x/11.x)
    """
    
    def __init__(self, base_url: str, app_token: str, user_token: str):
        """
        Initialisiert den GLPI API Client
        
        Args:
            base_url: Basis-URL der GLPI-API (z.B. "https://glpi.example.com/apirest.php")
            app_token: Application Token von GLPI
            user_token: User Token von GLPI
        """
        self.base_url = base_url.rstrip('/')
        self.app_token = app_token
        self.user_token = user_token
        self.session = None
        
        logger.info(f"GLPI-API Client initialisiert für {base_url}")
    
    async def initialize_session(self):
        """Initialisiert API-Session"""
        if self.session:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                # Init-Session anfragen
                init_url = f"{self.base_url}/initSession"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"user_token {self.user_token}",
                    "App-Token": self.app_token
                }
                
                async with session.get(init_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.session_token = data.get("session_token")
                        logger.info("GLPI-Session initialisiert")
                    else:
                        raise SyncError(f"Session-Initialisierung fehlgeschlagen: {response.status}")
                
                self.session = session
                
        except Exception as e:
            logger.error(f"Fehler bei GLPI-Session-Initialisierung: {e}")
            raise
    
    async def close_session(self):
        """Schließt API-Session"""
        if not self.session or not self.session_token:
            return
        
        try:
            kill_url = f"{self.base_url}/killSession"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            async with self.session.post(kill_url, headers=headers) as response:
                if response.status == 200:
                    logger.info("GLPI-Session geschlossen")
                else:
                    logger.warning(f"Session-Schließen fehlgeschlagen: {response.status}")
            
            await self.session.close()
            self.session = None
            self.session_token = None
            
        except Exception as e:
            logger.error(f"Fehler beim Schließen der GLPI-Session: {e}")
    
    async def get_computers_by_entity(self, entity_id: int, limit: int = 1000) -> List[GLPIComputer]:
        """
        Holt Computer einer bestimmten Entity (Kunde)
        
        Args:
            entity_id: GLPI Entity ID
            limit: Maximale Anzahl
            
        Returns:
            Liste von GLPIComputer
        """
        await self.initialize_session()
        
        try:
            search_url = f"{self.base_url}/Computer"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            params = {
                "range": f"0-{limit}",
                "order": "name",
                "sort": "ASC",
                "criteria[0][field]": "entities_id",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": str(entity_id)
            }
            
            async with self.session.get(search_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    computers = []
                    for item in data:
                        computer = GLPIComputer(
                            glpi_id=item.get("id", 0),
                            name=item.get("name", ""),
                            serial=item.get("serial", None),
                            otherserial=item.get("otherserial", None),
                            is_dynamic=bool(item.get("is_dynamic", 0)),
                            entities_id=item.get("entities_id", 0),
                            locations_id=item.get("locations_id", None),
                            users_id=item.get("users_id", None),
                            domain=item.get("domain", None),
                            comment=item.get("comment", None),
                            is_deleted=bool(item.get("is_deleted", 0)),
                            is_template=bool(item.get("is_template", 0))
                        )
                        computers.append(computer)
                    
                    logger.debug(f"GLPI-Computer abgerufen: {len(computers)} für Entity {entity_id}")
                    return computers
                else:
                    logger.error(f"GLPI-Abfrage fehlgeschlagen: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Fehler beim Abrufen von GLPI-Computern: {e}")
            return []
    
    async def find_computer_by_serial(self, serial: str) -> Optional[GLPIComputer]:
        """
        Sucht Computer nach Seriennummer
        
        Args:
            serial: Seriennummer
            
        Returns:
            GLPIComputer oder None
        """
        await self.initialize_session()
        
        try:
            search_url = f"{self.base_url}/Computer"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            params = {
                "range": "0-10",
                "criteria[0][field]": "serial",
                "criteria[0][searchtype]": "contains",
                "criteria[0][value]": serial
            }
            
            async with self.session.get(search_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and len(data) > 0:
                        item = data[0]
                        computer = GLPIComputer(
                            glpi_id=item.get("id", 0),
                            name=item.get("name", ""),
                            serial=item.get("serial", None),
                            otherserial=item.get("otherserial", None),
                            is_dynamic=bool(item.get("is_dynamic", 0)),
                            entities_id=item.get("entities_id", 0),
                            locations_id=item.get("locations_id", None),
                            comment=item.get("comment", None)
                        )
                        return computer
                    
                return None
                
        except Exception as e:
            logger.error(f"Fehler bei Suche nach Seriennummer {serial}: {e}")
            return None
    
    async def find_computer_by_mac(self, mac_address: str) -> Optional[GLPIComputer]:
        """
        Sucht Computer nach MAC-Adresse
        
        Anmerkung: GLPI muss über NetworkPort oder ähnliches MAC-Adressen speichern.
        Dies ist eine vereinfachte Implementierung.
        
        Args:
            mac_address: MAC-Adresse
            
        Returns:
            GLPIComputer oder None
        """
        await self.initialize_session()
        
        try:
            # Für Netzwerkgeräte mit MAC: NetworkEquipment API verwenden
            # Diese Implementierung fokussiert sich auf Computer
            
            # Alternative: Suche über Kommentar-Feld
            search_url = f"{self.base_url}/Computer"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            params = {
                "range": "0-10",
                "criteria[0][field]": "comment",
                "criteria[0][searchtype]": "contains", 
                "criteria[0][value]": mac_address
            }
            
            async with self.session.get(search_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and len(data) > 0:
                        item = data[0]
                        computer = GLPIComputer(
                            glpi_id=item.get("id", 0),
                            name=item.get("name", ""),
                            serial=item.get("serial", None),
                            otherserial=item.get("otherserial", None),
                            entities_id=item.get("entities_id", 0),
                            comment=item.get("comment", None)
                        )
                        return computer
                    
                return None
                
        except Exception as e:
            logger.error(f"Fehler bei Suche nach MAC {mac_address}: {e}")
            return None
    
    async def create_computer(self, computer_data: Dict[str, Any]) -> Optional[GLPIComputer]:
        """
        Erstellt neuen Computer in GLPI
        
        Args:
            computer_data: Computer-Daten im GLPI-API Format
            
        Returns:
            Neuer GLPIComputer oder None bei Fehler
        """
        await self.initialize_session()
        
        try:
            create_url = f"{self.base_url}/Computer"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            async with self.session.post(create_url, headers=headers, json=computer_data) as response:
                if response.status == 201:
                    data = await response.json()
                    
                    computer = GLPIComputer(
                        glpi_id=data.get("id", 0),
                        name=data.get("name", ""),
                        serial=data.get("serial", None),
                        otherserial=data.get("otherserial", None),
                        is_dynamic=bool(data.get("is_dynamic", 0)),
                        entities_id=data.get("entities_id", 0),
                        locations_id=data.get("locations_id", None),
                        users_id=data.get("users_id", None),
                        domain=data.get("domain", None),
                        comment=data.get("comment", None)
                    )
                    
                    logger.info(f"Computer in GLPI erstellt: {computer.name} (ID: {computer.glpi_id})")
                    return computer
                else:
                    error_text = await response.text()
                    logger.error(f"Computer-Erstellung fehlgeschlagen: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Fehler beim Erstellen von Computer: {e}")
            return None
    
    async def update_computer(self, computer_id: int, update_data: Dict[str, Any]) -> bool:
        """
        Aktualisiert bestehenden Computer
        
        Args:
            computer_id: GLPI Computer ID
            update_data: Zu aktualisierende Daten
            
        Returns:
            True bei Erfolg
        """
        await self.initialize_session()
        
        try:
            update_url = f"{self.base_url}/Computer/{computer_id}"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            async with self.session.put(update_url, headers=headers, json=update_data) as response:
                if response.status == 200:
                    logger.info(f"Computer {computer_id} aktualisiert")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Computer-Aktualisierung fehlgeschlagen: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren von Computer {computer_id}: {e}")
            return False
    
    async def delete_computer(self, computer_id: int, purge: bool = False) -> bool:
        """
        Löscht Computer aus GLPI
        
        Args:
            computer_id: GLPI Computer ID
            purge: Endgültig löschen (True) oder in Papierkorb (False)
            
        Returns:
            True bei Erfolg
        """
        await self.initialize_session()
        
        try:
            delete_url = f"{self.base_url}/Computer/{computer_id}"
            if purge:
                delete_url += "?force=1"
            
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token
            }
            
            async with self.session.delete(delete_url, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"Computer {computer_id} {'gepurged' if purge else 'gelöscht'}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Computer-Löschung fehlgeschlagen: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Fehler beim Löschen von Computer {computer_id}: {e}")
            return False


class GLPI_Sync:
    """
    GLPI-Synchronisation für Netzwerk-Scans
    
    Fähigkeiten:
    - Abgleich von Scan-Ergebnissen mit GLPI
    - Automatisches Anlegen neuer Geräte
    - Aktualisierung bestehender Geräte
    - Markieren nicht mehr gefundener Geräte
    - Konflikt-Lösung bei mehrfachen Funden
    - IP-Adressen, MAC-Adressen und Seriennummer-Zuordnung
    """
    
    def __init__(self, glpi_client: GLPIAPIClient, config: Dict[str, Any]):
        """
        Initialisiert den GLPI-Sync
        
        Args:
            glpi_client: GLPI-API Client
            config: Konfigurationsdictionary mit:
                - auto_sync: Automatische Sync nach Scans (default: True)
                - update_existing: Bestehende Geräte aktualisieren (default: True)
                - mark_missing: Nicht mehr gefundene Geräte markieren (default: False)
                - create_tickets_for_missing: Tickets für fehlende Geräte erstellen (default: False)
                - sync_timeout_seconds: Timeout für Sync-Operationen
                - max_parallel_operations: Maximale parallele Operationen
        """
        self.glpi_client = glpi_client
        self.config = config
        
        self.auto_sync = config.get("auto_sync", True)
        self.update_existing = config.get("update_existing", True)
        self.mark_missing = config.get("mark_missing", False)
        self.create_tickets_for_missing = config.get("create_tickets_for_missing", False)
        self.sync_timeout = config.get("sync_timeout_seconds", 60)
        self.max_parallel = config.get("max_parallel_operations", 5)
        
        # Cache für Entities und Geräte
        self.entity_cache: Dict[int, List[GLPIComputer]] = {}
        self.cache_timestamp: Optional[datetime] = None
        self.cache_ttl_seconds = 300  # 5 Minuten Cache
        
        logger.info("GLPI-Sync initialisiert")
    
    def generate_sync_id(self) -> str:
        """Generiert eindeutige Sync-ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = hex(hash(str(time.time())))[-6:]
        return f"sync_{timestamp}_{random_suffix}"
    
    async def sync_network_scan(self, scan_devices: List[NetworkDeviceForSync]) -> SyncResult:
        """
        Synchronisiert Netzwerk-Scan-Ergebnisse mit GLPI
        
        Args:
            scan_devices: Liste von erkannten Geräten
            
        Returns:
            SyncResult mit Ergebnissen
        """
        sync_id = self.generate_sync_id()
        sync_result = SyncResult(sync_id=sync_id)
        sync_result.sync_status = "running"
        
        try:
            logger.info(f"GLPI-Sync startet: {sync_id} mit {len(scan_devices)} Geräten")
            
            # Gruppiere Geräte nach Customer/Entity
            devices_by_customer: Dict[Optional[int], List[NetworkDeviceForSync]] = {}
            for device in scan_devices:
                customer_id = device.customer_id
                if customer_id not in devices_by_customer:
                    devices_by_customer[customer_id] = []
                devices_by_customer[customer_id].append(device)
            
            total_processed = 0
            all_new_devices = []
            all_updated_devices = []
            all_failed_devices = []
            
            # Verarbeite jede Entity separat
            for customer_id, devices in devices_by_customer.items():
                if not customer_id:
                    logger.warning(f"Geräte ohne Customer-ID gefunden, überspringe")
                    continue
                
                logger.info(f"Sync für Entity {customer_id}: {len(devices)} Geräte")
                
                # Hole bestehende GLPI-Geräte für diese Entity
                existing_glpi_computers = await self._get_cached_glpi_computers(customer_id)
                
                # Finde Zuordnungen und Differenzen
                matched, unmatched = self._match_devices(devices, existing_glpi_computers)
                
                # Neue Geräte erstellen
                new_devices = []
                for device in unmatched:
                    if device.glpi_computer_id:  # Schon gematcht
                        continue
                    
                    # Prüfe ob dieses Gerät bereits existiert (über MAC oder Serial)
                    existing_by_mac = None
                    if device.mac_address:
                        existing_by_mac = await self._find_existing_by_mac(device.mac_address)
                    
                    existing_by_serial = None
                    if device.serial_number:
                        existing_by_serial = await self._find_existing_by_serial(device.serial_number)
                    
                    if existing_by_mac or existing_by_serial:
                        # Bestehendes Gerät aktualisieren
                        glpi_computer = existing_by_mac or existing_by_serial
                        
                        if self.update_existing:
                            update_success = await self._update_existing_device(glpi_computer.glpi_id, device)
                            if update_success:
                                glpi_computer.domain = device.domain
                                glpi_computer.comment = device._generate_comment()
                                all_updated_devices.append(glpi_computer)
                                logger.info(f"Bestehendes Gerät aktualisiert: {device.hostname or device.ip_address}")
                            else:
                                all_failed_devices.append({
                                    "device": device.to_dict(), 
                                    "error": "Aktualisierung fehlgeschlagen"
                                })
                    else:
                        # Neues Gerät erstellen
                        glpi_computer = await self._create_new_device(device)
                        if glpi_computer:
                            all_new_devices.append(glpi_computer)
                            logger.info(f"Neues Gerät erstellt: {device.hostname or device.ip_address}")
                        else:
                            all_failed_devices.append({
                                "device": device.to_dict(),
                                "error": "Erstellung fehlgeschlagen"
                            })
                
                total_processed += len(devices)
            
            # Aktualisiere Sync-Ergebnis
            sync_result.new_devices = all_new_devices
            sync_result.updated_devices = all_updated_devices
            sync_result.failed_devices = all_failed_devices
            sync_result.total_processed = total_processed
            sync_result.sync_end_time = datetime.now()
            sync_result.sync_duration = (sync_result.sync_end_time - sync_result.sync_start_time).total_seconds()
            sync_result.sync_status = "completed"
            
            logger.info(f"GLPI-Sync abgeschlossen: {len(all_new_devices)} neue, {len(all_updated_devices)} aktualisierte Geräte")
            
            return sync_result
            
        except Exception as e:
            logger.error(f"GLPI-Sync fehlgeschlagen: {e}")
            sync_result.sync_end_time = datetime.now()
            sync_result.sync_status = "failed"
            sync_result.error_message = str(e)
            return sync_result
    
    def _match_devices(self, 
                       scan_devices: List[NetworkDeviceForSync], 
                       glpi_computers: List[GLPIComputer]) -> Tuple[List[NetworkDeviceForSync], List[NetworkDeviceForSync]]:
        """
        Matcht Scan-Geräte mit GLPI-Computern
        
        Returns:
            Tuple (matched_devices, unmatched_devices)
        """
        matched = []
        unmatched = []
        
        # Erstelle Mapping-Tabelle für schnellen Zugriff
        mac_to_computer = {}
        serial_to_computer = {}
        ip_to_computer = {}
        name_to_computer = {}
        
        for computer in glpi_computers:
            # Kommentar nach MAC durchsuchen (vereinfachter Ansatz)
            if computer.comment and "MAC:" in computer.comment:
                import re
                mac_matches = re.findall(r'MAC:\s*([0-9A-Fa-f:]+)', computer.comment)
                for mac in mac_matches:
                    mac_to_computer[mac.upper()] = computer
            
            # Seriennummer-Mapping
            if computer.serial:
                serial_to_computer[computer.serial] = computer
        
        # Versuche Matching für jedes Scan-Gerät
        for device in scan_devices:
            matched_computer = None
            
            # 1. Versuche MAC-Adresse
            if device.mac_address and device.mac_address in mac_to_computer:
                matched_computer = mac_to_computer[device.mac_address]
            
            # 2. Versuche Seriennummer
            elif device.serial_number and device.serial_number in serial_to_computer:
                matched_computer = serial_to_computer[device.serial_number]
            
            # 3. Versuche Hostname/IP-Kombination (unsicher)
            elif device.hostname:
                for computer in glpi_computers:
                    if computer.name == device.hostname:
                        matched_computer = computer
                        break
            
            if matched_computer:
                device.glpi_computer_id = matched_computer.glpi_id
                matched.append(device)
            else:
                unmatched.append(device)
        
        return matched, unmatched
    
    async def _get_cached_glpi_computers(self, entity_id: int) -> List[GLPIComputer]:
        """Holt GLPI-Computer mit Cache"""
        # Prüfe Cache
        if (entity_id in self.entity_cache and 
            self.cache_timestamp and 
            (datetime.now() - self.cache_timestamp).total_seconds() < self.cache_ttl_seconds):
            return self.entity_cache[entity_id]
        
        # Hole von GLPI
        computers = await self.glpi_client.get_computers_by_entity(entity_id)
        
        # Aktualisiere Cache
        self.entity_cache[entity_id] = computers
        self.cache_timestamp = datetime.now()
        
        return computers
    
    async def _find_existing_by_mac(self, mac_address: str) -> Optional[GLPIComputer]:
        """Findet bestehenden Computer über MAC-Adresse"""
        return await self.glpi_client.find_computer_by_mac(mac_address)
    
    async def _find_existing_by_serial(self, serial: str) -> Optional[GLPIComputer]:
        """Findet bestehenden Computer über Seriennummer"""
        return await self.glpi_client.find_computer_by_serial(serial)
    
    async def _create_new_device(self, device: NetworkDeviceForSync) -> Optional[GLPIComputer]:
        """Erstellt neues Gerät in GLPI"""
        glpi_data = device.to_glpi_computer_dict()
        return await self.glpi_client.create_computer(glpi_data)
    
    async def _update_existing_device(self, glpi_id: int, device: NetworkDeviceForSync) -> bool:
        """Aktualisiert bestehendes Gerät in GLPI"""
        update_data = {
            "input": {
                "comment": device._generate_comment(),
                "domain": device.domain or "",
                "users_id": device.user_id or 0
            }
        }
        
        return await self.glpi_client.update_computer(glpi_id, update_data)
    
    def clear_cache(self):
        """Leert den GLPI-Cache"""
        self.entity_cache.clear()
        self.cache_timestamp = None
        logger.info("GLPI-Cache geleert")
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            "cache_size": sum(len(computers) for computers in self.entity_cache.values()),
            "cache_entities": list(self.entity_cache.keys()),
            "cache_age_seconds": (datetime.now() - self.cache_timestamp).total_seconds() if self.cache_timestamp else None,
            "auto_sync": self.auto_sync,
            "update_existing": self.update_existing,
            "mark_missing": self.mark_missing
        }

    def sync_devices(self, entity_id: int, devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synchronisiert Geräte mit GLPI (API-kompatibel mit Tests)
        
        Args:
            entity_id: GLPI Entity ID
            devices: Liste von Geräten
            
        Returns:
            Dictionary mit Sync-Ergebnissen
        """
        try:
            # Konvertiere Geräte zu NetworkDeviceForSync
            sync_devices = []
            for device in devices:
                sync_device = NetworkDeviceForSync(
                    ip_address=device.get("ip_address", ""),
                    hostname=device.get("hostname"),
                    mac_address=device.get("mac_address"),
                    vendor=device.get("vendor"),
                    os_type=device.get("os_type"),
                    os_version=device.get("os_version"),
                    device_type=device.get("device_type", "computer"),
                    serial_number=device.get("serial_number"),
                    domain=device.get("domain"),
                    customer_id=entity_id,
                    user_id=device.get("user_id"),
                    scan_timestamp=device.get("scan_timestamp", datetime.now())
                )
                sync_devices.append(sync_device)
            
            # Führe synchronen Sync durch
            import asyncio
            sync_result = asyncio.run(self.sync_network_scan(sync_devices))
            
            return {
                "sync_id": sync_result.sync_id,
                "entity_id": entity_id,
                "new_devices": sync_result.new_devices,
                "updated_devices": sync_result.updated_devices,
                "failed_devices": sync_result.failed_devices,
                "total_processed": sync_result.total_processed,
                "sync_status": sync_result.sync_status
            }
            
        except Exception as e:
            logger.error(f"Sync fehlgeschlagen für Entity {entity_id}: {e}")
            return {
                "sync_id": self.generate_sync_id(),
                "entity_id": entity_id,
                "new_devices": [],
                "updated_devices": [],
                "failed_devices": len(devices) if devices else 0,
                "total_processed": len(devices) if devices else 0,
                "sync_status": "failed",
                "error_message": str(e)
            }
