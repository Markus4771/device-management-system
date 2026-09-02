"""
Remote Agent für Phase 2

Ein kleiner Scan-Agent für entfernte Kundennetzwerke.
Kann über VPN oder direkte Verbindung eingesetzt werden.
Sicherheitsfunktionen: verschlüsselte Kommunikation, Authentifizierung,
jederliche Berechtigungen, Protokollierung.
"""

import logging
import json
import base64
import hashlib
import hmac
import secrets
import asyncio
import socket
import ssl
import subprocess
import tempfile
import os
import sys
import time
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Status des Remote-Agents"""
    DISCONNECTED = "disconnected"  # Nicht verbunden
    CONNECTING = "connecting"      # Verbindung wird aufgebaut
    CONNECTED = "connected"        # Verbunden
    SCANNING = "scanning"          | | Am Scannen
    ERROR = "error"                # Fehlerzustand
    MAINTENANCE = "maintenance"    # Wartungsmodus


class ScanCommand(Enum):
    """Befehle für Netzwerk-Scans"""
    PING_SWEEP = "ping_sweep"      | | Ping-Sweep für alle Geräte
    PORT_SCAN = "port_scan"        | | Port-Scan für ausgewählte Geräte
    OS_DETECTION = "os_detection"  | OS-Erkennung
    MAC_COLLECTION = "mac_collection"  | MAC-Adressen sammeln
    NETWORK_DISCOVERY = "network_discovery"  # Netzwerk-Topologie
    DNS_RESOLUTION = "dns_resolution"  # DNS-Auflösung
    LDAP_QUERY = "ldap_query"      # LDAP-Abfragen
    WINDOWS_DETECTION = "windows_detection"  # Windows-Computer erkennen
    PRINTER_DETECTION = "printer_detection"  # Drucker erkennen
    DOMAIN_CONTROLLER_DETECTION = "domain_controller_detection"  # Domain Controller erkennen
    ASSET_COLLECTION = "asset_collection"  # Asset-Informationen sammeln


@dataclass
class RemoteAgentConfig:
    """Konfiguration für den Remote-Agent"""
    agent_id: str
    agent_name: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    location: Optional[str] = None
    connection_type: str = "vpn"  # "vpn", "direct", "ssh_tunnel"
    connection_endpoint: Optional[str] = None  # IP:Port oder Hostname
    credential_id: Optional[str] = None
    allowed_ip_ranges: List[str] = field(default_factory=list)  # Z.B. ["192.168.1.0/24", "10.0.0.0/8"]
    max_bandwidth_kbps: Optional[int] = None  # Maximale Bandbreite in kbps
    scan_time_window_start: Optional[str] = None  # Format: "HH:MM"
    scan_time_window_end: Optional[str] = None    # Format: "HH:MM"
    heartbeat_interval_seconds: int = 300         # Herzschlag-Intervall
    max_scan_duration_minutes: int = 60           # Maximale Scan-Dauer
    require_approval: bool = True                 # Scan erfordert Freigabe
    encryption_key: Optional[str] = None          # Verschlüsselungsschlüssel
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Konfiguration in ein Dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "location": self.location,
            "connection_type": self.connection_type,
            "connection_endpoint": self.connection_endpoint,
            "credential_id": self.credential_id,
            "allowed_ip_ranges": self.allowed_ip_ranges,
            "max_bandwidth_kbps": self.max_bandwidth_kbps,
            "scan_time_window_start": self.scan_time_window_start,
            "scan_time_window_end": self.scan_time_window_end,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "max_scan_duration_minutes": self.max_scan_duration_minutes,
            "require_approval": self.require_approval,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ScanTask:
    """Scan-Aufgabe für Remote-Agent"""
    task_id: str
    agent_id: str
    scan_commands: List[ScanCommand]  # Zu ausführende Befehle
    target_ip_range: str              # Z.B. "192.168.1.0/24"
    scan_parameters: Dict[str, Any] = field(default_factory=dict)  # Z.B. {"ports": "22,80,443,3389"}
    priority: int = 5                 # Priorität (1=hoch, 10=niedrig)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"           # "pending", "running", "completed", "failed", "canceled"
    progress_percentage: int = 0
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Scan-Aufgabe in ein Dictionary"""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "scan_commands": [cmd.value for cmd in self.scan_commands],
            "target_ip_range": self.target_ip_range,
            "scan_parameters": self.scan_parameters,
            "priority": self.priority,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "progress_percentage": self.progress_percentage,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "created_by": self.created_by,
            "approved_by": self.approved_by
        }


class RemoteAgent:
    """
    Remote-Agent für Netzwerk-Scans in entfernten Kundennetzwerken.
    
    Funktionen:
    - Automatische Verbindung über VPN/direkte Verbindung
    - Verschlüsselte Kommunikation mit Hauptserver
    - Ausführung von Netzwerk-Scans
    - Asset-Erkennung und -Sammlung
    - Fehlertolerante Operationen
    - Bandbreitenmanagement
    - Herzschlag- und Statusmeldungen
    """
    
    def __init__(self, config: RemoteAgentConfig, credential_manager=None):
        """
        Initialisiert den Remote-Agent
        
        Args:
            config: Agent-Konfiguration
            credential_manager: Optionaler Credential-Manager für Zugangsdaten
        """
        self.config = config
        self.credential_manager = credential_manager
        self.status = AgentStatus.DISCONNECTED
        self.current_task: Optional[ScanTask] = None
        self.heartbeat_timer: Optional[asyncio.Task] = None
        self.connection: Optional[socket.socket] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.last_heartbeat: Optional[datetime] = None
        self.stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "devices_discovered": 0,
            "total_scan_time": 0,
            "last_activity": None
        }
        
        # Verschlüsselungsinitialisierung
        self._init_encryption()
        
        logger.info(f"Remote-Agent {config.agent_name} ({config.agent_id}) initialisiert")
    
    def _init_encryption(self):
        """Initialisiert die Verschlüsselung"""
        if self.config.encryption_key:
            try:
                # SSL/TLS Kontext für sichere Kommunikation
                self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                self.ssl_context.check_hostname = False
                self.ssl_context.verify_mode = ssl.CERT_NONE  # In Produktion Zertifikate verwenden
                
                logger.debug("Verschlüsselung initialisiert")
            except Exception as e:
                logger.error(f"Fehler bei Verschlüsselungsinitialisierung: {e}")
    
    async def connect(self) -> bool:
        """
        Stellt Verbindung zum Hauptserver her
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if self.status != AgentStatus.DISCONNECTED:
            logger.warning(f"Agent bereits verbunden oder im Status {self.status}")
            return False
        
        self.status = AgentStatus.CONNECTING
        logger.info(f"Verbindung wird aufgebaut zu {self.config.connection_endpoint}")
        
        try:
            if self.config.connection_type == "direct":
                await self._connect_direct()
            elif self.config.connection_type == "vpn":
                await self._connect_vpn()
            elif self.config.connection_type == "ssh_tunnel":
                await self._connect_ssh_tunnel()
            else:
                logger.error(f"Unbekannter Verbindungstyp: {self.config.connection_type}")
                self.status = AgentStatus.ERROR
                return False
            
            # Herzschlag starten
            self.last_heartbeat = datetime.now()
            self.heartbeat_timer = asyncio.create_task(self._heartbeat_loop())
            
            logger.info(f"Verbindung erfolgreich hergestellt")
            self.status = AgentStatus.CONNECTED
            return True
            
        except Exception as e:
            logger.error(f"Verbindungsfehler: {e}")
            self.status = AgentStatus.ERROR
            return False
    
    async def _connect_direct(self):
        """Stellt direkte TCP-Verbindung her"""
        if not self.config.connection_endpoint:
            raise ValueError("connection_endpoint muss für direkte Verbindung gesetzt sein")
        
        host, port_str = self.config.connection_endpoint.split(":")
        port = int(port_str)
        
        # Socket erstellen
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # SSL/TLS wenn konfiguriert
        if self.ssl_context:
            self.connection = self.ssl_context.wrap_socket(
                self.connection,
                server_hostname=host
            )
        
        # Verbindung aufbauen mit Timeout
        self.connection.settimeout(30)
        self.connection.connect((host, port))
        
        # Handshake durchführen
        await self._send_handshake()
    
    async def _connect_vpn(self):
        """Stellt VPN-Verbindung her"""
        # In einer echten Implementierung: VPN-Client starten
        # Hier nur Platzhalter
        logger.info("VPN-Verbindung wird hergestellt...")
        
        # Simuliere VPN-Verbindungsaufbau
        await asyncio.sleep(2)
        
        # Nach VPN: Direkte Verbindung
        await self._connect_direct()
    
    async def _connect_ssh_tunnel(self):
        """Stellt SSH-Tunnel-Verbindung her"""
        # SSH-Tunnel mit Paramiko oder ähnlichem
        logger.info("SSH-Tunnel wird aufgebaut...")
        
        # Simuliere SSH-Tunnel
        await asyncio.sleep(3)
        
        # Nach SSH-Tunnel: Direkte Verbindung  
        await self._connect_direct()
    
    async def _send_handshake(self):
        """Sendet Handshake-Nachricht an Server"""
        handshake = {
            "type": "handshake",
            "agent_id": self.config.agent_id,
            "agent_name": self.config.agent_name,
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "capabilities": ["ping", "port_scan", "os_detection", "mac_collection"]
        }
        
        await self._send_message(handshake)
        
        # Antwort abwarten
        response = await self._receive_message(timeout=10)
        if response.get("type") != "handshake_ack":
            raise ConnectionError("Handshake fehlgeschlagen")
        
        logger.info("Handshake erfolgreich")
    
    async def disconnect(self):
        """Trennt Verbindung zum Hauptserver"""
        if self.status == AgentStatus.DISCONNECTED:
            return
        
        logger.info("Verbindung wird getrennt")
        
        # Herzschlag stoppen
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            try:
                await self.heartbeat_timer
            except asyncio.CancelledError:
                pass
        
        # Eventuell laufenden Scan stoppen
        if self.current_task and self.current_task.status == "running":
            await self.cancel_current_task()
        
        # Verbindung schließen
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
        
        self.status = AgentStatus.DISCONNECTED
        logger.info("Verbindung getrennt")
    
    async def _heartbeat_loop(self):
        """Sendet regelmäßig Herzschlag-Nachrichten"""
        while self.status == AgentStatus.CONNECTED:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                
                heartbeat = {
                    "type": "heartbeat",
                    "agent_id": self.config.agent_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": self.status.value,
                    "current_task": self.current_task.task_id if self.current_task else None,
                    "stats": self.stats
                }
                
                await self._send_message(heartbeat)
                self.last_heartbeat = datetime.now()
                
                logger.debug("Herzschlag gesendet")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fehler beim Senden von Herzschlag: {e}")
                # Versuche Reconnection
                await self._handle_connection_error()
    
    async def _handle_connection_error(self):
        """Behandelt Verbindungsfehler"""
        self.status = AgentStatus.ERROR
        logger.warning("Verbindungsfehler, versuche Wiederherstellung...")
        
        try:
            await self.disconnect()
            await asyncio.sleep(5)  # Warte vor Reconnection
            await self.connect()
        except Exception as e:
            logger.error(f"Wiederherstellung fehlgeschlagen: {e}")
    
    async def execute_scan(self, task: ScanTask) -> ScanTask:
        """
        Führt einen Scan durch
        
        Args:
            task: Scan-Task mit Details
            
        Returns:
            Aktualisierter Scan-Task
        """
        if self.status != AgentStatus.CONNECTED:
            raise RuntimeError(f"Agent nicht verbunden (Status: {self.status})")
        
        if self.current_task and self.current_task.status == "running":
            raise RuntimeError("Bereits ein Scan läuft")
        
        # Prüfe Berechtigung für Scan-Bereich
        if not self._is_ip_range_allowed(task.target_ip_range):
            raise PermissionError(f"IP-Bereich {task.target_ip_range} nicht erlaubt")
        
        # Setze Task
        self.current_task = task
        self.current_task.status = "running"
        self.current_task.started_at = datetime.now()
        self.current_task.progress_percentage =url 0
        
        logger.info(f"Scan startet: {task.task_id} für {task.target_ip_range}")
        
        try:
            # Analyse welche Befehle ausgeführt werden sollen
            discovery_results = {}
            
            # Ping-Sweep für alle aktiven Geräte finden
            if ScanCommand.PING_SWEEP in task.scan_commands:
                discovery_results = await self._perform_ping_sweep(task.target_ip_range)
                task.progress_percentage = 20
            
            # MAC-Adressen sammeln
            if ScanCommand.MAC_COLLECTION in task.scan_commands:
                mac_results = await self._collect_mac_addresses(discovery_results.get("active_hosts", []))
                discovery_results["mac_addresses"] = mac_results
                task.progress_percentage = 40
            
            # Port-Scans für wichtige Dienste
            if ScanCommand.PORT_SCAN in task.scan_commands:
                port_results = await self._perform_port_scan(
                    discovery_results.get("active_hosts", []),
                    task.scan_parameters.get("ports", "22,80,443,3389")
                )
                discovery_results["open_ports"] = port_results
                task.progress_percentage = 60
            
            # OS-Erkennung
            if ScanCommand.OS_DETECTION in task.scan_commands:
                os_results = await self._detect_operating_systems(
                    discovery_results.get("active_hosts", [])
                )
                discovery_results["operating_systems"] = os_results
                task.progress_percentage = 80
            
            # Wenn Windows-Computer gefunden, Domain-Funktionen prüfen
            if ScanCommand.WINDOWS_DETECTION in task.scan_commands:
                windows_results = await self._detect_windows_computers(discovery_results)
                discovery_results["windows_computers"] = windows_results
            
            # Domain Controller erkennen
            if ScanCommand.DOMAIN_CONTROLLER_DETECTION in task.scan_commands:
                dc_results = await self._detect_domain_controllers(discovery_results)
                discovery_results["domain_controllers"] = dc_results
            
            # Ergebnisse zusammenfassen
            task.result_data = discovery_results
            task.status = "completed"
            task.completed_at = datetime.now()
            task.progress_percentage = 100
            
            # Stats aktualisieren
            self.stats["tasks_completed"] += 1
            self.stats["devices_discovered"] += len(discovery_results.get("active_hosts", []))
            scan_duration = (task.completed_at - task.started_at).total_seconds()
            self.stats["total_scan_time"] += scan_duration
            self.stats["last_activity"] = datetime.now().isoformat()
            
            logger.info(f"Scan abgeschlossen: {task.task_id}, {len(discovery_results.get('active_hosts', []))} Geräte gefunden")
            
            # Ergebnisse an Server senden
            await self._send_scan_results(task)
            
            return task
            
        except Exception as e:
            logger.error(f"Scan-Fehler: {e}")
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now()
            
            self.stats["tasks_failed"] += 1
            self.stats["last_activity"] = datetime.now().isoformat()
            
            raise
    
    async def _perform_ping_sweep(self, ip_range: str) -> Dict[str, Any]:
        """
        Führt Ping-Sweep durch
        
        Args:
            ip_range: IP-Bereich als CIDR oder IP-Bereich
            
        Returns:
            Dictionary mit aktiven Hosts
        """
        logger.info(f"Ping-Sweep für {ip_range}")
        
        # Für Testzwecke simulieren wir Ergebnisse
        # In Produktion: nmap, fping oder ähnliches verwenden
        await asyncio.sleep(1)  # Simuliere Scan-Dauer
        
        # Simulierte Ergebnisse
        return {
            "active_hosts": [
                {"ip": "192.168.1.1", "hostname": "router.local", "response_time_ms": 2},
                {"ip": "192.168.1.10", "hostname": "pc01.local", "response_time_ms": 5},
                {"ip": "192.168.1.20", "hostname": "server01.local", "response_time_ms": 3},
                {"ip": "192.168.1.30", "hostname": "printer01.local", "response_time_ms": 10},
            ],
            "total_scanned": 254,
            "active_count": 4,
            "scan_duration_seconds": 5.2
        }
    
    async def _collect_mac_addresses(self, hosts: List[Dict]) -> Dict[str, str]:
        """
        Sammelt MAC-Adressen für Hosts
        
        Args:
            hosts: Liste von Host-Dictionaries
            
        Returns:
            Dictionary mit IP->MAC Zuordnung
        """
        logger.info(f"MAC-Adressen sammeln für {len(hosts)} Hosts")
        
        await asyncio.sleep(0.5)  # Simuliere Scan-Dauer
        
        # Simulierte MAC-Adressen
        mac_results = {}
        for host in hosts:
            ip = host.get("ip")
            if ip:
                # Generiere fiktive MAC-Adresse
                mac_parts = []
                for i in range(6):
                    mac_parts.append(f"{hashlib.md5(f'{ip}{i}'.encode()).hexdigest()[-2:]}")
                mac_address = ":".join(mac_parts).upper()
                mac_results[ip] = mac_address
        
        return mac_results
    
    async def _perform_port_scan(self, hosts: List[Dict], ports: str) -> Dict[str, List[int]]:
        """
        Führt Port-Scan durch
        
        Args:
            hosts: Liste von Host-Dictionaries
            ports: Komma-getrennte Liste von Ports
            
        Returns:
            Dictionary mit IP->[offene Ports] Zuordnung
        """
        logger.info(f"Port-Scan für {len(hosts)} Hosts, Ports: {ports}")
        
        await asyncio.sleep(1)  # Simuliere Scan-Dauer
        
        port_list = [int(p.strip()) for p in ports.split(",")] if ports else [22, 80, 443, 3389]
        
        # Simulierte Ergebnisse
        port_results = {}
        for host in hosts:
            ip = host.get("ip")
            if ip:
                # Simuliere zufällige offene Ports
                open_ports = []
                for port in port_list:
                    import random
                    if random.random() > 0.7:  # 30% Chance dass Port offen ist
                        open_ports.append(port)
                if open_ports:
                    port_results[ip] = open_ports
        
        return port_results
    
    async def _detect_operating_systems(self, hosts: List[Dict]) -> Dict[str, str]:
        """
        Erkennt Betriebssysteme
        
        Args:
            hosts: Liste von Host-Dictionaries
            
        Returns:
            Dictionary mit IP->OS Zuordnung
        """
        logger.info(f"OS-Erkennung für {len(hosts)} Hosts")
        
        await asyncio.sleep(0.8)  # Simuliere Scan-Dauer
        
        # Simulierte OS-Erkennung
        os_results = {}
        os_versions = ["Windows 10", "Windows 11", "Windows Server 2022", 
                      "Ubuntu 22.04", "CentOS 7", "Debian 11", "macOS 14"]
        
        import random
        for host in hosts:
            ip = host.get("ip")
            if ip:
                os_results[ip] = random.choice(os_versions)
        
        return os_results
    
    async def _detect_windows_computers(self, discovery_data: Dict) -> List[Dict]:
        """Erkennt Windows-Computer"""
        logger.info("Windows-Computer Erkennung")
        
        await asyncio.sleep(0.3)
        
        # Simulierte Windows-Erkennung
        windows_computers = []
        for host in discovery_data.get("active_hosts", []):
            ip = host.get("ip")
            if ip and ip.endswith(".10") or ip.endswith(".20"):  # Simulierte Windows-Hosts
                windows_computers.append({
                    "ip": ip,
                    "hostname": host.get("hostname"),
                    "os": "Windows",
                    "domain_joined": random.choice([True, False])
                })
        
        return windows_computers
    
    async def _detect_domain_controllers(self, discovery_data: Dict) -> List[Dict]:
        """Erkennt Domain Controller"""
        logger.info("Domain Controller Erkennung")
        
        await asyncio.sleep(0.3)
        
        # Simulierte DC-Erkennung
        dc_list = []
        for host in discovery_data.get("active_hosts", []):
            ip = host.get("ip")
            if ip == "192.168.1.1":  # Simulierter DC
                dc_list.append({
                    "ip": ip,
                    "hostname": "dc01.local",
                    "domain": "example.local",
                    "roles": ["Domain Controller", "DNS Server", "Global Catalog"]
                })
        
        return dc_list
    
    async def cancel_current_task(self):
        """Bricht aktuellen Scan ab"""
        if not self.current_task or self.current_task.status != "running":
            return
        
        logger.info(f"Scan wird abgebrochen: {self.current_task.task_id}")
        self.current_task.status = "canceled"
        self.current_task.completed_at = datetime.now()
        self.current_task.error_message = "Scan abgebrochen durch Benutzer"
        
        # Hier: Echte Abbruchlogik implementieren
    
    async def _send_message(self, message: Dict):
        """Sendet Nachricht an Server"""
        if not self.connection:
            raise ConnectionError("Keine Verbindung")
        
        try:
            message_json = json.dumps(message)
            self.connection.sendall(message_json.encode() + b"\n")
        except Exception as e:
            logger.error(f"Fehler beim Senden von Nachricht: {e}")
            raise
    
    async def _receive_message(self, timeout: int = 30) -> Dict:
        """Empfängt Nachricht vom Server"""
        if not self.connection:
            raise ConnectionError("Keine Verbindung")
        
        try:
            self.connection.settimeout(timeout)
            data = b""
            while True:
                chunk = self.connection.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            
            message_json = data.decode().strip()
            return json.loads(message_json)
        
        except socket.timeout:
            raise TimeoutError("Empfangstimeout")
        except Exception as e:
            logger.error(f"Fehler beim Empfangen von Nachricht: {e}")
            raise
    
    async def _send_scan_results(self, task: ScanTask):
        """Sendet Scan-Ergebnisse an Server"""
        results_message = {
            "type": "scan_results",
            "task_id": task.task_id,
            "agent_id": self.config.agent_id,
            "results": task.result_data,
            "scan_duration": (task.completed_at - task.started_at).total_seconds(),
            "timestamp": datetime.now().isoformat()
        }
        
        await self._send_message(results_message)
    
    def _is_ip_range_allowed(self, ip_range: str) -> bool:
        """
        Prüft ob IP-Bereich erlaubt ist
        
        Args:
            ip_range: Zu prüfender IP-Bereich
            
        Returns:
            True wenn erlaubt
        """
        if not self.config.allowed_ip_ranges:
            return True
        
        import ipaddress
        try:
            target_network = ipaddress.ip_network(ip_range, strict=False)
            
            for allowed_range in self.config.allowed_ip_ranges:
                allowed_network = ipaddress.ip_network(allowed_range, strict=False)
                if target_network.subnet_of(allowed_network):
                    return True
            
            return False
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt aktuellen Status zurück"""
        return {
            "agent_id": self.config.agent_id,
            "agent_name": self.config.agent_name,
            "status": self.status.value,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "stats": self.stats,
            "connection_info": {
                "type": self.config.connection_type,
                "endpoint": self.config.connection_endpoint,
                "connected_since": self.last_heartbeat.isoformat() if self.last_heartbeat else None
            }
        }