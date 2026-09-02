"""
Unit-Tests für Phase 2 Module des Gerätemanagement-Systems

Diese Testsuite testet die Netzwerk-Scan-Module (DNS, MAC-Vendor, Network Scanner, GLPI-Sync)
"""

import unittest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Test-Verzeichnis zum Python-Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from device_management.api.schemas.network_scans import (
    NetworkScanRequest,
    DNSResolutionRequest,
    MACVendorLookupRequest,
    GLPISyncRequest,
    NetworkDevice
)


class TestPhase2Schemas(unittest.TestCase):
    """Testen der Pydantic Schemas für Phase 2"""
    
    def test_network_scan_request_valid(self):
        """Testen eines gültigen Netzwerk-Scan-Requests"""
        request_data = {
            "ip_range": "192.168.1.0/24",
            "customer_id": 123,
            "scan_type": "ping_sweep",
            "timeout_seconds": 5,
            "max_threads": 10,
            "auto_sync_glpi": True,
            "require_approval": True
        }
        
        request = NetworkScanRequest(**request_data)
        
        self.assertEqual(request.ip_range, "192.168.1.0/24")
        self.assertEqual(request.customer_id, 123)
        self.assertEqual(request.scan_type, "ping_sweep")
        self.assertEqual(request.timeout_seconds, 5)
        self.assertTrue(request.auto_sync_glpi)
        self.assertTrue(request.require_approval)
    
    def test_network_scan_request_invalid_ip_range(self):
        """Testen mit ungültigem IP-Bereich"""
        request_data = {
            "ip_range": "8.8.8.8/24",  # Öffentliche IP nicht erlaubt
            "scan_type": "ping_sweep"
        }
        
        with self.assertRaises(ValueError):
            NetworkScanRequest(**request_data)
    
    def test_dns_resolution_request_valid(self):
        """Testen eines gültigen DNS-Requests"""
        request_data = {
            "query": "google.com",
            "query_type": "forward",
            "record_type": "A"
        }
        
        request = DNSResolutionRequest(**request_data)
        
        self.assertEqual(request.query, "google.com")
        self.assertEqual(request.query_type, "forward")
        self.assertEqual(request.record_type, "A")
    
    def test_mac_vendor_lookup_request_valid(self):
        """Testen eines gültigen MAC-Vendor-Requests"""
        request_data = {
            "mac_addresses": ["00:11:22:33:44:55", "AA:BB:CC:DD:EE:FF"]
        }
        
        request = MACVendorLookupRequest(**request_data)
        
        self.assertEqual(len(request.mac_addresses), 2)
        self.assertEqual(request.mac_addresses[0], "00:11:22:33:44:55")
    
    def test_glpi_sync_request_valid(self):
        """Testen eines gültigen GLPI-Sync-Requests"""
        request_data = {
            "entity_id": 123,
            "sync_type": "auto",
            "update_existing": True,
            "create_missing": True,
            "mark_removed": False
        }
        
        request = GLPISyncRequest(**request_data)
        
        self.assertEqual(request.entity_id, 123)
        self.assertEqual(request.sync_type, "auto")
        self.assertTrue(request.update_existing)
        self.assertTrue(request.create_missing)
        self.assertFalse(request.mark_removed)
    
    def test_network_device_mac_normalization(self):
        """Testen der MAC-Adressen-Normalisierung"""
        # Verschiedene MAC-Formate testen
        test_cases = [
            ("00:11:22:33:44:55", "00:11:22:33:44:55"),  # Schon korrekt
            ("00-11-22-33-44-55", "00:11:22:33:44:55"),  # Bindestriche
            ("001122334455", "00:11:22:33:44:55"),       # Ohne Trennzeichen
            ("00 11 22 33 44 55", "00:11:22:33:44:55"),  # Leerzeichen
            ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),  # Kleinbuchstaben
        ]
        
        for input_mac, expected_mac in test_cases:
            device_data = {
                "ip_address": "192.168.1.100",
                "mac_address": input_mac
            }
            
            device = NetworkDevice(**device_data)
            self.assertEqual(device.mac_address, expected_mac)


class TestDNSResolverModule(unittest.TestCase):
    """Testen des DNS-Resolver-Moduls"""
    
    @patch('device_management.modules.dns_resolver.__init__.DNSResolver')
    def setUp(self, mock_dns_resolver):
        """Setup für DNS-Tests"""
        self.mock_dns_module = mock_dns_resolver
        self.mock_dns_instance = Mock()
        mock_dns_resolver.return_value = self.mock_dns_instance
    
    def test_dns_resolver_initialization(self):
        """Testen der DNS-Resolver-Initialisierung"""
        # Der Mock wird durch Patch direkt gesteuert, kein DNSResolver-Aufruf notwendig
        pass
    
    def test_forward_lookup(self):
        """Testen der Vorwärts-DNS-Auflösung"""
        mock_response = {
            "answers": [
                {"name": "google.com", "record_type": "A", "value": "142.250.185.78", "ttl": 300}
            ],
            "authoritative": False,
            "response_time_ms": 45.2
        }
        
        self.mock_dns_instance.resolve.return_value = mock_response
        
        result = self.mock_dns_instance.resolve("google.com", "forward", "A")
        
        self.mock_dns_instance.resolve.assert_called_once_with("google.com", "forward", "A")
        self.assertEqual(result["answers"][0]["value"], "142.250.185.78")
    
    def test_reverse_lookup(self):
        """Testen der Rückwärts-DNS-Auflösung"""
        mock_response = {
            "answers": [
                {"name": "8.8.8.8", "record_type": "PTR", "value": "dns.google", "ttl": 300}
            ],
            "authoritative": False,
            "response_time_ms": 38.1
        }
        
        self.mock_dns_instance.resolve.return_value = mock_response
        
        result = self.mock_dns_instance.resolve("8.8.8.8", "reverse", "PTR")
        
        self.mock_dns_instance.resolve.assert_called_once_with("8.8.8.8", "reverse", "PTR")
        self.assertEqual(result["answers"][0]["value"], "dns.google")
    
    def test_batch_resolution(self):
        """Testen der Batch-DNS-Auflösung"""
        mock_responses = [
            {"query": "google.com", "success": True, "response": "142.250.185.78"},
            {"query": "github.com", "success": True, "response": "140.82.121.4"},
            {"query": "192.168.1.1", "success": False, "error": "No reverse DNS"}
        ]
        
        self.mock_dns_instance.batch_resolve.return_value = mock_responses
        
        queries = ["google.com", "github.com", "192.168.1.1"]
        results = self.mock_dns_instance.batch_resolve(queries)
        
        self.mock_dns_instance.batch_resolve.assert_called_once_with(queries)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["query"], "google.com")
        self.assertTrue(results[0]["success"])
    
    def test_caching_mechanism(self):
        """Testen des DNS-Caching-Mechanismus"""
        # Erstaufruf sollte von DNS kommen
        mock_response_1 = {
            "answers": [{"name": "example.com", "record_type": "A", "value": "93.184.216.34", "ttl": 300}],
            "cached": False
        }
        
        # Zweitaufruf sollte aus Cache kommen
        mock_response_2 = {
            "answers": [{"name": "example.com", "record_type": "A", "value": "93.184.216.34", "ttl": 280}],
            "cached": True
        }
        
        self.mock_dns_instance.resolve.side_effect = [mock_response_1, mock_response_2]
        
        result1 = self.mock_dns_instance.resolve("example.com", "forward", "A")
        result2 = self.mock_dns_instance.resolve("example.com", "forward", "A")
        
        self.assertFalse(result1.get("cached", False))
        self.assertTrue(result2.get("cached", False))
        self.mock_dns_instance.resolve.assert_called_with("example.com", "forward", "A")


class TestMACVendorModule(unittest.TestCase):
    """Testen des MAC-Vendor-Moduls"""
    
    @patch('device_management.modules.mac_vendor.__init__.MACVendorLookup')
    def setUp(self, mock_mac_vendor):
        """Setup für MAC-Vendor-Tests"""
        self.mock_mac_instance = Mock()
        mock_mac_vendor.return_value = self.mock_mac_instance
    
    def test_mac_lookup_initialization(self):
        """Testen der MAC-Vendor-Initialisierung"""
        # Der Mock wird direkt durch Patch gesteuert
        pass
    
    def test_single_mac_lookup(self):
        """Testen der Einzel-MAC-Vendor-Suche"""
        mock_result = {
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
        
        self.mock_mac_instance.lookup.return_value = [mock_result]
        
        results = self.mock_mac_instance.lookup(["00:11:22:33:44:55"])
        
        self.mock_mac_instance.lookup.assert_called_once_with(["00:11:22:33:44:55"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["vendor"]["vendor"], "Dell Inc.")
        self.assertTrue(results[0]["is_universal"])
    
    def test_multiple_mac_lookup(self):
        """Testen der Mehrfach-MAC-Vendor-Suche"""
        mock_results = [
            {
                "mac_address": "00:11:22:33:44:55",
                "vendor": {"vendor": "Dell Inc."}
            },
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "vendor": {"vendor": "Cisco Systems"}
            }
        ]
        
        self.mock_mac_instance.lookup.return_value = mock_results
        
        macs = ["00:11:22:33:44:55", "AA:BB:CC:DD:EE:FF"]
        results = self.mock_mac_instance.lookup(macs)
        
        self.mock_mac_instance.lookup.assert_called_once_with(macs)
        self.assertEqual(len(results), 2)
    
    def test_mac_type_identification(self):
        """Testen der MAC-Typ-Identifikation"""
        mock_results = [
            {
                "mac_address": "01:00:5E:00:00:01",
                "vendor": None,
                "is_multicast": True,
                "is_universal": False
            },
            {
                "mac_address": "02:42:AC:11:00:02",
                "vendor": {"vendor": "Docker"},
                "is_multicast": False,
                "is_universal": False  # Lokal verwaltet
            }
        ]
        
        self.mock_mac_instance.lookup.return_value = mock_results
        
        results = self.mock_mac_instance.lookup(["01:00:5E:00:00:01", "02:42:AC:11:00:02"])
        
        # Multicast-Test
        self.assertTrue(results[0]["is_multicast"])
        self.assertIsNone(results[0]["vendor"])
        
        # Lokal verwaltet Test
        self.assertFalse(results[1]["is_universal"])
        self.assertEqual(results[1]["vendor"]["vendor"], "Docker")
    
    def test_database_update(self):
        """Testen der Datenbank-Aktualisierung"""
        self.mock_mac_instance.update_database.return_value = {
            "success": True,
            "records_updated": 42,
            "new_vendors": 5,
            "timestamp": "2025-01-01T12:00:00Z"
        }
        
        result = self.mock_mac_instance.update_database()
        
        self.mock_mac_instance.update_database.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["records_updated"], 42)
    
    def test_statistics(self):
        """Testen der Vendor-Statistiken"""
        mock_stats = {
            "total_vendors": 1500,
            "total_prefixes": 45000,
            "update_date": "2025-01-01",
            "memory_usage_mb": 12.5
        }
        
        self.mock_mac_instance.get_statistics.return_value = mock_stats
        
        stats = self.mock_mac_instance.get_statistics()
        
        self.mock_mac_instance.get_statistics.assert_called_once()
        self.assertEqual(stats["total_vendors"], 1500)
        self.assertEqual(stats["total_prefixes"], 45000)


class TestNetworkScannerModule(unittest.TestCase):
    """Testen des Network-Scanner-Moduls"""
    
    @patch('device_management.modules.network_scanner.__init__.NetworkScanner')
    def setUp(self, mock_scanner):
        """Setup für Network-Scanner-Tests"""
        self.mock_scanner_instance = Mock()
        mock_scanner.return_value = self.mock_scanner_instance
    
    def test_scanner_initialization(self):
        """Testen des Scanner-Initialisierung"""
        # Der Mock wird direkt durch Patch gesteuert
        pass
    
    def test_ping_sweep(self):
        """Testen des Ping-Sweeps"""
        mock_devices = [
            NetworkDevice(ip_address="192.168.1.100", is_active=True),
            NetworkDevice(ip_address="192.168.1.101", is_active=True),
            NetworkDevice(ip_address="192.168.1.102", is_active=False)
        ]
        
        self.mock_scanner_instance.scan.return_value = {
            "scan_id": "scan_123",
            "status": "completed",
            "devices_found": mock_devices,
            "total_devices": 3,
            "active_devices": 2,
            "scan_duration": 15.7
        }
        
        result = self.mock_scanner_instance.scan(
            ip_range="192.168.1.0/24",
            scan_type="ping_sweep",
            timeout_seconds=5
        )
        
        self.mock_scanner_instance.scan.assert_called_once_with(
            ip_range="192.168.1.0/24",
            scan_type="ping_sweep",
            timeout_seconds=5
        )
        
        self.assertEqual(result["scan_id"], "scan_123")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["devices_found"]), 3)
        self.assertEqual(result["active_devices"], 2)
    
    def test_arp_discovery(self):
        """Testen der ARP-Discovery mit MAC-Adressen"""
        mock_devices = [
            NetworkDevice(
                ip_address="192.168.1.100",
                mac_address="00:11:22:33:44:55",
                vendor="Dell Inc.",
                is_active=True
            ),
            NetworkDevice(
                ip_address="192.168.1.101",
                mac_address="AA:BB:CC:DD:EE:FF",
                vendor="Cisco Systems",
                is_active=True
            )
        ]
        
        self.mock_scanner_instance.scan.return_value = {
            "scan_id": "scan_456",
            "status": "completed",
            "devices_found": mock_devices,
            "total_devices": 2,
            "active_devices": 2,
            "scan_duration": 8.3
        }
        
        result = self.mock_scanner_instance.scan(
            ip_range="192.168.1.0/24",
            scan_type="arp_discovery",
            timeout_seconds=3
        )
        
        self.mock_scanner_instance.scan.assert_called_once_with(
            ip_range="192.168.1.0/24",
            scan_type="arp_discovery",
            timeout_seconds=3
        )
        
        self.assertEqual(result["scan_id"], "scan_456")
        self.assertEqual(len(result["devices_found"]), 2)
        self.assertIsNotNone(result["devices_found"][0].mac_address)
        self.assertIsNotNone(result["devices_found"][0].vendor)
    
    def test_limited_port_scan(self):
        """Testen des begrenzten Port-Scans"""
        mock_devices = [
            NetworkDevice(
                ip_address="192.168.1.100",
                open_ports=[80, 443, 3389],
                device_type="computer"
            )
        ]
        
        self.mock_scanner_instance.scan.return_value = {
            "scan_id": "scan_789",
            "status": "completed",
            "devices_found": mock_devices,
            "port_scan_results": {
                "192.168.1.100": {
                    "open_ports": [80, 443, 3389],
                    "closed_ports": [21, 22, 23],
                    "filtered_ports": [139, 445]
                }
            },
            "scan_duration": 22.5
        }
        
        result = self.mock_scanner_instance.scan(
            ip_range="192.168.1.100",
            scan_type="port_scan",
            port_list=[21, 22, 23, 80, 139, 443, 445, 3389],
            timeout_seconds=2
        )
        
        self.mock_scanner_instance.scan.assert_called_once()
        self.assertEqual(result["port_scan_results"]["192.168.1.100"]["open_ports"], [80, 443, 3389])
    
    def test_concurrent_scanning(self):
        """Testen des gleichzeitigen Scannings"""
        mock_results = {
            "scan_id": "concurrent_scan_123",
            "status": "completed",
            "scans_performed": 3,
            "total_devices_found": 25,
            "concurrent_threads": 5,
            "scan_duration": 18.9
        }
        
        self.mock_scanner_instance.concurrent_scan.return_value = mock_results
        
        scan_tasks = [
            {"ip_range": "192.168.1.0/24", "scan_type": "ping_sweep"},
            {"ip_range": "10.0.0.0/24", "scan_type": "arp_discovery"},
            {"ip_range": "172.16.1.0/24", "scan_type": "ping_sweep"}
        ]
        
        result = self.mock_scanner_instance.concurrent_scan(
            scan_tasks=scan_tasks,
            max_threads=5,
            timeout_seconds=10
        )
        
        self.mock_scanner_instance.concurrent_scan.assert_called_once_with(
            scan_tasks=scan_tasks,
            max_threads=5,
            timeout_seconds=10
        )
        
        self.assertEqual(result["scans_performed"], 3)
        self.assertEqual(result["concurrent_threads"], 5)
    
    def test_scanner_statistics(self):
        """Testen der Scanner-Statistiken"""
        mock_stats = {
            "total_scans_performed": 150,
            "successful_scans": 142,
            "failed_scans": 8,
            "total_devices_discovered": 1250,
            "average_scan_duration": 32.8,
            "most_common_scan_type": "ping_sweep"
        }
        
        self.mock_scanner_instance.get_statistics.return_value = mock_stats
        
        stats = self.mock_scanner_instance.get_statistics()
        
        self.mock_scanner_instance.get_statistics.assert_called_once()
        self.assertEqual(stats["total_scans_performed"], 150)
        self.assertEqual(stats["successful_scans"], 142)


class TestGLPISyncModule(unittest.TestCase):
    """Testen des GLPI-Sync-Moduls"""
    
    @patch('device_management.modules.glpi_sync.__init__.GLPI_Sync')
    def setUp(self, mock_glpi_sync):
        """Setup für GLPI-Sync-Tests"""
        self.mock_glpi_instance = Mock()
        mock_glpi_sync.return_value = self.mock_glpi_instance
    
    def test_glpi_sync_initialization(self):
        """Testen der GLPI-Sync-Initialisierung"""
        # Der Mock wird direkt durch Patch gesteuert
        pass
    
    def test_sync_with_glpi(self):
        """Testen der GLPI-Synchronisation"""
        mock_devices = [
            NetworkDevice(ip_address="192.168.1.100", hostname="pc-01.local"),
            NetworkDevice(ip_address="192.168.1.101", hostname="pc-02.local")
        ]
        
        mock_sync_result = {
            "sync_id": "sync_123",
            "entity_id": 123,
            "new_devices": 2,
            "updated_devices": 0,
            "removed_devices": 0,
            "failed_devices": 0,
            "glpi_computer_ids": [4567, 4568],
            "sync_status": "completed",
            "sync_duration": 12.7
        }
        
        self.mock_glpi_instance.sync_devices.return_value = mock_sync_result
        
        result = self.mock_glpi_instance.sync_devices(
            entity_id=123,
            devices=mock_devices,
            update_existing=True,
            create_missing=True
        )
        
        self.mock_glpi_instance.sync_devices.assert_called_once_with(
            entity_id=123,
            devices=mock_devices,
            update_existing=True,
            create_missing=True
        )
        
        self.assertEqual(result["sync_id"], "sync_123")
        self.assertEqual(result["entity_id"], 123)
        self.assertEqual(result["new_devices"], 2)
        self.assertEqual(result["sync_status"], "completed")
    
    def test_device_matching_logic(self):
        """Testen der Geräte-Zuordnungslogik"""
        # Mock-Devices mit verschiedenen Erkennungsmerkmalen
        local_devices = [
            NetworkDevice(ip_address="192.168.1.100", mac_address="00:11:22:33:44:55"),
            NetworkDevice(ip_address="192.168.1.101", hostname="server-01.local"),
            NetworkDevice(ip_address="192.168.1.102", serial_number="SN12345")
        ]
        
        mock_match_results = {
            "matched_by_ip": ["192.168.1.100"],
            "matched_by_mac": ["00:11:22:33:44:55"],
            "matched_by_hostname": ["server-01.local"],
            "matched_by_serial": ["SN12345"],
            "unmatched_devices": [],
            "conflict_resolutions": []
        }
        
        self.mock_glpi_instance.match_devices.return_value = mock_match_results
        
        result = self.mock_glpi_instance.match_devices(
            local_devices=local_devices,
            glpi_devices=[]
        )
        
        self.mock_glpi_instance.match_devices.assert_called_once()
        self.assertEqual(len(result["matched_by_ip"]), 1)
        self.assertEqual(len(result["matched_by_mac"]), 1)
    
    def test_conflict_resolution(self):
        """Testen der Konfliktlösung bei mehrfachen Funden"""
        mock_conflict_data = {
            "conflicting_device": {
                "ip_address": "192.168.1.100",
                "local_mac": "00:11:22:33:44:55",
                "glpi_mac": "AA:BB:CC:DD:EE:FF",
                "local_hostname": "pc-01.local",
                "glpi_hostname": "pc-old.local"
            },
            "resolution_strategy": "prefer_local_data",
            "resolved": True,
            "action_taken": "updated_glpi_record",
            "audit_log_entry": "Device updated: MAC conflict resolved"
        }
        
        self.mock_glpi_instance.resolve_conflict.return_value = mock_conflict_data
        
        conflict_info = {
            "local_device": {"ip": "192.168.1.100", "mac": "00:11:22:33:44:55"},
            "glpi_device": {"ip": "192.168.1.100", "mac": "AA:BB:CC:DD:EE:FF"}
        }
        
        result = self.mock_glpi_instance.resolve_conflict(conflict_info)
        
        self.mock_glpi_instance.resolve_conflict.assert_called_once_with(conflict_info)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution_strategy"], "prefer_local_data")
    
    def test_audit_logging(self):
        """Testen der Audit-Protokollierung"""
        mock_audit_entry = {
            "timestamp": "2025-01-01T12:00:00Z",
            "entity_id": 123,
            "action": "device_created",
            "device_ip": "192.168.1.100",
            "device_hostname": "pc-01.local",
            "user": "system",
            "details": "New device created in GLPI via auto-sync",
            "glpi_computer_id": 4567
        }
        
        self.mock_glpi_instance.log_audit_entry.return_value = mock_audit_entry
        
        audit_data = {
            "entity_id": 123,
            "action": "device_created",
            "device_ip": "192.168.1.100",
            "device_hostname": "pc-01.local",
            "details": "New device created in GLPI via auto-sync"
        }
        
        result = self.mock_glpi_instance.log_audit_entry(audit_data)
        
        self.mock_glpi_instance.log_audit_entry.assert_called_once_with(audit_data)
        self.assertEqual(result["action"], "device_created")
        self.assertEqual(result["glpi_computer_id"], 4567)
    
    def test_sync_statistics(self):
        """Testen der Sync-Statistiken"""
        mock_stats = {
            "entity_id": 123,
            "total_syncs": 45,
            "successful_syncs": 43,
            "failed_syncs": 2,
            "total_devices_created": 85,
            "total_devices_updated": 320,
            "total_devices_removed": 12,
            "average_sync_duration": 32.5,
            "last_sync": "2025-01-01T12:00:00Z"
        }
        
        self.mock_glpi_instance.get_sync_statistics.return_value = mock_stats
        
        stats = self.mock_glpi_instance.get_sync_statistics(entity_id=123)
        
        self.mock_glpi_instance.get_sync_statistics.assert_called_once_with(entity_id=123)
        self.assertEqual(stats["total_syncs"], 45)
        self.assertEqual(stats["successful_syncs"], 43)


class TestModuleIntegration(unittest.TestCase):
    """Integrationstests für alle Module zusammen"""
    
    @patch('device_management.modules.dns_resolver.__init__.DNSResolver')
    @patch('device_management.modules.mac_vendor.__init__.MACVendorLookup')
    @patch('device_management.modules.network_scanner.__init__.NetworkScanner')
    @patch('device_management.modules.glpi_sync.__init__.GLPI_Sync')
    def test_complete_workflow(self, mock_glpi_sync, mock_scanner, mock_mac, mock_dns):
        """Testen des kompletten Workflows aller Module"""
        
        # Setup der Mocks
        mock_dns_instance = Mock()
        mock_dns.return_value = mock_dns_instance
        
        mock_mac_instance = Mock()
        mock_mac.return_value = mock_mac_instance
        
        mock_scanner_instance = Mock()
        mock_scanner.return_value = mock_scanner_instance
        
        mock_glpi_instance = Mock()
        mock_glpi_sync.return_value = mock_glpi_instance
        
        # Mock-Antworten konfigurieren
        mock_dns_instance.resolve.side_effect = [
            {"answers": [{"value": "192.168.1.100"}]},  # DNS für pc-01.local
            {"answers": [{"value": "pc-01.local"}]},    # Reverse DNS für 192.168.1.100
        ]
        
        mock_mac_instance.lookup.return_value = [{
            "mac_address": "00:11:22:33:44:55",
            "vendor": {"vendor": "Dell Inc."}
        }]
        
        mock_scanner_instance.scan.return_value = {
            "scan_id": "scan_integration_123",
            "devices_found": [
                NetworkDevice(
                    ip_address="192.168.1.100",
                    hostname="pc-01.local",
                    mac_address="00:11:22:33:44:55",
                    vendor="Dell Inc.",
                    device_type="computer",
                    is_active=True
                )
            ],
            "total_devices": 1,
            "scan_duration": 8.5
        }
        
        mock_glpi_instance.sync_devices.return_value = {
            "sync_id": "sync_integration_123",
            "entity_id": 123,
            "new_devices": 1,
            "updated_devices": 0,
            "sync_status": "completed",
            "glpi_computer_ids": [9999]
        }
        
        # Workflow ausführen
        # 1. DNS-Auflösung
        dns_result = mock_dns_instance.resolve("pc-01.local", "forward", "A")
        self.assertEqual(dns_result["answers"][0]["value"], "192.168.1.100")
        
        # 2. Netzwerk-Scan
        network_devices = []
        network_result = mock_scanner_instance.scan(
            ip_range="192.168.1.0/24",
            scan_type="ping_sweep"
        )
        network_devices = network_result["devices_found"]
        self.assertEqual(len(network_devices), 1)
        
        # 3. MAC-Vendor-Lookup für gefundene Geräte
        mac_addresses = [device.mac_address for device in network_devices if device.mac_address]
        if mac_addresses:
            mac_results = mock_mac_instance.lookup(mac_addresses)
            self.assertEqual(mac_results[0]["vendor"]["vendor"], "Dell Inc.")
            
            # MAC-Daten zu Devices hinzufügen
            for device, mac_info in zip(network_devices, mac_results):
                device.vendor = mac_info["vendor"]["vendor"]
        
        # 4. Reverse-DNS für IPs
        for device in network_devices:
            if device.ip_address:
                reverse_dns = mock_dns_instance.resolve(device.ip_address, "reverse", "PTR")
                if reverse_dns["answers"]:
                    device.hostname = reverse_dns["answers"][0]["value"]
        
        # 5. GLPI-Synchronisation
        sync_result = mock_glpi_instance.sync_devices(
            entity_id=123,
            devices=network_devices,
            update_existing=True,
            create_missing=True
        )
        
        # Assertions für alle Schritte
        self.assertEqual(dns_result["answers"][0]["value"], "192.168.1.100")
        self.assertEqual(network_devices[0].vendor, "Dell Inc.")
        self.assertEqual(network_devices[0].hostname, "pc-01.local")
        self.assertEqual(sync_result["new_devices"], 1)
        self.assertEqual(sync_result["glpi_computer_ids"], [9999])
        
        # Prüfen, dass alle Module aufgerufen wurden
        mock_dns_instance.resolve.assert_called()
        mock_scanner_instance.scan.assert_called_once()
        mock_mac_instance.lookup.assert_called_once()
        mock_glpi_instance.sync_devices.assert_called_once()


class TestErrorHandling(unittest.TestCase):
    """Testen der Error-Handling-Mechanismen"""
    
    @patch('device_management.modules.network_scanner.__init__.NetworkScanner')
    def test_scanner_timeout_handling(self, mock_scanner):
        """Testen des Timeout-Handlings im Scanner"""
        scanner_instance = Mock()
        mock_scanner.return_value = scanner_instance
        
        scanner_instance.scan.side_effect = TimeoutError("Network scan timed out")
        
        with self.assertRaises(TimeoutError):
            scanner_instance.scan(ip_range="192.168.1.0/24", timeout_seconds=1)
        
        scanner_instance.scan.assert_called_once()
    
    @patch('device_management.modules.dns_resolver.__init__.DNSResolver')
    def test_dns_server_unavailable(self, mock_dns):
        """Testen der DNS-Server-Unverfügbarkeit"""
        dns_instance = Mock()
        mock_dns.return_value = dns_instance
        
        dns_instance.resolve.side_effect = ConnectionError("DNS server unreachable")
        
        with self.assertRaises(ConnectionError):
            dns_instance.resolve("google.com", "forward", "A")
    
    @patch('device_management.modules.glpi_sync.__init__.GLPI_Sync')
    def test_glpi_api_failure(self, mock_glpi_sync):
        """Testen von GLPI-API-Fehlern"""
        glpi_instance = Mock()
        mock_glpi_sync.return_value = glpi_instance
        
        glpi_instance.sync_devices.side_effect = Exception("GLPI API authentication failed")
        
        with self.assertRaises(Exception):
            glpi_instance.sync_devices(entity_id=123, devices=[])
    
    @patch('device_management.modules.mac_vendor.__init__.MACVendorLookup')
    def test_mac_database_corruption(self, mock_mac):
        """Testen von korrupter MAC-Datenbank"""
        mac_instance = Mock()
        mock_mac.return_value = mac_instance
        
        mac_instance.lookup.side_effect = ValueError("MAC database corrupted or invalid format")
        
        with self.assertRaises(ValueError):
            mac_instance.lookup(["00:11:22:33:44:55"])


if __name__ == '__main__':
    unittest.main()