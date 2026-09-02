"""
Pydantic Schemas für Netzwerk-Scan API (Phase 2)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
import ipaddress
import re


class NetworkScanRequest(BaseModel):
    """
    Schema für Netzwerk-Scan Anfragen
    
    Sicherheitshinweis: IP-Bereiche müssen geprüft werden.
    """
    ip_range: str = Field(..., description="IP-Bereich im CIDR-Format oder Bereich, z.B. '192.168.1.0/24' oder '192.168.1.1-192.168.1.100'")
    customer_id: Optional[int] = Field(None, description="GLPI Entity ID für Kunden-Zuordnung")
    customer_name: Optional[str] = Field(None, description="Kundenname für Referenz")
    scan_type: str = Field("ping_sweep", description="Scan-Typ: ping_sweep, arp_discovery, port_scan, os_detection")
    port_list: Optional[List[int]] = Field(None, description="Liste zu scannender Ports (nur für port_scan)")
    timeout_seconds: int = Field(5, ge=1, le=60, description="Timeout pro Host in Sekunden")
    max_threads: int = Field(10, ge=1, le=50, description="Maximale parallele Threads")
    auto_sync_glpi: bool = Field(True, description="Automatische Synchronisation mit GLPI nach Scan")
    require_approval: bool = Field(True, description="Scan erfordert manuelle Freigabe")
    scan_comment: Optional[str] = Field(None, description="Kommentar/Beschreibung für Audit-Log")
    
    @validator('ip_range')
    def validate_ip_range(cls, v):
        """Validiert IP-Bereich"""
        try:
            # CIDR-Format prüfen
            if '/' in v:
                network = ipaddress.ip_network(v, strict=False)
                if network.is_private:
                    return v
                else:
                    raise ValueError("Nur private IP-Bereiche sind für Scans erlaubt")
            
            # Bereichsformat prüfen (192.168.1.1-192.168.1.100)
            elif '-' in v:
                parts = v.split('-')
                if len(parts) == 2:
                    start_ip = ipaddress.ip_address(parts[0].strip())
                    end_ip = ipaddress.ip_address(parts[1].strip())
                    
                    if (isinstance(start_ip, ipaddress.IPv4Address) and 
                        isinstance(end_ip, ipaddress.IPv4Address) and
                        start_ip <= end_ip):
                        # Prüfe ob private IP
                        if start_ip.is_private:
                            return v
                        else:
                            raise ValueError("Nur private IP-Bereiche sind für Scans erlaubt")
                    else:
                        raise ValueError("Ungültiges IP-Bereichsformat")
                else:
                    raise ValueError("Bereich muss Format 'start-end' haben")
            
            # Einzelne IP
            else:
                ip = ipaddress.ip_address(v)
                if ip.is_private:
                    return v
                else:
                    raise ValueError("Nur private IPs sind für Scans erlaubt")
                
        except ValueError as e:
            raise ValueError(f"Ungültiger IP-Bereich: {str(e)}")
    
    @validator('scan_type')
    def validate_scan_type(cls, v):
        """Validiert Scan-Typ"""
        allowed_types = ["ping_sweep", "arp_discovery", "port_scan", "os_detection"]
        if v not in allowed_types:
            raise ValueError(f"Scan-Typ muss einer von {allowed_types} sein")
        return v
    
    @validator('port_list')
    def validate_ports(cls, v, values):
        """Validiert Port-Liste"""
        if v is None:
            return v
        
        if 'scan_type' in values and values['scan_type'] != 'port_scan':
            return None
        
        # Sicherheitsprüfung: Nur bestimmte Ports erlauben
        allowed_ports = {
            20, 21, 22, 23, 25, 53, 80, 110, 119, 123, 143, 161, 162, 389,
            443, 445, 465, 587, 636, 993, 995, 1720, 1723, 3389, 5060, 5900,
            8080, 8443, 3306, 5432, 27017
        }
        
        invalid_ports = [p for p in v if p < 1 or p > 65535]
        if invalid_ports:
            raise ValueError(f"Ports müssen zwischen 1 und 65535 sein: {invalid_ports}")
        
        # Warnung für gefährliche Ports (optional)
        dangerous_ports = {135, 137, 138, 139, 445}
        dangerous_found = set(v) & dangerous_ports
        if dangerous_found:
            raise ValueError(f"Gefährliche Ports nicht erlaubt: {dangerous_found}")
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "ip_range": "192.168.1.0/24",
                "customer_id": 123, "scan_comment": "Kundennetzwerk Scan",
                "scan_type": "ping_sweep",
                "timeout_seconds": 5,
                "auto_sync_glpi": True
            }
        }


class NetworkDevice(BaseModel):
    """Schema für erkannte Netzwerkgeräte"""
    ip_address: str = Field(..., description="IP-Adresse des Geräts")
    hostname: Optional[str] = Field(None, description="Hostname (DNS/NetBIOS)")
    mac_address: Optional[str] = Field(None, description="MAC-Adresse im AA:BB:CC:DD:EE:FF Format")
    vendor: Optional[str] = Field(None, description="Hersteller aus MAC-Adresse")
    os_type: Optional[str] = Field(None, description="Betriebssystem-Typ")
    os_version: Optional[str] = Field(None, description="Betriebssystem-Version")
    device_type: Optional[str] = Field(None, description="Gerätetyp: computer, printer, switch, router, etc.")
    domain: Optional[str] = Field(None, description="Domain/Zugehörigkeit")
    is_domain_controller: bool = Field(False, description="Ist Domain Controller")
    open_ports: List[int] = Field(default_factory=list, description="Erkannte offene Ports")
    is_active: bool = Field(True, description="Gerät ist aktiv/online")
    last_seen: Optional[datetime] = Field(None, description="Letzte Erkennung")
    
    @validator('mac_address')
    def validate_mac_address(cls, v):
        """Validiert und normalisiert MAC-Adresse"""
        if v is None:
            return v
        
        # Entferne Sonderzeichen
        clean_mac = re.sub(r'[^0-9A-Fa-f]', '', v)
        
        if len(clean_mac) != 12:
            raise ValueError("MAC-Adresse muss 12 Hex-Zeichen haben")
        
        # Formatieren als AA:BB:CC:DD:EE:FF
        formatted = ':'.join([clean_mac[i:i+2].upper() for i in range(0, 12, 2)])
        return formatted
    
    class Config:
        schema_extra = {
            "example": {
                "ip_address": "192.168.1.100",
                "hostname": "pc-01.local",
                "mac_address": "00:11:22:33:44:55",
                "vendor": "Dell",
                "os_type": "windows",
                "os_version": "Windows 10 Pro",
                "device_type": "computer",
                "domain": "home.local",
                "is_domain_controller": False,
                "open_ports": [80, 443, 3389],
                "is_active": True
            }
        }


class NetworkScanResponse(BaseModel):
    """Schema für Netzwerk-Scan Antwort"""
    scan_id: str = Field(..., description="Eindeutige Scan-ID")
    status: str = Field(..., description="Scan-Status: pending, running, completed, failed")
    network_range: str = Field(..., description="Gescannter IP-Bereich")
    scan_start_time: datetime = Field(..., description="Scan-Startzeit")
    scan_end_time: Optional[datetime] = Field(None, description="Scan-Endzeit")
    devices_found: List[NetworkDevice] = Field(default_factory=list, description="Gefundene Geräte")
    total_devices: int = Field(0, description="Gesamtanzahl gefundener Geräte")
    new_devices_count: int = Field(0, description="Anzahl neuer Geräte (nicht in GLPI)")
    updated_devices_count: int = Field(0, description="Anzahl aktualisierter Geräte")
    scan_duration: Optional[float] = Field(None, description="Scan-Dauer in Sekunden")
    error_message: Optional[str] = Field(None, description="Fehlermeldung bei Fehlschlag")
    glpi_sync_initiated: bool = Field(False, description="GLPI-Sync wurde ausgelöst")
    glpi_sync_result: Optional[Dict[str, Any]] = Field(None, description="GLPI-Sync Ergebnis")
    
    class Config:
        schema_extra = {
            "example": {
                "scan_id": "scan_20250101120000_abc123",
                "status": "completed",
                "network_range": "192.168.1.0/24",
                "scan_start_time": "2025-01-01T12:00:00Z",
                "scan_end_time": "2025-01-01T12:05:30Z",
                "total_devices": 15,
                "glpi_sync_initiated": True
            }
        }


class DNSResolutionRequest(BaseModel):
    """Schema für DNS-Auflösungs-Anfragen"""
    query: str = Field(..., description="DNS-Query (Hostname oder IP-Adresse)")
    query_type: str = Field("forward", description="Query-Typ: forward (Hostname->IP) oder reverse (IP->Hostname)")
    record_type: str = Field("A", description="DNS-Record-Typ: A, AAAA, CNAME, MX, NS, PTR, TXT, SOA")
    dns_server: Optional[str] = Field(None, description="Optional spezifischer DNS-Server")
    
    @validator('query_type')
    def validate_query_type(cls, v):
        """Validiert Query-Typ"""
        allowed_types = ["forward", "reverse"]
        if v not in allowed_types:
            raise ValueError(f"Query-Typ muss einer von {allowed_types} sein")
        return v
    
    @validator('record_type')
    def validate_record_type(cls, v):
        """Validiert DNS-Record-Typ"""
        allowed_types = ["A", "AAAA", "CNAME", "MX", "NS", "PTR", "TXT", "SOA", "SRV"]
        if v not in allowed_types:
            raise ValueError(f"Record-Typ muss einer von {allowed_types} sein")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "query": "google.com",
                "query_type": "forward",
                "record_type": "A"
            }
        }


class DNSRecord(BaseModel):
    """Schema für DNS-Einträge"""
    name: str = Field(..., description="DNS-Name")
    record_type: str = Field(..., description="Record-Typ")
    value: str = Field(..., description="Record-Wert")
    ttl: Optional[int] = Field(None, description="Time-To-Live")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "google.com",
                "record_type": "A",
                "value": "142.250.185.78",
                "ttl": 300
            }
        }


class DNSResolutionResponse(BaseModel):
    """Schema für DNS-Auflösungs-Antwort"""
    query: str = Field(..., description="Ursprüngliche Query")
    query_type: str = Field(..., description="Query-Typ")
    answers: List[DNSRecord] = Field(default_factory=list, description="DNS-Antworten")
    authoritative: bool = Field(False, description="Antwort ist autoritativ")
    nameserver: Optional[str] = Field(None, description="Antwortender Nameserver")
    response_time_ms: Optional[float] = Field(None, description="Antwortzeit in Millisekunden")
    timestamp: datetime = Field(..., description="Zeitpunkt der Auflösung")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "google.com",
                "query_type": "forward",
                "answers": [{
                    "name": "google.com",
                    "record_type": "A",
                    "value": "142.250.185.78",
                    "ttl": 300
                }],
                "authoritative": False,
                "response_time_ms": 45.2,
                "timestamp": "2025-01-01T12:00:00Z"
            }
        }


class MACVendorLookupRequest(BaseModel):
    """Schema für MAC-Vendor-Lookup-Anfragen"""
    mac_addresses: List[str] = Field(..., description="Liste von MAC-Adressen")
    
    @validator('mac_addresses')
    def validate_mac_addresses(cls, v):
        """Validiert MAC-Adressen-Liste"""
        if not v:
            raise ValueError("Mindestens eine MAC-Adresse erforderlich")
        
        # Begrenze Anzahl für Performance/Sicherheit
        if len(v) > 100:
            raise ValueError("Zu viele MAC-Adressen in einer Anfrage (max. 100)")
        
        validated_macs = []
        for mac in v:
            # Entferne Sonderzeichen
            clean_mac = re.sub(r'[^0-9A-Fa-f]', '', mac)
            
            if len(clean_mac) >= 6:  # Mindestens OUI (6 Zeichen)
                validated_macs.append(mac)
            else:
                raise ValueError(f"Ungültige MAC-Adresse: {mac}")
        
        return validated_macs
    
    class Config:
        schema_extra = {
            "example": {
                "mac_addresses": ["00:11:22:33:44:55", "AA:BB:CC:DD:EE:FF"]
            }
        }


class VendorInfo(BaseModel):
    """Schema für Vendor-Informationen"""
    prefix: str = Field(..., description="MAC-Prefix (erste 6 Hex-Zeichen)")
    vendor: str = Field(..., description="Herstellername")
    address: Optional[str] = Field(None, description="Herstelleradresse")
    country: Optional[str] = Field(None, description="Herstellerland")
    assignment: Optional[str] = Field(None, description="Zuweisungstyp: MA-L, MA-M, MA-S")
    source: str = Field("IEEE OUI", description="Datenquelle")
    
    class Config:
        schema_extra = {
            "example": {
                "prefix": "00:11:22",
                "vendor": "Dell Inc.",
                "address": "One Dell Way, Round Rock, Texas, USA",
                "country": "US",
                "assignment": "MA-L",
                "source": "IEEE OUI"
            }
        }


class MACAddressInfo(BaseModel):
    """Schema für komplette MAC-Adressen-Information"""
    mac_address: str = Field(..., description="Originale MAC-Adresse")
    normalized_mac: str = Field(..., description="Normalisierte MAC-Adresse")
    vendor_prefix: Optional[str] = Field(None, description="Vendor-Prefix")
    vendor: Optional[VendorInfo] = Field(None, description="Hersteller-Info")
    is_universal: bool = Field(True, description="Universelle (nicht lokale) Adresse")
    is_multicast: bool = Field(False, description="Multicast-Adresse")
    
    class Config:
        schema_extra = {
            "example": {
                "mac_address": "00:11:22:33:44:55",
                "normalized_mac": "00:11:22:33:44:55",
                "vendor_prefix": "00:11:22",
                "vendor": {
                    "prefix": "00:11:22",
                    "vendor": "Dell Inc.",
                    "address": "One Dell Way, Round Rock, Texas, USA",
                    "source": "IEEE OUI"
                },
                "is_universal": True,
                "is_multicast": False
            }
        }


class MACVendorLookupResponse(BaseModel):
    """Schema für MAC-Vendor-Lookup-Antwort"""
    results: List[MACAddressInfo] = Field(default_factory=list, description="Lookup-Ergebnisse")
    vendor_statistics: Dict[str, int] = Field(default_factory=dict, description="Zähler pro Hersteller")
    total_processed: int = Field(0, description="Gesamtanzahl verarbeiteter MAC-Adressen")
    lookup_timestamp: datetime = Field(..., description="Zeitpunkt des Lookups")
    
    class Config:
        schema_extra = {
            "example": {
                "results": [{
                    "mac_address": "00:11:22:33:44:55",
                    "normalized_mac": "00:11:22:33:44:55",
                    "vendor_prefix": "00:11:22",
                    "vendor": {
                        "prefix": "00:11:22",
                        "vendor": "Dell Inc.",
                        "source": "IEEE OUI"
                    }
                }],
                "vendor_statistics": {"Dell Inc.": 1},
                "total_processed": 1,
                "lookup_timestamp": "2025-01-01T12:00:00Z"
            }
        }


class GLPISyncRequest(BaseModel):
    """Schema für GLPI-Synchronisations-Anfragen"""
    entity_id: int = Field(..., description="GLPI Entity ID")
    scan_ids: Optional[List[str]] = Field(None, description="Liste von Scan-IDs für Sync")
    sync_type: str = Field("auto", description="Sync-Typ: auto, manual, delta_only")
    update_existing: bool = Field(True, description="Bestehende Geräte aktualisieren")
    create_missing: bool = Field(True, description="Fehlende Geräte in GLPI anlegen")
    mark_removed: bool = Field(False, description="Nicht mehr gefundene Geräte markieren")
    
    @validator('sync_type')
    def validate_sync_type(cls, v):
        """Validiert Sync-Typ"""
        allowed_types = ["auto", "manual", "delta_only"]
        if v not in allowed_types:
            raise ValueError(f"Sync-Typ muss einer von {allowed_types} sein")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "entity_id": 123,
                "scan_ids": ["scan_20250101120000_abc123"],
                "sync_type": "auto",
                "update_existing": True,
                "create_missing": True,
                "mark_removed": False
            }
        }


class GLPISyncResponse(BaseModel):
    """Schema für GLPI-Synchronisations-Antwort"""
    sync_id: str = Field(..., description="Eindeutige Sync-ID")
    entity_id: int = Field(..., description="GLPI Entity ID")
    sync_start_time: datetime = Field(..., description="Sync-Startzeit")
    sync_end_time: Optional[datetime] = Field(None, description="Sync-Endzeit")
    new_devices: int = Field(0, description="Neue Geräte in GLPI angelegt")
    updated_devices: int = Field(0, description="Bestehende Geräte aktualisiert")
    removed_devices: int = Field(0, description="Als entfernt markierte Geräte")
    failed_devices: int = Field(0, description="Fehlgeschlagene Geräte")
    sync_duration: Optional[float] = Field(None, description="Sync-Dauer in Sekunden")
    sync_status: str = Field(..., description="Sync-Status: pending, running, completed, failed")
    error_message: Optional[str] = Field(None, description="Fehlermeldung bei Fehlschlag")
    
    class Config:
        schema_extra = {
            "example": {
                "sync_id": "sync_20250101120000_xyz789",
                "entity_id": 123,
                "sync_start_time": "2025-01-01T12:00:00Z",
                "sync_end_time": "2025-01-01T12:01:30Z",
                "new_devices": 5,
                "updated_devices": 3,
                "removed_devices": 0,
                "failed_devices": 1,
                "sync_duration": 90.5,
                "sync_status": "completed",
                "error_message": None
            }
        }


class RemoteAgentStatus(BaseModel):
    """Schema für Remote-Agent-Status"""
    agent_id: str = Field(..., description="Eindeutige Agent-ID")
    agent_name: str = Field(..., description="Agent-Name")
    customer_id: Optional[int] = Field(None, description="Kunden-ID")
    customer_name: Optional[str] = Field(None, description="Kundenname")
    status: str = Field(..., description="Agent-Status: offline, online, busy, error")
    last_heartbeat: Optional[datetime] = Field(None, description="Letzter Heartbeat")
    connection_type: str = Field(..., description="Verbindungstyp: direct, vpn, proxy")
    connection_endpoint: Optional[str] = Field(None, description="Verbindungsendpunkt")
    current_task_id: Optional[str] = Field(None, description="Aktuelle Task-ID")
    network_interfaces: Optional[List[Dict[str, Any]]] = Field(None, description="Netzwerkschnittstellen")
    system_info: Optional[Dict[str, Any]] = Field(None, description="Systeminformationen")
    scan_capabilities: List[str] = Field(default_factory=list, description="Scan-Fähigkeiten")
    
    class Config:
        schema_extra = {
            "example": {
                "agent_id": "agent_001",
                "agent_name": "Kundennetzwerk-Scanner",
                "customer_id": 123,
                "customer_name": "Musterfirma GmbH",
                "status": "online",
                "last_heartbeat": "2025-01-01T12:00:00Z",
                "connection_type": "vpn",
                "connection_endpoint": "vpn.musterfirma.de",
                "current_task_id": "task_123",
                "scan_capabilities": ["ping_sweep", "arp_discovery", "dns_resolution"]
            }
        }


class ScanStatistics(BaseModel):
    """Schema für Scan-Statistiken"""
    period_days: int = Field(..., description="Statistik-Periode in Tagen")
    total_scans: int = Field(0, description="Gesamtzahl Scans")
    successful_scans: int = Field(0, description="Erfolgreiche Scans")
    failed_scans: int = Field(0, description="Fehlgeschlagene Scans")
    total_devices_found: int = Field(0, escription="Gesamt gefundene Geräte")
    new_devices_created: int = Field(0, description="Neue Geräte in GLPI angelegt")
    devices_updated: int = Field(0, description="Geräte aktualisiert")
    avg_scan_duration: float = Field(0.0, description="Durchschnittliche Scan-Dauer (Sekunden)")
    most_active_customers: List[Dict[str, Any]] = Field(default_factory=list, description="Aktivste Kunden")
    scan_type_distribution: Dict[str, int] = Field(default_factory=dict, description="Verteilung nach Scan-Typ")
    
    class Config:
        schema_extra = {
            "example": {
                "period_days": 30,
                "total_scans": 150,
                "successful_scans": 142,
                "failed_scans": 8,
                "total_devices_found": 1250,
                "new_devices_created": 85,
                "devices_updated": 320,
                "avg_scan_duration": 45.3,
                "most_active_customers": [
                    {"customer_id": 123, "customer_name": "Musterfirma", "scan_count": 45}
                ]
            }
        }


class NetworkDeviceStats(BaseModel):
    """Schema für Gerätestatistiken"""
    customer_id: Optional[int] = Field(None, description="Kunden-ID für Filter")
    total_devices: int = Field(0, description="Gesamtzahl Geräte")
    windows_devices: int = Field(0, description="Windows-Geräte")
    linux_devices: int = Field(0, description="Linux-Geräte")
    network_devices: int = Field(0, description="Netzwerkgeräte")
    printers: int = Field(0, description="Drucker")
    servers: int = Field(0, description="Server")
    domain_controllers: int = Field(0, description="Domain Controller")
    device_status: Dict[str, int] = Field(default_factory=dict, description="Status-Verteilung")
    top_vendors: List[Dict[str, Any]] = Field(default_factory=list, description="Top-Hersteller")
    os_distribution: Dict[str, int] = Field(default_factory=dict, description="OS-Verteilung")
    
    class Config:
        schema_extra = {
            "example": {
                "customer_id": 123,
                "total_devices": 145,
                "windows_devices": 120,
                "linux_devices": 15,
                "network_devices": 8,
                "printers": 5,
                "servers": 3,
                "domain_controllers": 2,
                "device_status": {"online": 100, "offline": 45},
                "top_vendors": [
                    {"vendor": "Dell", "count": 45, "percentage": 31},
                ]
            }
        }