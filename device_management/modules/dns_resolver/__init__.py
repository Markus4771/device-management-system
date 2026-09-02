"""
DNS-Resolver für Phase 2

DNS-Auflösung und Reverse-DNS für Netzwerk-Scans.
Unterstützt verschiedene DNS-Server, Zonen-Transfers,
DNS-Einträge analysieren und Hostname-Resolution.
"""

import logging
import socket
import dns.resolver
import dns.reversename
import dns.zone
import dns.query
import dns.exception
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import ipaddress
import re

logger = logging.getLogger(__name__)


class DNSError(Exception):
    """DNS-spezifische Fehler"""
    pass


@dataclass
class DNSRecord:
    """DNS-Eintrag"""
    name: str
    record_type: str  # "A", "AAAA", "CNAME", "MX", "NS", "PTR", "SRV", "TXT"
    value: str
    ttl: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert den DNS-Eintrag in ein Dictionary"""
        return {
            "name": self.name,
            "record_type": self.record_type,
            "value": self.value,
            "ttl": self.ttl,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class DNSZone:
    """DNS-Zone"""
    zone_name: str
    records: List[DNSRecord] = field(default_factory=list)
    nameservers: List[str] = field(default_factory=list)
    serial: Optional[int] = None
    refresh: Optional[int] = None
    retry: Optional[int] = None
    expire: Optional[int] = None
    minimum_ttl: Optional[int] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die DNS-Zone in ein Dictionary"""
        return {
            "zone_name": self.zone_name,
            "records": [record.to_dict() for record in self.records],
            "nameservers": self.nameservers,
            "serial": self.serial,
            "refresh": self.refresh,
            "retry": self.retry,
            "expire": self.expire,
            "minimum_ttl": self.minimum_ttl,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class DNSResolutionResult:
    """DNS-Auflösungsergebnis"""
    query: str
    query_type: str
    answers: List[DNSRecord]
    authoritative: bool = False
    nameserver: Optional[str] = None
    response_time_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Ergebnis in ein Dictionary"""
        return {
            "query": self.query,
            "query_type": self.query_type,
            "answers": [answer.to_dict() for answer in self.answers],
            "authoritative": self.authoritative,
            "nameserver": self.nameserver,
            "response_time_ms": self.response_time_ms,
            "timestamp": self.timestamp.isoformat()
        }


class DNSResolver:
    """
    DNS-Resolver für Netzwerk-Scans.
    
    Fähigkeiten:
    - Vorwärts- und Rückwärts-DNS-Auflösung
    - Unterstützung für mehrere DNS-Server
    - Zonen-Transfer (AXFR/IXFR)
    - DNS-Eintrag-Analyse
    - Cache für wiederholte Anfragen
    - Zeitmessung und Statistiken
    - Unterstützung für DNSSEC (optional)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den DNS-Resolver
        
        Args:
            config: Konfigurationsdictionary mit:
                - dns_servers: Liste von DNS-Servern (IP:Port)
                - timeout_seconds: Timeout für DNS-Anfragen
                - enable_dnssec: DNSSEC-Unterstützung aktivieren
                - use_cache: Cache für DNS-Anfragen verwenden
                - cache_ttl_seconds: TTL für Cache-Einträge
                - enable_zone_transfer: Zonen-Transfer erlauben (mit Berechtigung)
        """
        self.config = config
        
        # DNS-Server Liste
        self.dns_servers = config.get("dns_servers", ["8.8.8.8", "8.8.4.4"])
        
        # Cache für DNS-Anfragen
        self.cache_enabled = config.get("use_cache", True)
        self.cache: Dict[str, Tuple[DNSResolutionResult, datetime]] = {}
        self.cache_ttl = config.get("cache_ttl_seconds", 300)
        
        # Statistiken
        self.stats = {
            "queries_total": 0,
            "queries_successful": 0,
            "queries_failed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "zone_transfers": 0,
            "response_time_avg_ms": 0
        }
        
        logger.info(f"DNS-Resolver initialisiert mit {len(self.dns_servers)} DNS-Servern")
    
    async def resolve_hostname(self, hostname: str, record_type: str = "A") -> DNSResolutionResult:
        """
        Löst einen Hostnamen auf
        
        Args:
            hostname: Zu auflösender Hostname
            record_type: DNS-Eintragstyp (A, AAAA, CNAME, MX, etc.)
            
        Returns:
            DNS-Auflösungsergebnis
        """
        self.stats["queries_total"] += 1
        
        # Prüfe Cache
        cache_key = f"{hostname}:{record_type}"
        if self.cache_enabled and cache_key in self.cache:
            cached_result, cached_time = self.cache[cache_key]
            age = (datetime.now() - cached_time).total_seconds()
            
            if age < self.cache_ttl:
                self.stats["cache_hits"] += 1
                logger.debug(f"Cache-Treffer für {hostname} ({record_type})")
                return cached_result
        
        self.stats["cache_misses"] += 1
        
        # Resolver für asynchrone Anfragen vorbereiten
        resolver = dns.asyncresolver.Resolver()
        resolver.nameservers = self._parse_dns_servers()
        resolver.timeout = self.config.get("timeout_seconds", 5)
        resolver.lifetime = self.config.get("timeout_seconds", 5)
        
        if self.config.get("enable_dnssec", False):
            # DNSSEC-Unterstützung aktivieren
            pass
        
        try:
            start_time = datetime.now()
            
            # DNS-Anfrage
            if record_type == "A":
                answers = await resolver.resolve(hostname, "A")
            elif record_type == "AAAA":
                answers = await resolver.resolve(hostname, "AAAA")
            elif record_type == "CNAME":
                answers = await resolver.resolve(hostname, "CNAME")
            elif record_type == "MX":
                answers = await resolver.resolve(hostname, "MX")
            elif record_type == "NS":
                answers = await resolver.resolve(hostname, "NS")
            elif record_type == "PTR":
                answers = await resolver.resolve(hostname, "PTR")
            elif record_type == "TXT":
                answers = await resolver.resolve(hostname, "TXT")
            elif record_type == "SOA":
                answers = await resolver.resolve(hostname, "SOA")
            elif record_type == "SRV":
                answers = await resolver.resolve(hostname, "SRV")
            else:
                raise DNSError(f"Unbekannter DNS-Eintragstyp: {record_type}")
            
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            # Antwort parsen
            dns_records = []
            for answer in answers:
                dns_record = DNSRecord(
                    name=hostname,
                    record_type=record_type,
                    value=str(answer),
                    ttl=answer.ttl if hasattr(answer, 'ttl') else None
                )
                dns_records.append(dns_record)
            
            # Ergebnis erstellen
            result = DNSResolutionResult(
                query=hostname,
                query_type=record_type,
                answers=dns_records,
                authoritative=answers.response.is_authoritative(),
                nameserver=answers.nameserver if hasattr(answers, 'nameserver') else None,
                response_time_ms=response_time
            )
            
            # In Cache speichern
            if self.cache_enabled:
                self.cache[cache_key] = (result, datetime.now())
            
            self.stats["queries_successful"] += 1
            self._update_stats(response_time)
            
            logger.debug(f"DNS-Auflösung erfolgreich: {hostname} -> {len(dns_records)} Einträge")
            return result
            
        except dns.exception.DNSException as e:
            self.stats["queries_failed"] += 1
            logger.warning(f"DNS-Auflösung fehlgeschlagen für {hostname} ({record_type}): {e}")
            
            # Leeres Ergebnis zurückgeben
            return DNSResolutionResult(
                query=hostname,
                query_type=record_type,
                answers=[],
                authoritative=False,
                response_time_ms=None
            )
    
    async def reverse_dns_lookup(self, ip_address: str) -> DNSResolutionResult:
        """
        Führt Reverse-DNS-Lookup durch
        
        Args:
            ip_address: IP-Adresse für Reverse-Lookup
            
        Returns:
            DNS-Auflösungsergebnis mit PTR-Einträgen
        """
        try:
            # IP-Adresse überprüfen
            ip_obj = ipaddress.ip_address(ip_address)
            
            # Reverse-DNS-Name generieren
            if ip_obj.version == 4:
                # IPv4: 1.2.3.4 -> 4.3.2.1.in-addr.arpa
                reversed_parts = ip_address.split('.')[::-1]
                ptr_name = '.'.join(reversed_parts) + '.in-addr.arpa'
            else:
                # IPv6: 2001:db8::1 -> 1.0.0.0...ip6.arpa
                # Vereinfachte Implementierung
                expanded = ipaddress.ip_address(ip_address).exploded
                # Entferne Doppelpunkte und kehre um
                hex_chars = expanded.replace(':', '')
                reversed_chars = hex_chars[::-1]
                ptr_name = '.'.join(reversed_chars) + '.ip6.arpa'
            
            # PTR-Eintrag auflösen
            return await self.resolve_hostname(ptr_name, "PTR")
            
        except ValueError as e:
            logger.error(f"Ungültige IP-Adresse für Reverse-DNS: {ip_address}")
            raise DNSError(f"Ungültige IP-Adresse: {ip_address}")
    
    async def perform_zone_transfer(self, zone_name: str, nameserver: Optional[str] = None) -> Optional[DNSZone]:
        """
        Führt DNS-Zonen-Transfer durch
        
        Args:
            zone_name: Name der Zone
            nameserver: Optional spezifischer Nameserver
            
        Returns:
            DNSZone oder None bei Fehler
            
        Warnung: Zonen-Transfer erfordert Berechtigung!
        """
        if not self.config.get("enable_zone_transfer", False):
            logger.warning("Zonen-Transfer nicht aktiviert")
            return None
        
        try:
            # Nameserver bestimmen
            target_nameserver = nameserver
            if not target_nameserver:
                # NS-Einträge für Zone abfragen
                ns_result = await self.resolve_hostname(zone_name, "NS")
                if ns_result.answers:
                    target_nameserver = ns_result.answers[0].value
            
            if not target_nameserver:
                logger.error(f"Kein Nameserver für Zone {zone_name} gefunden")
                return None
            
            # Zonen-Transfer durchführen
            start_time = datetime.now()
            
            # AXFR (vollständiger Transfer)
            zone = dns.zone.from_xfr(dns.query.xfr(target_nameserver, zone_name))
            
            end_time = datetime.now()
            self.stats["zone_transfers"] += 1
            
            # Zone parsen
            records = []
            for (name, ttl, rdata) in zone.iterate_rdatas():
                record = DNSRecord(
                    name=str(name),
                    record_type=rdata.rdtype.name,
                    value=str(rdata),
                    ttl=ttl
                )
                records.append(record)
            
            # SOA-Eintrag extrahieren
            soa_record = None
            for record in records:
                if record.record_type == "SOA":
                    soa_record = record
                    break
            
            # DNSZone erstellen
            dns_zone = DNSZone(
                zone_name=zone_name,
                records=records,
                nameservers=[target_nameserver],
                last_updated=end_time
            )
            
            if soa_record:
                # SOA-Werte extrahieren
                soa_values = soa_record.value.split()
                if len(soa_values) >= 7:
                    dns_zone.serial = int(soa_values[2]) if soa_values[2].isdigit() else None
                    dns_zone.refresh = int(soa_values[3]) if soa_values[3].isdigit() else None
                    dns_zone.retry = int(soa_values[4]) if soa_values[4].isdigit() else None
                    dns_zone.expire = int(soa_values[5]) if soa_values[5].isdigit() else None
                    dns_zone.minimum_ttl = int(soa_values[6]) if soa_values[6].isdigit() else None
            
            logger.info(f"Zonen-Transfer für {zone_name} erfolgreich: {len(records)} Einträge")
            return dns_zone
            
        except Exception as e:
            logger.error(f"Zonen-Transfer fehlgeschlagen für {zone_name}: {e}")
            return None
    
    async def get_domain_records(self, domain: str) -> Dict[str, List[DNSRecord]]:
        """
        Holt alle DNS-Einträge für eine Domain
        
        Args:
            domain: Domain-Name
            
        Returns:
            Dictionary nach Record-Typ gruppiert
        """
        record_types = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"]
        
        results = {}
        
        for record_type in record_types:
            try:
                resolution = await self.resolve_hostname(domain, record_type)
                if resolution.answers:
                    results[record_type] = resolution.answers
            except Exception as e:
                logger.debug(f"DNS-Eintrag {record_type} für {domain} nicht gefunden: {e}")
        
        return results
    
    async def discover_dns_servers(self, domain: str) -> List[str]:
        """
        Entdeckt DNS-Server für eine Domain
        
        Args:
            domain: Domain-Name
            
        Returns:
            Liste von DNS-Servern
        """
        dns_servers = []
        
        try:
            # NS-Einträge für Domain
            ns_result = await self.resolve_hostname(domain, "NS")
            for answer in ns_result.answers:
                ns_hostname = answer.value.rstrip('.')
                
                # A-Einträge für NS-Hostnamen
                try:
                    a_result = await self.resolve_hostname(ns_hostname, "A")
                    for a_answer in a_result.answers:
                        dns_servers.append(a_answer.value)
                except Exception as e:
                    logger.debug(f"Keine A-Einträge für {ns_hostname}: {e}")
                    
                # AAAA-Einträge für NS-Hostnamen
                try:
                    aaaa_result = await self.resolve_hostname(ns_hostname, "AAAA")
                    for aaaa_answer in aaaa_result.answers:
                        dns_servers.append(f"[{aaaa_answer.value}]")
                except Exception as e:
                    logger.debug(f"Keine AAAA-Einträge für {ns_hostname}: {e}")
                    
        except Exception as e:
            logger.warning(f"DNS-Server-Entdeckung fehlgeschlagen für {domain}: {e}")
        
        return dns_servers
    
    async def resolve_ip_to_hostname(self, ip_address: str) -> Optional[str]:
        """
        Konvertiert IP-Adresse zu Hostname
        
        Args:
            ip_address: IP-Adresse
            
        Returns:
            Hostname oder None
        """
        try:
            result = await self.reverse_dns_lookup(ip_address)
            
            if result.answers:
                # Nimm ersten PTR-Eintrag
                ptr_value = result.answers[0].value
                return ptr_value.rstrip('.')
            
            return None
            
        except Exception as e:
            logger.debug(f"Reverse-DNS fehlgeschlagen für {ip_address}: {e}")
            return None
    
    async def batch_resolve_hostnames(self, hostnames: List[str], record_type: str = "A") -> Dict[str, DNSResolutionResult]:
        """
        Löst mehrere Hostnamen gleichzeitig auf
        
        Args:
            hostnames: Liste von Hostnamen
            record_type: DNS-Eintragstyp
            
        Returns:
            Dictionary mit Hostname->Ergebnis Zuordnung
        """
        tasks = {}
        
        for hostname in hostnames:
            tasks[hostname] = asyncio.create_task(self.resolve_hostname(hostname, record_type))
        
        results = {}
        for hostname, task in tasks.items():
            try:
                results[hostname] = await task
            except Exception as e:
                logger.warning(f"Batch-Auflösung fehlgeschlagen für {hostname}: {e}")
                results[hostname] = DNSResolutionResult(
                    query=hostname,
                    query_type=record_type,
                    answers=[],
                    authoritative=False
                )
        
        return results
    
    def get_domain_computers(self, domain_records: Dict[str, List[DNSRecord]]) -> List[str]:
        """
        Extrahiert Computer-Hostnamen aus DNS-Einträgen
        
        Args:
            domain_records: DNS-Einträge nach Typ gruppiert
            
        Returns:
            Liste von Computer-Hostnamen
        """
        computers = []
        
        # A und AAAA Einträge sind Hosts
        for record_type in ["A", "AAAA"]:
            if record_type in domain_records:
                for record in domain_records[record_type]:
                    hostname = record.name.rstrip('.')
                    if hostname not in computers:
                        computers.append(hostname)
        
        return computers
    
    def clear_cache(self):
        """Leert den DNS-Cache"""
        self.cache.clear()
        logger.info("DNS-Cache geleert")
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "cache_enabled": self.cache_enabled,
            "dns_servers": self.dns_servers
        }
    
    def _parse_dns_servers(self) -> List[str]:
        """Parst DNS-Server-Adressen"""
        servers = []
        
        for server in self.dns_servers:
            # Unterstützt "8.8.8.8" oder "8.8.8.8:53" Format
            if ':' in server:
                ip, port = server.split(':')
            else:
                ip, port = server, 53
            
            try:
                # Versuche IP in numerische Form zu konvertieren
                socket.inet_aton(ip)
                servers.append(ip)
            except socket.error:
                # Falls Hostname, auflösen
                try:
                    ip_resolved = socket.gethostbyname(ip)
                    servers.append(ip_resolved)
                except Exception:
                    logger.warning(f"DNS-Server {server} konnte nicht aufgelöst werden")
        
        return servers
    
    def _update_stats(self, response_time: float):
        """Aktualisiert Antwortzeit-Statistiken"""
        if self.stats["response_time_avg_ms"] == 0:
            self.stats["response_time_avg_ms"] = response_time
        else:
            # Gleitender Durchschnitt
            self.stats["response_time_avg_ms"] = (
                self.stats["response_time_avg_ms"] * 0.9 + response_time * 0.1
            )
    
    async def resolve(self, query: str, query_type: str = "forward", record_type: str = "A") -> Dict[str, Any]:
        """
        Löst eine DNS-Anfrage auf
        
        Args:
            query: Zu auflösende Query (Hostname oder IP)
            query_type: "forward" für Hostname-Auflösung, "reverse" für Reverse-DNS
            record_type: DNS Record Type (A, AAAA, MX, etc.)
            
        Returns:
            Dictionary mit Antwort-Daten
        """
        try:
            if query_type.lower() == "forward":
                result = await self.resolve_hostname(query, record_type)
                return {
                    "answers": [{"value": answer.value} for answer in result.answers],
                    "success": result.success,
                    "error": result.error,
                    "timestamp": result.timestamp.isoformat()
                }
            elif query_type.lower() == "reverse":
                result = await self.reverse_dns_lookup(query)
                return {
                    "answers": [{"value": answer.value} for answer in result.answers],
                    "success": result.success,
                    "error": result.error,
                    "timestamp": result.timestamp.isoformat()
                }
            else:
                raise ValueError(f"Unbekannter query_type: {query_type}. Erlaubt: 'forward', 'reverse'")
        except Exception as e:
            logger.error(f"Fehler bei DNS-Auflösung für {query} ({query_type}): {e}")
            return {
                "answers": [],
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }