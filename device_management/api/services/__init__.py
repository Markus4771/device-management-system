"""
Services für Geschäftslogik des Device Management Systems
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
from sqlalchemy.orm import Session
import logging

from ...models import Device, Customer, Location, User, FormDocument
from ...modules.glpi_connector.api_client import GLPIAPIClient
from ..schemas import DeviceCreate, DeviceUpdate

logger = logging.getLogger(__name__)


def normalize_mac_address(mac: str) -> Optional[str]:
    """
    Normalisiert eine MAC-Adresse ins Format AA:BB:CC:DD:EE:FF.
    
    Akzeptiert Formate:
    - AA:BB:CC:DD:EE:FF
    - AA-BB-CC-DD-EE-FF
    - AABB.CCDD.EEFF
    - AABBCCDDEEFF
    - AA BB CC DD EE FF
    """
    if not mac:
        return None
    
    # Entferne alle nicht-hexadezimalen Zeichen
    mac_clean = re.sub(r'[^a-fA-F0-9]', '', mac)
    
    # Prüfe Länge (48 Bits = 12 hex Zeichen)
    if len(mac_clean) != 12:
        return None
    
    # Formatiere ins gewünschte Format
    normalized = ':'.join(mac_clean[i:i+2].upper() for i in range(0, 12, 2))
    return normalized


def validate_ip_address(ip: str) -> bool:
    """
    Validiert eine IPv4 oder IPv6 Adresse.
    """
    if not ip:
        return True
    
    # IPv4 Regex
    ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    
    # IPv6 Regex (vereinfacht)
    ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::([0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}$|^[0-9a-fA-F]{1,4}::([0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$'
    
    return bool(re.match(ipv4_pattern, ip) or re.match(ipv6_pattern, ip))


class DeviceService:
    """Service für Geräteverwaltung"""
    
    @staticmethod
    def create_device(db: Session, device_data: DeviceCreate, user_id: str) -> Device:
        """Erstellt ein neues Gerät."""
        # MAC-Adresse normalisieren
        if device_data.mac_address:
            normalized_mac = normalize_mac_address(device_data.mac_address)
            if normalized_mac:
                device_data.mac_address = normalized_mac
            else:
                # MAC-Adresse ungültig, setze None
                device_data.mac_address = None
        
        # IP-Adresse validieren
        if device_data.ip_address and not validate_ip_address(device_data.ip_address):
            device_data.ip_address = None
        
        # Kunde existiert?
        customer = db.query(Customer).filter(Customer.id == device_data.customer_id).first()
        if not customer:
            raise ValueError("Kunde nicht gefunden")
        
        # Standort prüfen falls angegeben
        if device_data.location_id:
            location = db.query(Location).filter(Location.id == device_data.location_id).first()
            if not location:
                raise ValueError("Standort nicht gefunden")
        
        # Gerät erstellen
        db_device = Device(
            **device_data.dict(exclude_unset=True),
            status="active",
            source="manual",
            created_by=user_id,
            sync_status="pending"
        )
        
        db.add(db_device)
        db.commit()
        db.refresh(db_device)
        
        logger.info(f"Device created: {db_device.pc_name} (ID: {db_device.id})")
        
        # GLPI-Synchronisation im Hintergrund starten (async)
        # Hier würden wir einen Celery Task starten
        
        return db_device
    
    @staticmethod
    def update_device(db: Session, device_id: str, device_data: DeviceUpdate, user_id: str) -> Device:
        """Aktualisiert ein vorhandenes Gerät."""
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise ValueError("Gerät nicht gefunden")
        
        # MAC-Adresse normalisieren falls geändert
        if device_data.mac_address is not None:
            normalized_mac = normalize_mac_address(device_data.mac_address)
            if normalized_mac:
                device_data.mac_address = normalized_mac
            else:
                device_data.mac_address = None
        
        # IP-Adresse validieren falls geändert
        if device_data.ip_address is not None and not validate_ip_address(device_data.ip_address):
            device_data.ip_address = None
        
        # Nur überschreiben, wenn Werte gesetzt sind
        update_data = device_data.dict(exclude_unset=True)
        
        # Kunde prüfen falls geändert
        if "customer_id" in update_data:
            customer = db.query(Customer).filter(Customer.id == update_data["customer_id"]).first()
            if not customer:
                raise ValueError("Kunde nicht gefunden")
        
        # Standort prüfen falls geändert
        if "location_id" in update_data and update_data["location_id"]:
            location = db.query(Location).filter(Location.id == update_data["location_id"]).first()
            if not location:
                raise ValueError("Standort nicht gefunden")
        
        for field, value in update_data.items():
            setattr(device, field, value)
        
        device.updated_at = datetime.utcnow()
        device.sync_status = "pending"  # Neu synchronisieren
        
        db.commit()
        db.refresh(device)
        
        logger.info(f"Device updated: {device.pc_name} (ID: {device_id})")
        
        return device
    
    @staticmethod
    def get_device(db: Session, device_id: str) -> Optional[Device]:
        """Ruft ein Gerät anhand der ID ab."""
        return db.query(Device).filter(Device.id == device_id).first()
    
    @staticmethod
    def get_devices_by_customer(db: Session, customer_id: str) -> List[Device]:
        """Ruft alle Geräte eines Kunden ab."""
        return db.query(Device).filter(
            Device.customer_id == customer_id,
            Device.status == "active"
        ).all()
    
    @staticmethod
    def search_devices(db: Session, search_term: str, customer_id: Optional[str] = None) -> List[Device]:
        """Sucht Geräte nach verschiedenen Kriterien."""
        query = db.query(Device).filter(Device.status == "active")
        
        if customer_id:
            query = query.filter(Device.customer_id == customer_id)
        
        if search_term:
            query = query.filter(
                (Device.pc_name.ilike(f"%{search_term}%")) |
                (Device.serial_number.ilike(f"%{search_term}%")) |
                (Device.mac_address.ilike(f"%{search_term}%")) |
                (Device.user.ilike(f"%{search_term}%")) |
                (Device.technician.ilike(f"%{search_term}%"))
            )
        
        return query.limit(50).all()


class GLPIAsyncService:
    """Service für GLPI-Synchronisation (Hintergrundaufgaben)"""
    
    @staticmethod
    def sync_device_to_glpi(device: Device, customer: Customer):
        """
        Synchronisiert ein Gerät mit GLPI.
        
        Diese Funktion sollte als Hintergrundtask (Celery) ausgeführt werden.
        """
        try:
            with GLPIAPIClient() as glpi_client:
                # GLPI Computer-Daten erstellen
                computer_data = {
                    "name": device.pc_name,
                    "entities_id": customer.glpi_entity_id,
                    "serial": device.serial_number,
                    "otherserial": device.mac_address,  # MAC Adresse
                    "comment": device.notes
                }
                
                if device.location_id:
                    location = device.location
                    if location and location.glpi_location_id:
                        computer_data["locations_id"] = location.glpi_location_id
                
                # Prüfen ob Gerät bereits in GLPI existiert
                if device.glpi_computer_id:
                    # Update bestehendes Gerät
                    success = glpi_client.update_computer(device.glpi_computer_id, computer_data)
                    if success:
                        device.sync_status = "synced"
                        device.last_sync_with_glpi = datetime.utcnow()
                        logger.info(f"Device {device.id} updated in GLPI")
                    else:
                        device.sync_status = "error"
                        logger.error(f"Failed to update device {device.id} in GLPI")
                else:
                    # Neues Gerät erstellen
                    glpi_computer_id = glpi_client.create_computer(computer_data)
                    if glpi_computer_id:
                        device.glpi_computer_id = glpi_computer_id
                        device.sync_status = "synced"
                        device.last_sync_with_glpi = datetime.utcnow()
                        logger.info(f"Device {device.id} created in GLPI with ID {glpi_computer_id}")
                    else:
                        device.sync_status = "error"
                        logger.error(f"Failed to create device {device.id} in GLPI")
                
                # Session wird automatisch durch Context Manager geschlossen
                
        except Exception as e:
            logger.error(f"Error syncing device {device.id} to GLPI: {e}")
            device.sync_status = "error"
        
        return device