"""
Active Directory / LDAP Connector für Phase 2

Erkennt Domänencomputer, Benutzer, Gruppen und Domain Controller in Windows Active Directory Umgebungen.
"""

import logging
import ssl
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
import warnings

# Optional: LDAP3 Bibliothek, falls installiert
try:
    import ldap3
    LDAP3_AVAILABLE = True
except ImportError:
    LDAP3_AVAILABLE = False
    warnings.warn("ldap3 nicht installiert. LDAP-Funktionen sind eingeschränkt.")

logger = logging.getLogger(__name__)


@dataclass
class ADComputer:
    """Repräsentiert einen Computer aus Active Directory"""
    computer_name: str
    distinguished_name: Optional[str] = None
    sam_account_name: Optional[str] = None  # z.B. COMPUTERNAME$
    dns_hostname: Optional[str] = None
    operating_system: Optional[str] = None
    operating_system_version: Optional[str] = None
    last_logon_timestamp: Optional[datetime] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    location: Optional[str] = None
    department: Optional[str] = None
    managed_by: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    is_enabled: bool = True
    is_domain_controller: bool = False
    groups: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert den Computer in ein Dictionary"""
        return {
            "computer_name": self.computer_name,
            "distinguished_name": self.distinguished_name,
            "sam_account_name": self.sam_account_name,
            "dns_hostname": self.dns_hostname,
            "operating_system": self.operating_system,
            "operating_system_version": self.operating_system_version,
            "last_logon_timestamp": self.last_logon_timestamp.isoformat() if self.last_logon_timestamp else None,
            "created": self.created.isoformat() if self.created else None,
            "modified": self.modified.isoformat() if self.modified else None,
            "location": self.location,
            "department": self.department,
            "managed_by": self.managed_by,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "is_enabled": self.is_enabled,
            "is_domain_controller": self.is_domain_controller,
            "groups": self.groups
        }


@dataclass
class ADUser:
    """Repräsentiert einen Benutzer aus Active Directory"""
    username: str
    distinguished_name: Optional[str] = None
    sam_account_name: Optional[str] = None
    display_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    manager: Optional[str] = None
    telephone: Optional[str] = None
    mobile: Optional[str] = None
    office: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    last_logon: Optional[datetime] = None
    is_enabled: bool = True
    groups: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert den Benutzer in ein Dictionary"""
        return {
            "username": self.username,
            "distinguished_name": self.distinguished_name,
            "sam_account_name": self.sam_account_name,
            "display_name": self.display_name,
            "given_name": self.given_name,
            "surname": self.surname,
            "email": self.email,
            "department": self.department,
            "title": self.title,
            "company": self.company,
            "manager": self.manager,
            "telephone": self.telephone,
            "mobile": self.mobile,
            "office": self.office,
            "created": self.created.isoformat() if self.created else None,
            "modified": self.modified.isoformat() if self.modified else None,
            "last_logon": self.last_logon.isoformat() if self.last_logon else None,
            "is_enabled": self.is_enabled,
            "groups": self.groups
        }


@dataclass
class ADGroup:
    """Repräsentiert eine Gruppe aus Active Directory"""
    group_name: str
    distinguished_name: Optional[str] = None
    sam_account_name: Optional[str] = None
    description: Optional[str] = None
    group_type: Optional[str] = None  # Security, Distribution
    scope: Optional[str] = None  # Global, Universal, DomainLocal
    members: List[str] = field(default_factory=list)  # DN von Mitgliedern
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Gruppe in ein Dictionary"""
        return {
            "group_name": self.group_name,
            "distinguished_name": self.distinguished_name,
            "sam_account_name": self.sam_account_name,
            "description": self.description,
            "group_type": self.group_type,
            "scope": self.scope,
            "members": self.members,
            "created": self.created.isoformat() if self.created else None,
            "modified": self.modified.isoformat() if self.modified else None
        }


class ActiveDirectoryConnector:
    """
    Connector für Active Directory und LDAP-Verbindungen
    
    Fähigkeiten:
    - Verbindung zu AD/LDAP-Servern
    - Abfrage von Computern, Benutzern, Gruppen
    - Erkennung von Domain Controllern
    - Synchronisation mit Netzwerk-Scan-Ergebnissen
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den AD-Connector
        
        Args:
            config: Konfigurationsdictionary mit:
                - server_url: LDAP/AD Server URL (z.B. ldap://domain.local)
                - bind_dn: Bind DN für Authentifizierung
                - bind_password: Passwort für Authentifizierung
                - base_dn: Basis DN für Suchoperationen
                - use_ssl: SSL/TLS verwenden (default: True)
                - use_tls: STARTTLS verwenden (default: False)
                - verify_ssl: SSL-Zertifikat prüfen (default: True)
                - timeout: Timeout für Verbindungen in Sekunden (default: 10)
                - page_size: Größe für paginierte Suchen (default: 1000)
        """
        self.config = config
        self.server_url = config.get("server_url")
        self.bind_dn = config.get("bind_dn")
        self.bind_password = config.get("bind_password")
        self.base_dn = config.get("base_dn", "")
        self.use_ssl = config.get("use_ssl", True)
        self.use_tls = config.get("use_tls", False)
        self.verify_ssl = config.get("verify_ssl", True)
        self.timeout = config.get("timeout", 10)
        self.page_size = config.get("page_size", 1000)
        
        self.connection = None
        
        logger.info("ActiveDirectoryConnector initialisiert für Server: %s", self.server_url)
    
    def connect(self) -> bool:
        """Stellt eine Verbindung zum AD/LDAP-Server her"""
        if not LDAP3_AVAILABLE:
            logger.warning("ldap3 nicht installiert, Verbindung simuliert")
            return True
        
        try:
            server = ldap3.Server(
                self.server_url,
                use_ssl=self.use_ssl,
                use_tls=self.use_tls,
                get_info=ldap3.ALL
            )
            
            self.connection = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_password,
                auto_bind=True,
                authentication=ldap3.NTLM if '\\' in (self.bind_dn or '') else ldap3.SIMPLE,
                receive_timeout=self.timeout
            )
            
            if self.connection.bound:
                logger.info("Erfolgreich mit AD/LDAP-Server verbunden: %s", self.server_url)
                return True
            else:
                logger.error("Verbindung zum AD/LDAP-Server fehlgeschlagen")
                return False
                
        except Exception as e:
            logger.error("Fehler bei AD/LDAP-Verbindung: %s", e)
            return False
    
    def disconnect(self):
        """Trennt die Verbindung zum AD/LDAP-Server"""
        if self.connection and LDAP3_AVAILABLE:
            try:
                self.connection.unbind()
                logger.info("AD/LDAP-Verbindung getrennt")
            except Exception as e:
                logger.warning("Fehler beim Trennen der Verbindung: %s", e)
        
        self.connection = None
    
    def get_computers(self, filter_string: Optional[str] = None) -> List[ADComputer]:
        """
        Holt alle Computer aus Active Directory
        
        Args:
            filter_string: Optionaler LDAP-Filter (default: (objectClass=computer))
            
        Returns:
            Liste von ADComputer-Objekten
        """
        if not LDAP3_AVAILABLE:
            logger.warning("ldap3 nicht installiert, simuliere Computer")
            return self._simulate_computers()
        
        if not self.connection or not self.connection.bound:
            if not self.connect():
                return []
        
        default_filter = "(objectClass=computer)"
        search_filter = filter_string or default_filter
        
        try:
            search_base = self.base_dn or self._get_default_base_dn()
            attributes = [
                'cn', 'distinguishedName', 'sAMAccountName', 'dNSHostName',
                'operatingSystem', 'operatingSystemVersion', 'lastLogonTimestamp',
                'whenCreated', 'whenChanged', 'location', 'department',
                'managedBy', 'ipAddress', 'macAddress', 'userAccountControl',
                'primaryGroupID', 'memberOf'
            ]
            
            self.connection.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=ldap3.SUBTREE,
                attributes=attributes,
                paged_size=self.page_size
            )
            
            computers = []
            for entry in self.connection.entries:
                computer = self._entry_to_ad_computer(entry)
                computers.append(computer)
            
            logger.info("%d Computer aus AD gelesen", len(computers))
            return computers
            
        except Exception as e:
            logger.error("Fehler beim Abrufen von Computern: %s", e)
            return []
    
    def get_domain_controllers(self) -> List[ADComputer]:
        """Holt alle Domain Controller aus Active Directory"""
        dc_filter = "(&(objectClass=computer)(userAccountControl:1.2.840.113556.1.4.803:=8192))"
        computers = self.get_computers(dc_filter)
        
        # Markiere alle als Domain Controller
        for computer in computers:
            computer.is_domain_controller = True
        
        logger.info("%d Domain Controller gefunden", len(computers))
        return computers
    
    def get_users(self, filter_string: Optional[str] = None) -> List[ADUser]:
        """
        Holt alle Benutzer aus Active Directory
        
        Args:
            filter_string: Optionaler LDAP-Filter (default: (objectClass=user))
            
        Returns:
            Liste von ADUser-Objekten
        """
        if not LDAP3_AVAILABLE:
            logger.warning("ldap3 nicht installiert, simuliere Benutzer")
            return self._simulate_users()
        
        if not self.connection or not self.connection.bound:
            if not self.connect():
                return []
        
        default_filter = "(&(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
        search_filter = filter_string or default_filter
        
        try:
            search_base = self.base_dn or self._get_default_base_dn()
            attributes = [
                'cn', 'distinguishedName', 'sAMAccountName', 'displayName',
                'givenName', 'sn', 'mail', 'department', 'title', 'company',
                'manager', 'telephoneNumber', 'mobile', 'physicalDeliveryOfficeName',
                'whenCreated', 'whenChanged', 'lastLogon', 'userAccountControl',
                'memberOf'
            ]
            
            self.connection.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=ldap3.SUBTREE,
                attributes=attributes,
                paged_size=self.page_size
            )
            
            users = []
            for entry in self.connection.entries:
                user = self._entry_to_ad_user(entry)
                users.append(user)
            
            logger.info("%d Benutzer aus AD gelesen", len(users))
            return users
            
        except Exception as e:
            logger.error("Fehler beim Abrufen von Benutzern: %s", e)
            return []
    
    def get_groups(self, filter_string: Optional[str] = None) -> List[ADGroup]:
        """
        Holt alle Gruppen aus Active Directory
        
        Args:
            filter_string: Optionaler LDAP-Filter (default: (objectClass=group))
            
        Returns:
            Liste von ADGroup-Objekten
        """
        if not LDAP3_AVAILABLE:
            logger.warning("ldap3 nicht installiert, simuliere Gruppen")
            return self._simulate_groups()
        
        if not self.connection or not self.connection.bound:
            if not self.connect():
                return []
        
        default_filter = "(objectClass=group)"
        search_filter = filter_string or default_filter
        
        try:
            search_base = self.base_dn or self._get_default_base_dn()
            attributes = [
                'cn', 'distinguishedName', 'sAMAccountName', 'description',
                'groupType', 'member'
            ]
            
            self.connection.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=ldap3.SUBTREE,
                attributes=attributes,
                paged_size=self.page_size
            )
            
            groups = []
            for entry in self.connection.entries:
                group = self._entry_to_ad_group(entry)
                groups.append(group)
            
            logger.info("%d Gruppen aus AD gelesen", len(groups))
            return groups
            
        except Exception as e:
            logger.error("Fehler beim Abrufen von Gruppen: %s", e)
            return []
    
    def _get_default_base_dn(self) -> str:
        """Erzeugt einen default Base DN aus der Server URL"""
        if not self.server_url:
            return ""
        
        # Extrahiere Domain aus URL
        domain_part = self.server_url.replace('ldap://', '').replace('ldaps://', '').split(':')[0]
        
        # Konvertiere domain.local zu DC=domain,DC=local
        parts = domain_part.split('.')
        dn_parts = [f"DC={part}" for part in parts]
        
        return ','.join(dn_parts)
    
    def _entry_to_ad_computer(self, entry) -> ADComputer:
        """Konvertiert einen LDAP-Eintrag in ein ADComputer-Objekt"""
        computer = ADComputer(
            computer_name=str(entry.cn) if entry.cn else "",
            distinguished_name=str(entry.distinguishedName) if entry.distinguishedName else None,
            sam_account_name=str(entry.sAMAccountName) if entry.sAMAccountName else None,
            dns_hostname=str(entry.dNSHostName) if entry.dNSHostName else None,
            operating_system=str(entry.operatingSystem) if entry.operatingSystem else None,
            operating_system_version=str(entry.operatingSystemVersion) if entry.operatingSystemVersion else None,
            location=str(entry.location) if entry.location else None,
            department=str(entry.department) if entry.department else None,
            managed_by=str(entry.managedBy) if entry.managedBy else None,
            ip_address=str(entry.ipAddress) if entry.ipAddress else None,
            mac_address=str(entry.macAddress) if entry.macAddress else None
        )
        
        # Parse Timestamps
        if entry.lastLogonTimestamp:
            try:
                # AD Timestamp: 100-nanosekunden-Intervalle seit 1.1.1601
                ad_timestamp = int(str(entry.lastLogonTimestamp))
                unix_timestamp = (ad_timestamp / 10000000) - 11644473600
                computer.last_logon_timestamp = datetime.fromtimestamp(unix_timestamp)
            except (ValueError, TypeError):
                pass
        
        if entry.whenCreated:
            try:
                computer.created = datetime.strptime(str(entry.whenCreated), '%Y%m%d%H%M%S.%fZ')
            except ValueError:
                pass
        
        if entry.whenChanged:
            try:
                computer.modified = datetime.strptime(str(entry.whenChanged), '%Y%m%d%H%M%S.%fZ')
            except ValueError:
                pass
        
        # UserAccountControl: 2 = disabled, 8192 = domain controller
        if entry.userAccountControl:
            try:
                uac = int(str(entry.userAccountControl))
                computer.is_enabled = not bool(uac & 2)  # Bit 1 = ACCOUNTDISABLE
                computer.is_domain_controller = bool(uac & 8192)  # Bit 13 = SERVER_TRUST_ACCOUNT
            except (ValueError, TypeError):
                pass
        
        # Gruppen-Mitgliedschaften
        if entry.memberOf:
            computer.groups = [str(group) for group in entry.memberOf]
        
        return computer
    
    def _entry_to_ad_user(self, entry) -> ADUser:
        """Konvertiert einen LDAP-Eintrag in ein ADUser-Objekt"""
        user = ADUser(
            username=str(entry.cn) if entry.cn else "",
            distinguished_name=str(entry.distinguishedName) if entry.distinguishedName else None,
            sam_account_name=str(entry.sAMAccountName) if entry.sAMAccountName else None,
            display_name=str(entry.displayName) if entry.displayName else None,
            given_name=str(entry.givenName) if entry.givenName else None,
            surname=str(entry.sn) if entry.sn else None,
            email=str(entry.mail) if entry.mail else None,
            department=str(entry.department) if entry.department else None,
            title=str(entry.title) if entry.title else None,
            company=str(entry.company) if entry.company else None,
            manager=str(entry.manager) if entry.manager else None,
            telephone=str(entry.telephoneNumber) if entry.telephoneNumber else None,
            mobile=str(entry.mobile) if entry.mobile else None,
            office=str(entry.physicalDeliveryOfficeName) if entry.physicalDeliveryOfficeName else None
        )
        
        # Parse Timestamps
        if entry.whenCreated:
            try:
                user.created = datetime.strptime(str(entry.whenCreated), '%Y%m%d%H%M%S.%fZ')
            except ValueError:
                pass
        
        if entry.whenChanged:
            try:
                user.modified = datetime.strptime(str(entry.whenChanged), '%Y%m%d%H%M%S.%fZ')
            except ValueError:
                pass
        
        if entry.lastLogon:
            try:
                ad_timestamp = int(str(entry.lastLogon))
                unix_timestamp = (ad_timestamp / 10000000) - 11644473600
                user.last_logon = datetime.fromtimestamp(unix_timestamp)
            except (ValueError, TypeError):
                pass
        
        # UserAccountControl: 2 = disabled
        if entry.userAccountControl:
            try:
                uac = int(str(entry.userAccountControl))
                user.is_enabled = not bool(uac & 2)  # Bit 1 = ACCOUNTDISABLE
            except (ValueError, TypeError):
                pass
        
        # Gruppen-Mitgliedschaften
        if entry.memberOf:
            user.groups = [str(group) for group in entry.memberOf]
        
        return user
    
    def _entry_to_ad_group(self, entry) -> ADGroup:
        """Konvertiert einen LDAP-Eintrag in ein ADGroup-Objekt"""
        group = ADGroup(
            group_name=str(entry.cn) if entry.cn else "",
            distinguished_name=str(entry.distinguishedName) if entry.distinguishedName else None,
            sam_account_name=str(entry.sAMAccountName) if entry.sAMAccountName else None,
            description=str(entry.description) if entry.description else None
        )
        
        # GroupType: 2 = Global, 4 = DomainLocal, 8 = Universal
        if entry.groupType:
            try:
                group_type = int(str(entry.groupType))
                
                if group_type & 2:
                    group.scope = "Global"
                elif group_type & 4:
                    group.scope = "DomainLocal"
                elif group_type & 8:
                    group.scope = "Universal"
                
                # Security Group (BIT 31 = 0) oder Distribution Group (BIT 31 = 1)
                group.group_type = "Security" if not (group_type & 0x80000000) else "Distribution"
            except (ValueError, TypeError):
                pass
        
        # Mitglieder
        if entry.member:
            group.members = [str(member) for member in entry.member]
        
        return group
    
    def _simulate_computers(self) -> List[ADComputer]:
        """Simuliert Computer für Testzwecke (falls ldap3 nicht verfügbar)"""
        import random
        
        computers = []
        computer_names = [
            "PC-MUSTER-001", "PC-MUSTER-002", "PC-MUSTER-003",
            "WS-MUSTER-001", "WS-MUSTER-002", "LAPTOP-MUSTER-001",
            "DC-MUSTER-01", "DC-MUSTER-02", "FS-MUSTER-01",
            "PRINT-MUSTER-01", "NAS-MUSTER-01"
        ]
        
        for name in computer_names:
            computer = ADComputer(
                computer_name=name,
                sam_account_name=f"{name}$",
                dns_hostname=f"{name.lower()}.muster.local",
                operating_system="Windows 10" if "PC" in name else "Windows Server 2022" if "DC" in name else "Ubuntu 22.04" if "NAS" in name else "Windows 11",
                operating_system_version="10.0.19045" if "PC" in name else "10.0.20348" if "DC" in name else "22.04",
                location="Hauptgebäude, EG, Raum 101",
                department="IT" if "DC" in name or "NAS" in name else "Vertrieb" if "PC" in name else "Produktion",
                ip_address=f"192.168.1.{random.randint(100, 200)}",
                mac_address=f"{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:"
                           f"{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:{random.randint(0, 255):02x}",
                is_enabled=random.random() > 0.1,  # 90% enabled
                is_domain_controller="DC" in name,
                groups=["Domain Computers", "Workstation Admins"] if "PC" in name else ["Domain Controllers"]
            )
            computers.append(computer)
        
        return computers
    
    def _simulate_users(self) -> List[ADUser]:
        """Simuliert Benutzer für Testzwecke (falls ldap3 nicht verfügbar)"""
        import random
        
        users = []
        user_data = [
            {"username": "mmuster", "display_name": "Max Mustermann", "department": "IT", "title": "IT-Leiter"},
            {"username": "eexample", "display_name": "Erika Beispiel", "department": "Vertrieb", "title": "Vertriebsleiterin"},
            {"username": "jtechie", "display_name": "John Techniker", "department": "IT", "title": "Systemadministrator"},
            {"username": "aadmin", "display_name": "Admin Admin", "department": "IT", "title": "Domain Administrator"},
            {"username": "uuser", "display_name": "User User", "department": "Produktion", "title": "Mitarbeiter"}
        ]
        
        for data in user_data:
            user = ADUser(
                username=data["username"],
                display_name=data["display_name"],
                email=f"{data['username']}@muster.local",
                department=data["department"],
                title=data["title"],
                company="Muster GmbH",
                telephone=f"+49 1234 567{random.randint(100, 999)}",
                mobile=f"+49 176 1234{random.randint(1000, 9999)}",
                office="Hauptgebäude, 2. OG",
                is_enabled=True,
                groups=["Domain Users", f"{data['department']} Department"]
            )
            users.append(user)
        
        return users
    
    def _simulate_groups(self) -> List[ADGroup]:
        """Simuliert Gruppen für Testzwecke (falls ldap3 nicht verfügbar)"""
        groups = [
            ADGroup(
                group_name="Domain Admins",
                description="Administratoren der Domain",
                group_type="Security",
                scope="Global",
                members=["CN=Admin Admin,OU=Admins,DC=muster,DC=local"]
            ),
            ADGroup(
                group_name="Domain Users",
                description="Alle Benutzer der Domain",
                group_type="Security",
                scope="Global",
                members=["CN=Max Mustermann,OU=Users,DC=muster,DC=local", 
                        "CN=Erika Beispiel,OU=Users,DC=muster,DC=local"]
            ),
            ADGroup(
                group_name="IT Department",
                description="Mitarbeiter der IT-Abteilung",
                group_type="Security",
                scope="Global",
                members=["CN=Max Mustermann,OU=Users,DC=muster,DC=local",
                        "CN=John Techniker,OU=Users,DC=muster,DC=local"]
            ),
            ADGroup(
                group_name="Workstation Admins",
                description="Administratoren für Workstations",
                group_type="Security",
                scope="DomainLocal",
                members=["CN=John Techniker,OU=Users,DC=muster,DC=local"]
            )
        ]
        
        return groups
    
    def sync_with_network_devices(self, network_devices: List[Dict]) -> Dict[str, Any]:
        """
        Synchronisiert AD-Computer mit Netzwerk-Scan-Ergebnissen
        
        Args:
            network_devices: Liste von Netzwerkgeräten aus dem Scanner
            
        Returns:
            Dictionary mit Synchronisationsergebnissen
        """
        ad_computers = self.get_computers()
        sync_results = {
            "matched_devices": [],
            "unmatched_network_devices": [],
            "unmatched_ad_computers": [],
            "conflicts": []
        }
        
        # Erstelle Mapping von Hostnamen zu AD-Computern
        ad_by_hostname = {}
        for ad_computer in ad_computers:
            if ad_computer.dns_hostname:
                hostname = ad_computer.dns_hostname.lower()
                ad_by_hostname[hostname] = ad_computer
            if ad_computer.computer_name:
                name = ad_computer.computer_name.lower()
                ad_by_hostname[name] = ad_computer
        
        # Vergleiche Netzwerkgeräte mit AD-Computern
        for device in network_devices:
            device_hostname = (device.get("hostname") or "").lower()
            device_ip = device.get("ip_address")
            
            matched = False
            
            # Match über Hostname
            if device_hostname and device_hostname in ad_by_hostname:
                ad_computer = ad_by_hostname[device_hostname]
                sync_results["matched_devices"].append({
                    "network_device": device,
                    "ad_computer": ad_computer.to_dict(),
                    "match_type": "hostname"
                })
                matched = True
            
            # Match über IP (falls AD Computer IP hat)
            if not matched and device_ip:
                for ad_computer in ad_computers:
                    if ad_computer.ip_address == device_ip:
                        sync_results["matched_devices"].append({
                            "network_device": device,
                            "ad_computer": ad_computer.to_dict(),
                            "match_type": "ip_address"
                        })
                        matched = True
                        break
            
            if not matched:
                sync_results["unmatched_network_devices"].append(device)
        
        # Finde AD-Computer ohne Netzwerkgerät
        for ad_computer in ad_computers:
            found = False
            for match in sync_results["matched_devices"]:
                if match["ad_computer"]["computer_name"] == ad_computer.computer_name:
                    found = True
                    break
            
            if not found:
                sync_results["unmatched_ad_computers"].append(ad_computer.to_dict())
        
        logger.info("AD-Netzwerk-Sync abgeschlossen: %d Matches, %d unmatche Netzwerk, %d unmatche AD",
                   len(sync_results["matched_devices"]),
                   len(sync_results["unmatched_network_devices"]),
                   len(sync_results["unmatched_ad_computers"]))
        
        return sync_results