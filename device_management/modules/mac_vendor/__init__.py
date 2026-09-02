"""
MAC Vendor Lookup für Phase 2

Hersteller-Erkennung über MAC-Adressen.
Verwendet IEEE OUI-Datenbank für Hersteller-Identifikation.
Unterstützt verschiedene Datenbankquellen und Cache.
"""

import logging
import re
import json
import os
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import urllib.request
import gzip
import io

logger = logging.getLogger(__name__)


@dataclass
class MACVendor:
    """MAC-Vendor Information"""
    prefix: str                    # Erste 6 Hex-Zeichen (z.B. "00:11:22")
    vendor: str                    # Hersteller-Name
    address: Optional[str] = None  # Hersteller-Adresse
    country: Optional[str] = None  # Hersteller-Land
    assignment: Optional[str] = None  # Zuweisungstyp (MA-L, MA-M, MA-S)
    updated: Optional[datetime] = None  # Letztes Update
    source: str = "IEEE OUI"       # Datenquelle
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Vendor-Info in ein Dictionary"""
        return {
            "prefix": self.prefix,
            "vendor": self.vendor,
            "address": self.address,
            "country": self.country,
            "assignment": self.assignment,
            "updated": self.updated.isoformat() if self.updated else None,
            "source": self.source
        }


@dataclass
class MACAddressInfo:
    """Komplette MAC-Adressen-Information"""
    mac_address: str              # Originale MAC-Adresse
    normalized_mac: str          # Normalisierte Form (AA:BB:CC:DD:EE:FF)
    vendor_prefix: Optional[str] = None  # Erste 6 Hex-Zeichen
    vendor_info: Optional[MACVendor] = None  # Hersteller-Info
    is_universal: bool = True     # Universell (nicht lokal)
    is_multicast: bool = False    # Multicast-Adresse
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert MAC-Info in ein Dictionary"""
        return {
            "mac_address": self.mac_address,
            "normalized_mac": self.normalized_mac,
            "vendor_prefix": self.vendor_prefix,
            "vendor": self.vendor_info.to_dict() if self.vendor_info else None,
            "is_universal": self.is_universal,
            "is_multicast": self.is_multicast,
            "timestamp": self.timestamp.isoformat()
        }


class MACVendorLookup:
    """
    MAC-Vendor Lookup für Netzwerk-Scans.
    
    Fähigkeiten:
    - Hersteller-Identifikation über MAC-Adressen
    - IEEE OUI-Datenbank Integration
    - Normalisierung von MAC-Adressen
    - Cache für schnelle Abfragen
    - Automatische Datenbank-Aktualisierung
    - Multicast/Local-Adresserkennung
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den MAC-Vendor Lookup
        
        Args:
            config: Konfigurationsdictionary mit:
                - database_path: Pfad zur lokalen Datenbank (default: mac_vendors.db)
                - auto_update: Automatische Aktualisierung aktivieren (default: True)
                - update_url: URL für OUI-Datenbank-Updates
                - use_cache: Cache für Lookups verwenden (default: True)
                - cache_ttl_days: TTL für Cache in Tagen (default: 30)
                - normalize_mac: MAC-Adressen normalisieren (default: True)
        """
        self.config = config
        
        # Pfade und URLs
        self.database_path = config.get("database_path", "mac_vendors.db")
        self.auto_update = config.get("auto_update", True)
        
        # Standard IEEE OUI URLs
        self.update_urls = config.get("update_url", [
            "https://standards-oui.ieee.org/oui/oui.csv",
            "https://standards-oui.ieee.org/oui28/mam.csv",
            "https://standards-oui.ieee.org/oui36/oui36.csv"
        ])
        
        # Cache
        self.cache_enabled = config.get("use_cache", True)
        self.cache: Dict[str, MACVendor] = {}
        
        # Statistiken
        self.stats = {
            "lookups_total": 0,
            "lookups_cached": 0,
            "lookups_database": 0,
            "lookups_failed": 0,
            "database_size": 0,
            "last_update": None
        }
        
        # Datenbank initialisieren
        self._init_database()
        
        # Bei Bedarf aktualisieren
        if self.auto_update:
            self._check_and_update_database()
        
        logger.info("MAC-Vendor Lookup initialisiert")
    
    def _init_database(self):
        """Initialisiert die Vendor-Datenbank"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Tabellen erstellen
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vendors (
                    prefix TEXT PRIMARY KEY,
                    vendor TEXT NOT NULL,
                    address TEXT,
                    country TEXT,
                    assignment TEXT,
                    updated DATETIME,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_accessed DATETIME
                )
            ''')
            
            # Indizes erstellen
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_vendor_search ON vendors(vendor)
            ''')
            
            # Statistiken aktualisieren
            cursor.execute('SELECT COUNT(*) FROM vendors')
            self.stats["database_size"] = cursor.fetchone()[0]
            
            cursor.execute('SELECT MAX(updated) FROM vendors')
            last_update = cursor.fetchone()[0]
            if last_update:
                self.stats["last_update"] = last_update
            
            conn.commit()
            conn.close()
            
            logger.info(f"MAC-Vendor Datenbank mit {self.stats['database_size']} Einträgen")
            
        except Exception as e:
            logger.error(f"Fehler bei Datenbank-Initialisierung: {e}")
            raise
    
    def _check_and_update_database(self):
        """
        Prüft ob Datenbank aktualisiert werden muss
        
        Aktualisiert automatisch wenn:
        1. Datenbank leer ist
        2. Letztes Update > 30 Tage her ist
        """
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Prüfe ob Datenbank leer
            cursor.execute('SELECT COUNT(*) FROM vendors')
            count = cursor.fetchone()[0]
            
            if count == 0:
                logger.info("Datenbank ist leer, starte automatischen Download...")
                self.update_database()
                return
            
            # Prüfe letztes Update
            cursor.execute('SELECT MAX(updated) FROM vendors WHERE updated IS NOT NULL')
            last_update_str = cursor.fetchone()[0]
            
            if last_update_str:
                from datetime import datetime, timedelta
                last_update = datetime.fromisoformat(last_update_str)
                days_since_update = (datetime.now() - last_update).days
                
                if days_since_update > 30:
                    logger.info(f"Datenbank ist {days_since_update} Tage alt, starte Update...")
                    self.update_database()
            
            conn.close()
            
        except Exception as e:
            logger.warning(f"Fehler bei Datenbank-Check: {e}")
    
    def update_database(self) -> bool:
        """
        Aktualisiert die Vendor-Datenbank
        
        Returns:
            True bei Erfolg
        """
        logger.info("Aktualisiere MAC-Vendor Datenbank...")
        
        successful_downloads = 0
        
        for url in self.update_urls:
            try:
                logger.info(f"Lade Daten von {url}")
                
                # Datei herunterladen
                response = urllib.request.urlopen(url, timeout=30)
                
                # Prüfe Content-Type
                content_type = response.headers.get('Content-Type', '')
                content_encoding = response.headers.get('Content-Encoding', '')
                
                # Dekomprimieren falls nötig
                if 'gzip' in content_encoding or url.endswith('.gz'):
                    compressed_data = response.read()
                    data = gzip.decompress(compressed_data).decode('utf-8')
                else:
                    data = response.read().decode('utf-8')
                
                # CSV parsen
                vendors_added = self._parse_csv_data(data, url)
                successful_downloads += 1
                
                logger.info(f"Von {url}: {vendors_added} Vendor(s) hinzugefügt")
                
            except Exception as e:
                logger.warning(f"Fehler beim Download von {url}: {e}")
        
        # Statistiken aktualisieren
        if successful_downloads > 0:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM vendors')
            self.stats["database_size"] = cursor.fetchone()[0]
            self.stats["last_update"] = datetime.now().isoformat()
            
            conn.close()
            
            logger.info(f"Datenbankaktualisierung abgeschlossen: {self.stats['database_size']} Vendor(s)")
            return True
        
        logger.warning("Keine Daten erfolgreich aktualisiert")
        return False
    
    def _parse_csv_data(self, csv_data: str, source: str) -> int:
        """
        Parst CSV-Daten und fügt sie der Datenbank hinzu
        
        Args:
            csv_data: CSV-Daten als String
            source: Datenquelle
            
        Returns:
            Anzahl hinzugefügter Vendor-Einträge
        """
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            lines = csv_data.strip().split('\n')
            vendors_added = 0
            
            # IEEE CSV hat typischerweise Header: Registry,Assignment,Organization Name,Organization Address
            # Oder: OUI,Organization Name,Organization Address
            
            for line in lines[1:]:  # Überspringe Header
                parts = [part.strip('"') for part in line.split(',')]
                
                if len(parts) >= 3:
                    # Extrahiere OUI/Prefix (erste 6 Hex-Zeichen)
                    oui_field = parts[0].strip()
                    vendor_name = parts[1].strip()
                    
                    # In manchen Dateien ist die Adresse kombinierter String
                    address = parts[2].strip() if len(parts) > 2 else ""
                    
                    # Parse OUI/Prefix
                    prefix = self._extract_oui_prefix(oui_field)
                    if not prefix:
                        continue
                    
                    # Extrahiere zusätzliche Felder
                    country = None
                    assignment = None
                    
                    if len(parts) > 3:
                        country = parts[3].strip() if len(parts) > 3 else None
                    
                    if len(parts) > 4:
                        assignment = parts[4].strip() if len(parts) > 4 else None
                    
                    # Vendor erstellen
                    vendor = MACVendor(
                        prefix=prefix,
                        vendor=vendor_name,
                        address=address if address else None,
                        country=country,
                        assignment=assignment,
                        updated=datetime.now(),
                        source=source
                    )
                    
                    # In Datenbank einfügen oder aktualisieren
                    try:
                        cursor.execute('''
                            INSERT OR REPLACE INTO vendors 
                            (prefix, vendor, address, country, assignment, updated, source, last_accessed)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            vendor.prefix,
                            vendor.vendor,
                            vendor.address,
                            vendor.country,
                            vendor.assignment,
                            vendor.updated.isoformat(),
                            vendor.source,
                            datetime.now().isoformat()
                        ))
                        
                        vendors_added += 1
                        
                    except Exception as e:
                        logger.debug(f"Fehler beim Einfügen von Vendor {prefix}: {e}")
            
            conn.commit()
            conn.close()
            
            # Cache leeren
            if self.cache_enabled:
                self.cache.clear()
            
            return vendors_added
            
        except Exception as e:
            logger.error(f"Fehler beim Parsen von CSV-Daten: {e}")
            return 0
    
    def _extract_oui_prefix(self, oui_field: str) -> Optional[str]:
        """
        Extrahiert OUI-Prefix aus Feld
        
        Args:
            oui_field: OUI-Feld aus CSV
            
        Returns:
            Normalisierter Prefix (z.B. "00:11:22") oder None
        """
        try:
            # Entferne nicht-Hex-Zeichen
            hex_chars = re.sub(r'[^0-9A-Fa-f]', '', oui_field)
            
            if len(hex_chars) >= 6:
                prefix_hex = hex_chars[:6].upper()
                
                # In AA:BB:CC Format konvertieren
                normalized = ':'.join([prefix_hex[i:i+2] for i in range(0, 6, 2)])
                return normalized
            
            return None
            
        except Exception:
            return None
    
    def normalize_mac_address(self, mac_address: str) -> Optional[str]:
        """
        Normalisiert MAC-Adresse in AA:BB:CC:DD:EE:FF Format
        
        Args:
            mac_address: MAC-Adresse in beliebigem Format
            
        Returns:
            Normalisierte MAC-Adresse oder None bei Fehler
        """
        try:
            # Entferne alle nicht-Hex-Zeichen
            hex_chars = re.sub(r'[^0-9A-Fa-f]', '', mac_address.upper())
            
            if len(hex_chars) != 12:
                return None
            
            # In AA:BB:CC:DD:EE:FF Format konvertieren
            normalized = ':'.join([hex_chars[i:i+2] for i in range(0, 12, 2)])
            return normalized
            
        except Exception:
            return None
    
    def analyze_mac_address(self, mac_address: str) -> Dict[str, Any]:
        """
        Analysiert MAC-Adresse auf Eigenschaften
        
        Args:
            mac_address: MAC-Adresse
            
        Returns:
            Dictionary mit Analyse-Ergebnissen
        """
        normalized = self.normalize_mac_address(mac_address)
        if not normalized:
            return {"error": "Ungültige MAC-Adresse"}
        
        # Extrahiere erstes Byte für Analyse
        first_byte_hex = normalized[:2]
        first_byte = int(first_byte_hex, 16)
        
        # Universell/Local Bit (zweites niedrigstwertige Bit vom ersten Byte)
        universal_local_bit = (first_byte >> 1) & 0x01
        
        # Multicast/Unicast Bit (niedrigstwertige Bit vom ersten Byte)
        multicast_bit = first_byte & 0x01
        
        is_universal = universal_local_bit == 0  # 0 = universell, 1 = lokal
        is_multicast = multicast_bit == 1  # 1 = multicast, 0 = unicast
        
        # Vendor Prefix extrahieren
        vendor_prefix = normalized[:8]  # AA:BB:CC
        
        # Vendor Lookup
        vendor_info = self.lookup_vendor(vendor_prefix)
        
        return {
            "normalized_mac": normalized,
            "vendor_prefix": vendor_prefix,
            "vendor_info": vendor_info.to_dict() if vendor_info else None,
            "is_universal": is_universal,
            "is_multicast": is_multicast,
            "is_local": not is_universal,
            "is_unicast": not is_multicast,
            "analysis": {
                "first_byte_hex": first_byte_hex,
                "first_byte_decimal": first_byte,
                "universal_local_bit": universal_local_bit,
                "multicast_bit": multicast_bit
            }
        }
    
    def lookup_vendor(self, mac_prefix: str) -> Optional[MACVendor]:
        """
        Sucht Vendor für MAC-Prefix
        
        Args:
            mac_prefix: MAC-Prefix (erste 6 Hex-Zeichen), z.B. "00:11:22"
            
        Returns:
            MACVendor oder None
        """
        self.stats["lookups_total"] += 1
        
        # Normalisiere Prefix
        normalized_prefix = self.normalize_mac_address(mac_prefix + "000000")
        if not normalized_prefix:
            return None
        
        vendor_prefix = normalized_prefix[:8]  # AA:BB:CC Format
        
        # Prüfe Cache
        if self.cache_enabled and vendor_prefix in self.cache:
            self.stats["lookups_cached"] += 1
            logger.debug(f"Cache-Treffer für {vendor_prefix}")
            return self.cache[vendor_prefix]
        
        # Datenbank-Abfrage
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT prefix, vendor, address, country, assignment, updated, source
                FROM vendors
                WHERE prefix = ?
                ORDER BY updated DESC
                LIMIT 1
            ''', (vendor_prefix,))
            
            row = cursor.fetchone()
            
            if row:
                # Update last_accessed
                cursor.execute('''
                    UPDATE vendors 
                    SET last_accessed = ?
                    WHERE prefix = ?
                ''', (datetime.now().isoformat(), vendor_prefix))
                
                conn.commit()
                conn.close()
                
                # Vendor erstellen
                vendor = MACVendor(
                    prefix=row[0],
                    vendor=row[1],
                    address=row[2],
                    country=row[3],
                    assignment=row[4],
                    updated=datetime.fromisoformat(row[5]) if row[5] else None,
                    source=row[6]
                )
                
                # In Cache speichern
                if self.cache_enabled:
                    self.cache[vendor_prefix] = vendor
                
                self.stats["lookups_database"] += 1
                logger.debug(f"Vendor gefunden für {vendor_prefix}: {vendor.vendor}")
                return vendor
            else:
                conn.close()
                self.stats["lookups_failed"] += 1
                logger.debug(f"Kein Vendor gefunden für {vendor_prefix}")
                return None
                
        except Exception as e:
            self.stats["lookups_failed"] += 1
            logger.warning(f"Fehler bei Vendor-Lookup für {vendor_prefix}: {e}")
            return None
    
    def lookup_mac_address(self, mac_address: str) -> MACAddressInfo:
        """
        Kompletter Lookup für MAC-Adresse
        
        Args:
            mac_address: MAC-Adresse
            
        Returns:
            MACAddressInfo mit allen Informationen
        """
        normalized_mac = self.normalize_mac_address(mac_address)
        
        if not normalized_mac:
            raise ValueError(f"Ungültige MAC-Adresse: {mac_address}")
        
        # Analyse
        analysis = self.analyze_mac_address(mac_address)
        
        vendor_prefix = analysis.get("vendor_prefix")
        vendor_info = None
        
        if vendor_prefix:
            vendor_info = self.lookup_vendor(vendor_prefix)
        
        # MACAddressInfo erstellen
        mac_info = MACAddressInfo(
            mac_address=mac_address,
            normalized_mac=normalized_mac,
            vendor_prefix=vendor_prefix,
            vendor_info=vendor_info,
            is_universal=analysis.get("is_universal", True),
            is_multicast=analysis.get("is_multicast", False)
        )
        
        return mac_info
    
    def batch_lookup_mac_addresses(self, mac_addresses: List[str]) -> Dict[str, MACAddressInfo]:
        """
        Führt Lookup für mehrere MAC-Adressen durch
        
        Args:
            mac_addresses: Liste von MAC-Adressen
            
        Returns:
            Dictionary mit MAC->Info Zuordnung
        """
        results = {}
        
        for mac in mac_addresses:
            try:
                mac_info = self.lookup_mac_address(mac)
                results[mac] = mac_info
            except Exception as e:
                logger.warning(f"Batch-Lookup fehlgeschlagen für {mac}: {e}")
                results[mac] = MACAddressInfo(
                    mac_address=mac,
                    normalized_mac=mac,
                    vendor_prefix=None,
                    vendor_info=None,
                    is_universal=True,
                    is_multicast=False
                )
        
        return results
    
    def search_vendors(self, search_term: str, limit: int = 50) -> List[MACVendor]:
        """
        Sucht Vendor nach Namen
        
        Args:
            search_term: Suchbegriff
            limit: Maximale Ergebnisse
            
        Returns:
            Liste von MACVendor
        """
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT prefix, vendor, address, country, assignment, updated, source
                FROM vendors
                WHERE vendor LIKE ? OR prefix LIKE ?
                ORDER BY vendor
                LIMIT ?
            ''', (f'%{search_term}%', f'%{search_term}%', limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            vendors = []
            for row in rows:
                vendor = MACVendor(
                    prefix=row[0],
                    vendor=row[1],
                    address=row[2],
                    country=row[3],
                    assignment=row[4],
                    updated=datetime.fromisoformat(row[5]) if row[5] else None,
                    source=row[6]
                )
                vendors.append(vendor)
            
            logger.debug(f"Vendor-Suche: {len(vendors)} Ergebnisse für '{search_term}'")
            return vendors
            
        except Exception as e:
            logger.error(f"Fehler bei Vendor-Suche: {e}")
            return []
    
    def get_common_vendors(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Gibt häufigste Vendor zurück
        
        Args:
            limit: Maximale Anzahl
            
        Returns:
            Liste von Vendor-Statistiken
        """
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Zähle wie oft jeder Vendor in der Datenbank vorkommt
            cursor.execute('''
                SELECT vendor, COUNT(*) as count
                FROM vendors
                GROUP BY vendor
                ORDER BY count DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            common_vendors = []
            for vendor, count in rows:
                common_vendors.append({
                    "vendor": vendor,
                    "count": count,
                    "percentage": (count / self.stats["database_size"]) * 100 if self.stats["database_size"] > 0 else 0
                })
            
            return common_vendors
            
        except Exception as e:
            logger.error(f"Fehler bei Common-Vendors: {e}")
            return []
    
    def clear_cache(self):
        """Leert den Vendor-Cache"""
        self.cache.clear()
        logger.info("Vendor-Cache geleert")
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "cache_enabled": self.cache_enabled,
            "database_path": self.database_path,
            "auto_update": self.auto_update
        }
    
    def lookup(self, mac_addresses: List[str]) -> List[Dict[str, Any]]:
        """
        Lookup für MAC-Adressen (API-kompatibel mit Tests)
        
        Args:
            mac_addresses: Liste von MAC-Adressen
            
        Returns:
            Liste von Ergebnis-Dictionaries
        """
        results = []
        for mac in mac_addresses:
            try:
                mac_info = self.lookup_mac_address(mac)
                # Konvertiere MACAddressInfo in dictionary-Format für Tests
                result = {
                    "mac_address": mac_info.mac_address,
                    "vendor": {"vendor": mac_info.vendor.vendor if mac_info.vendor else "Unbekannt"}
                }
                results.append(result)
            except Exception as e:
                logger.warning(f"Lookup fehlgeschlagen für {mac}: {e}")
                results.append({
                    "mac_address": mac,
                    "vendor": {"vendor": "Unbekannt"}
                })
        return results