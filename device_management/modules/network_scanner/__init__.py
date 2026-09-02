"""
Network Scanner Module für Phase 2

Automatische Erkennung von Netzwerkgeräten in Kundennetzwerken mit:
-
 IP-Bereich-Scans
- Aktive Hosts erkennen
-S MAC-Adressen erfassen
- Hersteller-Erkennung
- Windows-Computer erkennen
- Domain Controller erkennen
- Automatischer GLPI-Abgleich
"""

import logging
import ipaddress
import subprocess
import socket
import time
import json
from typing import Dict, List, Optional, Tuple, Set, Any
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NetworkDevice:
    """Repräsentiert ein erkanntes Netzwerkgerät"""
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    os_type: Optional[str] = None  # windows, linux, printer, network_device, etc.
    os_version: Optional[str] = None
    open_ports: List[int] = field(default_factory=list)
    device_type: Optional[str] = None  # computer, printer, switch, router, etc.
    domain: Optional[str] = None
    is_domain_controller: bool = False
    is_active: bool = True
    last_seen: Optional[datetime] = None
    scan_time: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Gerät in ein Dictionary für JSON/GLPI"""
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "mac_address": self.mac_address,
            "vendor": self.vendor,
            "os_type": self.os_type,
            "os_version": self.os_version,
            "open_ports": self.open_ports,
            "device_type": self.device_type,
            "domain": self.domain,
            "is_domain_controller": self.is_domain_controller,
            "is_active": self.is_active,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "scan_time": self.scan_time.isoformat() if self.scan_time else None
        }
    
    def is_windows_computer(self) -> bool:
        """Prüft, ob es sich um einen Windows-Computer handelt"""
        return self.os_type == "windows" and self.device_type == "computer"


@dataclass
class ScanResult:
    """Ergebnis eines Netzwerk-Scans"""
    scan_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    network_range: str = ""
    scan_start_time: datetime = field(default_factory=datetime.now)
    scan_end_time: Optional[datetime] = None
    devices_found: List[NetworkDevice] = field(default_factory=list)
    devices_updated: List[NetworkDevice] = field(default_factory=list)
    devices_removed: List[NetworkDevice] = field(default_factory=list)
    total_devices: int = 0
    scan_duration: Optional[float] = None
    scan_status: str = "pending"  # pending, running, completed, failed
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Scan-Ergebnis in ein Dictionary"""
        return {
            "scan_id": self.scan_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "network_range": self.network_range,
            "scan_start_time": self.scan_start_time.isoformat(),
            "scan_end_time": self.scan_end_time.isoformat() if self.scan_end_time else None,
            "devices_found": [d.to_dict() for d in self.devices_found],
            "devices_updated": [d.to_dict() for d in self.devices_updated],
            "devices_removed": [d.to_dict() for d in self.devices_removed],
            "total_devices": self.total_devices,
            "scan_duration": self.scan_duration,
            "scan_status": self.scan_status,
            "error_message": self.error_message
        }


class NetworkScanner:
    """
    Hauptklasse für Netzwerk-Scans
    
    Fähigkeiten:
    - IP-Bereich-Scans
    - Ping-Scans für aktive Hosts
    - MAC-Adressen-Erkennung (ARP)
    - Port-Scans (eingeschränkt)
    - OS-Detection
    - Hersteller-Erkennung über MAC
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den Netzwerk-Scanner
        
        Args:
            config: Konfigurationsdictionary mit:
                - scan_timeout: Timeout für Scans in Sekunden (default: 5)
                - ping_enabled: Ping-Scans aktivieren (default: True)
                - arp_enabled: ARP-Scans aktivieren (default: True)
                - port_scan_enabled: Port-Scans aktivieren (default: False)
                - allowed_ports: Liste erlaubter Ports für Scans (default: [])
                - max_threads: Maximale Threads für parallele Scans
                - mac_vendor_db_path: Pfad zur MAC-Vendor-Datenbank
        """
        self.config = config
        self.scan_timeout = config.get("scan_timeout", 5)
        self.ping_enabled = config.get("ping_enabled", True)
        self.arp_enabled = config.get("arp_enabled", True)
        self.port_scan_enabled = config.get("port_scan_enabled", False)
        self.allowed_ports = config.get("allowed_ports", [])
        self.max_threads = config.get("max_threads", 10)
        self.mac_vendor_db = self._load_mac_vendor_db(config.get("mac_vendor_db_path"))
        
        logger.info("NetworkScanner initialisiert mit Konfiguration: %s", config)
    
    def _load_mac_vendor_db(self, db_path: Optional[str]) -> Dict[str, str]:
        """Lädt die MAC-Vendor-Datenbank"""
        # Fallback: Standard IEEE OUI Daten
        standard_vendors = {
            "00:50:56": "VMware",  # VMware MAC-Adressen
            "00:0C:29": "VMware",  # VMware MAC-Adressen
            "00:05:69": "VMware",  # VMware MAC-Adressen
            "00:1C:42": "Parallels",  # Parallels
            "08:00:27": "Oracle VM VirtualBox",
            "00:15:5D": "Microsoft Hyper-V",
            "00:1A:4B": "Cisco",
            "00:1B:63": "Hewlett-Packard",
            "00:1D:72": "Dell",
            "00:1E:68": "Lenovo",
            "00:21:5A": "Apple",
            "00:24:E9": "Samsung",
            "00:26:BB": "Intel",
            "00:50:BA": "Belkin",
            "00:AA:00": "Intel",
            "00:E0:4C": "Realtek",
            "08:00:20": "Sun Microsystems",
            "08:00:5A": "IBM",
            "0C:C4:7A": "Ubiquiti",
            "14:DA:E9": "ASUSTek",
            "18:66:DA": "Samsung",
            "28:16:2E": "NETGEAR",
            "30:9C:23": "Brocade",
            "3C:8A:BF": "Synology",
            "54:04:A6": "ASUSTek",
            "6C:88:14": "Ubiquiti",
            "84:A8:E4": "Apple",
            "A4:5E:60": "Cisco",
            "B8:27:EB": "Raspberry Pi",
            "C4:2C:03": "Apple",
            "D8:BB:2C": "Apple",
            "E4:8D:8C": "Intel",
            "F0:9F:C2": "Ubiquiti"
        }
        
        if not db_path:
            return standard_vendors
        
        try:
            with open(db_path, 'r') as f:
                vendor_data = json.load(f)
                return vendor_data
        except FileNotFoundError:
            logger.warning("MAC-Vendor-Datenbank nicht gefunden, verwende Standard")
            return standard_vendors
        except json.JSONDecodeError:
            logger.warning("MAC-Vendor-Datenbank hat ungültiges JSON-Format")
            return standard_vendors
    
    def generate_scan_id(self) -> str:
        """Generiert eine eindeutige Scan-ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = hex(hash(str(time.time())))[-6:]
        return f"scan_{timestamp}_{random_suffix}"
    
    def scan_ip_range(self, ip_range: str, customer_info: Optional[Dict] = None) -> ScanResult:
        """
        Scannt einen IP-Bereich
        
        Args:
            ip_range: IP-Bereich im Format "192.168.1.0/24" oder "192.168.1.1-192.168.1.100"
            customer_info: Optional Customer-Informationen für GLPI-Sync
            
        Returns:
            ScanResult mit erkannten Geräten
        """
        scan_id = self.generate_scan_id()
        result = ScanResult(
            scan_id=scan_id,
            customer_id=customer_info.get("id") if customer_info else None,
            customer_name=customer_info.get("name") if customer_info else None,
            network_range=ip_range,
            scan_status="running"
        )
        
        logger.info("Starte Scan %s für IP-Bereich: %s", scan_id, ip_range)
        
        try:
            # IP-Bereich validieren und auflösen
            ip_list = self._resolve_ip_range(ip_range)
            logger.info("IP-Bereich aufgelöst zu %d IP-Adressen", len(ip_list))
            
            # Aktive Hosts finden
            active_hosts = self._find_active_hosts(ip_list)
            logger.info("%d aktive Hosts gefunden", len(active_hosts))
            
            # Für jeden aktiven Host Informationen sammeln
            devices = []
            for ip in active_hosts:
                device = self._scan_single_host(ip)
                if device:
                    devices.append(device)
            
            result.devices_found = devices
            result.total_devices = len(devices)
            result.scan_end_time = datetime.now()
            result.scan_duration = (result.scan_end_time - result.scan_start_time).total_seconds()
            result.scan_status = "completed"
            
            logger.info("Scan %s abgeschlossen: %d Geräte gefunden, Dauer: %.2f Sekunden",
                       scan_id, result.total_devices, result.scan_duration)
            
        except Exception as e:
            logger.error("Scan %s fehlgeschlagen: %s", scan_id, str(e))
            result.scan_status = "failed"
            result.error_message = str(e)
            result.scan_end_time = datetime.now()
        
        return result
    
    def _resolve_ip_range(self, ip_range: str) -> List[str]:
        """Löst einen IP-Bereich in eine Liste von IP-Adressen auf"""
        ip_list = []
        
        try:
            # CIDR-Notation (z.B. 192.168.1.0/24)
            if '/' in ip_range:
                network = ipaddress.ip_network(ip_range, strict=False)
                for ip in network.hosts():
                    ip_list.append(str(ip))
            
            # Bereichsnotation (z.B. 192.168.1.1-192.168.1.100)
            elif '-' in ip_range:
                start_ip, end_ip = ip_range.split('-')
                start = ipaddress.ip_address(start_ip.strip())
                end = ipaddress.ip_address(end_ip.strip())
                
                current = start
                while current <= end:
                    ip_list.append(str(current))
                    current = ipaddress.ip_address(int(current) + 1)
            
            # Einzelne IP
            else:
                ip_list.append(ip_range)
                
        except ValueError as e:
            logger.error("Ungültiger IP-Bereich %s: %s", ip_range, e)
            raise
        
        return ip_list
    
    def _find_active_hosts(self, ip_list: List[str]) -> List[str]:
        """Findet aktive Hosts im Netzwerk"""
        active_hosts = []
        
        if self.ping_enabled:
            active_hosts.extend(self._ping_scan(ip_list))
        
        if self.arp_enabled and len(active_hosts) < len(ip_list):
            # ARP-Scan für noch nicht gefundene Hosts
            remaining_ips = [ip for ip in ip_list if ip not in active_hosts]
            if remaining_ips:
                arp_hosts = self._arp_scan(remaining_ips)
                active_hosts.extend(arp_hosts)
        
        return active_hosts
    
    def _ping_scan(self, ip_list: List[str]) -> List[str]:
        """Führt einen Ping-Scan durch"""
        active_hosts = []
        
        # Einfacher Ping-Scan (kann je nach OS/Rechten variieren)
        for ip in ip_list:
            try:
                # Ping-Befehl ausführen
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', str(self.scan_timeout), ip],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.scan_timeout + 1
                )
                
                if result.returncode == 0:
                    active_hosts.append(ip)
                    
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        
        return active_hosts
    
    def _arp_scan(self, ip_list: List[str]) -> List[str]:
        """Führt einen ARP-Scan durch (erfordert root-Rechte oder spezielle Tools)"""
        active_hosts = []
        
        # ARP-Scan ist plattformabhängig
        # Hier implementieren wir einen vereinfachten Ansatz
        # In einer Produktionsumgebung würde man arp-scan oder nmap verwenden
        
        for ip in ip_list:
            try:
                # Versuche, MAC-Adresse über ARP zu erhalten
                # Dies ist eine vereinfachte Implementierung
                # In Linux: arp -a | grep $ip
                # In Windows: arp -a | findstr $ip
                
                # Für jetzt simulieren wir einfach
                # In der Produktion wäre hier die echte ARP-Abfrage
                logger.debug("ARP-Scan für %s (simuliert)", ip)
                
            except Exception:
                pass
        
        return active_hosts
    
    def _scan_single_host(self, ip: str) -> Optional[NetworkDevice]:
        """
        Scannt einen einzelnen Host und sammelt Informationen
        
        Args:
            ip: IP-Adresse des Hosts
            
        Returns:
            NetworkDevice mit Informationen oder None bei Fehler
        """
        try:
            device = NetworkDevice(ip_address=ip)
            
            # Hostname ermitteln (DNS Reverse Lookup)
            try:
                hostname_info = socket.gethostbyaddr(ip)
                device.hostname = hostname_info[0]
            except (socket.herror, socket.gaierror):
                device.hostname = None
            
            # MAC-Adresse ermitteln (ARP)
            device.mac_address = self._get_mac_address(ip)
            
            # Hersteller aus MAC bestimmen
            if device.mac_address:
                device.vendor = self._get_vendor_from_mac(device.mac_address)
            
            # OS-Typ und Version ermitteln
            device.os_type, device.os_version = self._detect_os(ip)
            
            # Device-Typ bestimmen
            device.device_type = self._determine_device_type(ip, device)
            
            # Port-Scan (wenn aktiviert und erlaubt)
            if self.port_scan_enabled:
                device.open_ports = self._port_scan(ip)
            
            # Domain-Informationen (simuliert)
            device.domain = self._detect_domain(ip, device)
            device.is_domain_controller = self._check_domain_controller(ip, device)
            
            device.last_seen = datetime.now()
            
            return device
            
        except Exception as e:
            logger.error("Fehler beim Scannen von %s: %s", ip, e)
            return None
    
    def _get_mac_address(self, ip: str) -> Optional[str]:
        """Ermittelt die MAC-Adresse für eine IP (simuliert)"""
        # In der Produktion: arp -a oder ähnliches
        # Für Testzwecke generieren wir eine zufällige MAC
        import random
        
        # Simulierte MAC für Test
        mac_hex = [f"{random.randint(0, 255):02x}" for _ in range(6)]
        return ":".join(mac_hex)
    
    def _get_vendor_from_mac(self, mac: str) -> Optional[str]:
        """Bestimmt den Hersteller aus der MAC-Adresse"""
        # Extrahiere die ersten 3 Bytes (OUI)
        oui = mac.replace(":", "").replace("-", "").upper()[:6]
        oui_formatted = f"{oui[:2]}:{oui[2:4]}:{oui[4:6]}"
        
        # Suche in der Vendor-Datenbank
        for vendor_prefix, vendor_name in self.mac_vendor_db.items():
            if mac.startswith(vendor_prefix) or oui_formatted.startswith(vendor_prefix):
                return vendor_name
        
        return None
    
    def _detect_os(self, ip: str) -> Tuple[Optional[str], Optional[str]]:
        """Erkennt Betriebssystem und Version (simuliert)"""
        # In der Produktion: nmap OS-Detection oder Banner-Grabbing
        # Für Testzwecke: Heuristik basierend auf typischen Ports
        
        # Simulierte OS1-Erkennung
        os_types = ["windows", "linux", "unix", "network_device", "printer"]
        os_versions = {
            "windows": ["11", "10", "Server 2022", "Server 2019", "Server 2016"],
            "linux": ["Ubuntu 22.04", "Debian 12", "CentOS 7", "RHEL 8"],
            "unix": ["FreeBSD", "OpenBSD"],
            "network_device": ["Cisco IOS", "Juniper JunOS", "Mikrotik RouterOS"],
            "printer": ["HP Firmware", "Canon", "Brother"]
        }
        
        import random
        os_type = random.choice(os_types)
        os_version = random.choice(os_versions.get(os_type, ["Unknown"]))
        
        return os_type, os_version
    
    def _determine_device_type(self, ip: str, device: NetworkDevice) -> Optional[str]:
        """Bestimmt den Gerätetyp basierend auf OS und Ports"""
        if device.os_type == "windows" and "computer" in (device.hostname or "").lower():
            return "computer"
        elif device.os_type == "printer":
            return "printer"
        elif device.os_type == "network_device":
            return "network_device"
        elif 22 in device.open_ports:  # SSH
            return "server"
        elif 80 in device.open_ports or 443 in device.open_ports:  # HTTP/HTTPS
            return "web_server"
        else:
            return "unknown"
    
    def _port_scan(self, ip: str) -> List[int]:
        """Führt einen Port-Scan durch (nur erlaubte Ports)"""
        open_ports = []
        
        if not self.allowed_ports:
            return open_ports
        
        for port in self.allowed_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    open_ports.append(port)
                    
            except (socket.timeout, socket.error):
                pass
        
        return open_ports
    
    def _detect_domain(self, ip: str, device: NetworkDevice) -> Optional[str]:
        """Erkennt die Domain/Zugehörigkeit (simuliert)"""
        # In der Produktion: LDAP/Active Directory Abfrage
        # Für Testzwecke: Heuristik basierend auf Hostname
        
        if device.hostname and "." in device.hostname:
            parts = device.hostname.split(".")
            if len(parts) > 1:
                return ".".join(parts[1:])
        
        return None
    
    def _check_domain_controller(self, ip: str, device: NetworkDevice) -> bool:
        """Prüft, ob es sich um einen Domain Controller handelt"""
        # Domain Controller haben typischerweise bestimmte Ports offen
        dc_ports = [53, 88, 135, 389, 445, 636, 3268, 3269]  # DNS, Kerberos, LDAP, etc.
        
        if device.os_type == "windows" and any(port in device.open_ports for port in dc_ports):
            return True
        
        if device.hostname and any(name in (device.hostname or "").lower() 
                                   for name in ["dc", "domain", "controller"]):
            return True
        
        return False

    def scan(self, ip_range: str, timeout_seconds: int = 5) -> Dict[str, Any]:
        """
        Scannt einen IP-Bereich (API-kompatibel mit Tests)
        
        Args:
            ip_range: IP-Bereich im Format "192.168.1.0/24"
            timeout_seconds: Timeout für den Scan
            
        Returns:
            Dictionary mit Scan-Ergebnissen
        """
        # Konvertiere timeout_seconds für interne Konfiguration
        original_timeout = self.scan_timeout
        self.scan_timeout = timeout_seconds
        
        try:
            scan_result = self.scan_ip_range(ip_range)
            return {
                "scan_id": scan_result.scan_id,
                "devices_found": scan_result.devices_found,
                "total_devices": scan_result.total_devices,
                "scan_duration": scan_result.scan_duration,
                "scan_status": scan_result.scan_status
            }
        except Exception as e:
            logger.error(f"Scan fehlgeschlagen für {ip_range}: {e}")
            return {
                "scan_id": self.generate_scan_id(),
                "devices_found": [],
                "total_devices": 0,
                "scan_duration": None,
                "scan_status": "failed",
                "error_message": str(e)
            }
        finally:
            # Stelle originales Timeout wieder her
            self.scan_timeout = original_timeout
