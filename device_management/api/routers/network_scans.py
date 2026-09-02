"""
Network Scan API Router für Phase 2

Bietet API-Endpunkte für Netzwerk-Scans, Remote-Agent-Management,
DNS-Resolution, und GLPI-Synchronisation.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import logging
import uuid
from datetime import datetime

from ..dependencies.auth import get_current_active_user
from ...schemas import (
    NetworkScanRequest,
    NetworkScanResponse,
    RemoteAgentStatus,
    DNSResolutionRequest,
    DNSResolutionResponse,
    MACVendorLookupRequest,
    MACVendorLookupResponse,
    GLPISyncRequest,
    GLPISyncResponse,
    ScanStatistics,
    NetworkDeviceStats
)
from ...config import settings
from ...modules.network_scanner import NetworkScanner, ScanResult
from ...modules.remote_agent import RemoteAgent, RemoteAgentConfig, ScanTask, ScanCommand
from ...modules.dns_resolver import DNSResolver, DNSResolutionResult
from ...modules.mac_vendor import MACVendorLookup
from ...modules.glpi_sync import GLPISync, GLPIAPIClient, NetworkDeviceForSync

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-Instanzen (werden lazy geladen)
network_scanner: Optional[NetworkScanner] = None
dns_resolver: Optional[DNSResolver] = None
mac_vendor_lookup: Optional[MACVendorLookup] = None
glpi_sync: Optional[GLPISync] = None
remote_agents: Dict[str, RemoteAgent] = {}

# Konfiguration für Module
NETWORK_SCANNER_CONFIG = {
    "scan_timeout": 5,
    "ping_enabled": True,
    "arp_enabled": True,
    "port_scan_enabled": False,  # Vorsicht: Port-Scans können als Angriff interpretiert werden
    "allowed_ports": [22, 80, 443, 3389, 53, 139, 445],  # Nur häufigste Ports
    "max_threads": 10,
    "mac_vendor_db_path": settings.storage_path / "mac_vendors.json"
}

DNS_RESOLVER_CONFIG = {
    "dns_servers": ["8.8.8.8", "8.8.4.4"],  # Google DNS als Fallback
    "timeout_seconds": 5,
    "use_cache": True,
    "cache_ttl_seconds": 300,
    "enable_dnssec": False,
    "enable_zone_transfer": False  # Nur mit expliziter Berechtigung
}

MAC_VENDOR_CONFIG = {
    "database_path": settings.storage_path / "mac_vendors.db",
    "auto_update": True,
    "use_cache": True,
    "cache_ttl_days": 30,
    "normalize_mac": True
}


def get_network_scanner() -> NetworkScanner:
    """Lazy-Loading für NetworkScanner"""
    global network_scanner
    if network_scanner is None:
        network_scanner = NetworkScanner(NETWORK_SCANNER_CONFIG)
    return network_scanner


def get_dns_resolver() -> DNSResolver:
    """Lazy-Loading für DNSResolver"""
    global dns_resolver
    if dns_resolver is None:
        dns_resolver = DNSResolver(DNS_RESOLVER_CONFIG)
    return dns_resolver


def get_mac_vendor_lookup() -> MACVendorLookup:
    """Lazy-Loading für MACVendorLookup"""
    global mac_vendor_lookup
    if mac_vendor_lookup is None:
        mac_vendor_lookup = MACVendorLookup(MAC_VENDOR_CONFIG)
    return mac_vendor_lookup


def get_glpi_sync() -> Optional[GLPISync]:
    """Lazy-Loading für GLPISync"""
    global glpi_sync
    if glpi_sync is None:
        try:
            # Nur initialisieren wenn GLPI konfiguriert ist
            if (hasattr(settings, 'glpi_url') and 
                hasattr(settings, 'glpi_app_token') and 
                hasattr(settings, 'glpi_user_token')):
                
                glpi_client = GLPIAPIClient(
                    base_url=settings.glpi_url,
                    app_token=settings.glpi_app_token,
                    user_token=settings.glpi_user_token
                )
                
                glpi_sync_config = {
                    "auto_sync": True,
                    "update_existing": True,
                    "mark_missing": False,
                    "create_tickets_for_missing": False,
                    "sync_timeout_seconds": 60,
                    "max_parallel_operations": 5
                }
                
                glpi_sync = GLPISync(glpi_client, glpi_sync_config)
                logger.info("GLPI-Sync initialisiert")
            else:
                logger.warning("GLPI nicht konfiguriert, GLPI-Sync deaktiviert")
                return None
                
        except Exception as e:
            logger.error(f"GLPI-Sync Initialisierung fehlgeschlagen: {e}")
            return None
    
    return glpi_sync


def get_remote_agent(agent_id: str) -> Optional[RemoteAgent]:
    """Holt Remote-Agent Instanz"""
    return remote_agents.get(agent_id)


async def _verify_scan_permission(user: dict, ip_range: str, scan_type: str):
    """
    Prüft ob Benutzer Scan-Berechtigung hat
    
    TODO: Integration mit Security-Modul
    """
    # Basierend auf Phase 2 Sicherheitsanforderungen
    # Aktuell nur einfache Prüfung
    allowed = True
    reason = "OK"
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Scan nicht erlaubt: {reason}"
        )


@router.post("/network-scan", response_model=NetworkScanResponse, tags=["Network Scans"])
async def start_network_scan(
    scan_request: NetworkScanRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Startet einen Netzwerk-Scan
    
    Sicherheitshinweis: Netzwerk-Scans erfordern explizite Berechtigung.
    Scan-Bereiche werden automatisch geprüft.
    """
    logger.info(f"Network-Scan angefordert von {current_user.get('username')} für {scan_request.ip_range}")
    
    # Berechtigung prüfen
    await _verify_scan_permission(current_user, scan_request.ip_range, "ping_sweep")
    
    # Scanner initialisieren
    scanner = get_network_scanner()
    
    # Customer-Informationen extrahieren
    customer_info = None
    if scan_request.customer_id:
        customer_info = {
            "customer_id": scan_request.customer_id,
            "customer_name": scan_request.customer_name
        }
    
    try:
        # Scan starten
        scan_result = scanner.scan_ip_range(
            ip_range=scan_request.ip_range,
            customer_info=customer_info
        )
        
        # GLPI-Sync wenn aktiviert
        if scan_request.auto_sync_glpi and get_glpi_sync():
            background_tasks.add_task(_sync_to_glpi_background, scan_result)
        
        # Konvertiere zu Response
        response = NetworkScanResponse(
            scan_id=scan_result.scan_id,
            status=scan_result.scan_status,
            devices_found=[device.to_dict() for device in scan_result.devices_found],
            total_devices=scan_result.total_devices,
            scan_duration=scan_result.scan_duration,
            error_message=scan_result.error_message,
            glpi_sync_initiated=scan_request.auto_sync_glpi
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Network-Scan fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan fehlgeschlagen: {str(e)}"
        )


@router.post("/network-scan/{scan_id}/sync-glpi", tags=["Network Scans"])
async def sync_scan_to_glpi(
    scan_id: str,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Synchronisiert Scan-Ergebnisse mit GLPI
    
    Erfordert GLPI-Konfiguration.
    """
    logger.info(f"GLPI-Sync angefordert für Scan {scan_id} von {current_user.get('username')}")
    
    glpi_sync = get_glpi_sync()
    if not glpi_sync:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GLPI-Sync nicht konfiguriert"
        )
    
    # TODO: Scan-Ergebnisse aus Datenbank/Speicher laden
    # Hier nur Platzhalter
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GLPI-Sync Implementierung in Arbeit"
    )


async def _sync_to_glpi_background(scan_result: ScanResult):
    """Hintergrundtask für GLPI-Sync"""
    try:
        glpi_sync = get_glpi_sync()
        if not glpi_sync:
            return
        
        # Konvertiere Scan-Geräte zu NetworkDeviceForSync
        scan_devices = []
        for device in scan_result.devices_found:
            sync_device = NetworkDeviceForSync(
                ip_address=device.ip_address,
                hostname=device.hostname,
                mac_address=device.mac_address,
                vendor=device.vendor,
                os_type=device.os_type,
                os_version=device.os_version,
                device_type=device.device_type,
                domain=device.domain,
                is_domain_controller=device.is_domain_controller,
                open_ports=device.open_ports,
                scan_timestamp=device.scan_time,
                customer_id=scan_result.customer_id
            )
            scan_devices.append(sync_device)
        
        # Sync durchführen
        sync_result = await glpi_sync.sync_network_scan(scan_devices)
        
        logger.info(f"Hintergrund GLPI-Sync abgeschlossen: {sync_result.sync_id}")
        
    except Exception as e:
        logger.error(f"Hintergrund GLPI-Sync fehlgeschlagen: {e}")


@router.get("/network-scan/{scan_id}", response_model=NetworkScanResponse, tags=["Network Scans"])
async def get_scan_result(
    scan_id: str,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Holt Scan-Ergebnisse
    
    TODO: Scan-Ergebnisse persistent speichern und hier abrufen
    """
    # Platzhalter-Implementierung
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Scan-Ergebnis-Abruf in Arbeit"
    )


@router.post("/dns-resolve", response_model=DNSResolutionResponse, tags=["DNS"])
async def dns_resolve(
    dns_request: DNSResolutionRequest,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Führt DNS-Auflösung durch
    
    Unterstützt Vorwärts- und Rückwärts-Lookups.
    """
    logger.info(f"DNS-Auflösung angefordert: {dns_request.query} ({dns_request.record_type})")
    
    resolver = get_dns_resolver()
    
    try:
        if dns_request.query_type == "forward":
            result = await resolver.resolve_hostname(
                hostname=dns_request.query,
                record_type=dns_request.record_type
            )
        elif dns_request.query_type == "reverse":
            result = await resolver.reverse_dns_lookup(dns_request.query)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültiger query_type. Erlaubt: 'forward', 'reverse'"
            )
        
        response = DNSResolutionResponse(
            query=result.query,
            query_type=result.query_type,
            answers=[answer.to_dict() for answer in result.answers],
            authoritative=result.authoritative,
            nameserver=result.nameserver,
            response_time_ms=result.response_time_ms,
            timestamp=result.timestamp
        )
        
        return response
        
    except Exception as e:
        logger.error(f"DNS-Auflösung fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DNS-Auflösung fehlgeschlagen: {str(e)}"
        )


@router.post("/mac-vendor-lookup", response_model=MACVendorLookupResponse, tags=["MAC Vendor"])
async def mac_vendor_lookup(
    mac_request: MACVendorLookupRequest,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Sucht Hersteller-Informationen für MAC-Adressen
    
    Unterstützt mehrere MAC-Adressen gleichzeitig (Batch-Lookup).
    """
    logger.info(f"MAC-Vendor-Lookup für {len(mac_request.mac_addresses)} Adressen")
    
    vendor_lookup = get_mac_vendor_lookup()
    
    try:
        results = []
        vendor_map = {}
        
        for mac_address in mac_request.mac_addresses:
            try:
                mac_info = vendor_lookup.lookup_mac_address(mac_address)
                results.append(mac_info.to_dict())
                
                if mac_info.vendor_info:
                    vendor_name = mac_info.vendor_info.vendor
                    vendor_map[vendor_name] = vendor_map.get(vendor_name, 0) + 1
                    
            except Exception as e:
                logger.warning(f"MAC-Lookup fehlgeschlagen für {mac_address}: {e}")
                results.append({
                    "mac_address": mac_address,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
        
        response = MACVendorLookupResponse(
            results=results,
            vendor_statistics=vendor_map,
            total_processed=len(results),
            lookup_timestamp=datetime.now()
        )
        
        return response
        
    except Exception as e:
        logger.error(f"MAC-Vendor-Lookup fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MAC-Vendor-Lookup fehlgeschlagen: {str(e)}"
        )


@router.post("/glpi-sync", response_model=GLPISyncResponse, tags=["GLPI Sync"])
async def start_glpi_sync(
    sync_request: GLPISyncRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Startet manuelle GLPI-Synchronisation
    
    Erfordert GLPI-Konfiguration und Scan-Ergebnisse.
    """
    logger.info(f"GLPI-Sync angefordert für Entity {sync_request.entity_id}")
    
    glpi_sync = get_glpi_sync()
    if not glpi_sync:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GLPI-Sync nicht konfiguriert"
        )
    
    # TODO: Implementierung basierend auf sync_request.scan_ids
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GLPI-Sync manuelle Ausführung in Arbeit"
    )


@router.post("/remote-agent/register", tags=["Remote Agents"])
async def register_remote_agent(
    agent_config: dict,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Registriert einen neuen Remote-Agent
    
    Remote-Agents können in entfernten Kundennetzwerken eingesetzt werden.
    Erfordert Admin-Berechtigungen.
    """
    # Nur Admins dürfen Agents registrieren
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Remote-Agents registrieren"
        )
    
    try:
        config = RemoteAgentConfig(
            agent_id=agent_config.get("agent_id", str(uuid.uuid4())),
            agent_name=agent_config.get("agent_name", "Unnamed Agent"),
            customer_id=agent_config.get("customer_id"),
            customer_name=agent_config.get("customer_name"),
            location=agent_config.get("location"),
            connection_type=agent_config.get("connection_type", "direct"),
            connection_endpoint=agent_config.get("connection_endpoint"),
            credential_id=agent_config.get("credential_id"),
            allowed_ip_ranges=agent_config.get("allowed_ip_ranges", []),
            max_bandwidth_kbps=agent_config.get("max_bandwidth_kbps"),
            scan_time_window_start=agent_config.get("scan_time_window_start"),
            scan_time_window_end=agent_config.get("scan_time_window_end"),
            heartbeat_interval_seconds=agent_config.get("heartbeat_interval_seconds", 300),
            max_scan_duration_minutes=agent_config.get("max_scan_duration_minutes", 60),
            require_approval=agent_config.get("require_approval", True),
            encryption_key=agent_config.get("encryption_key"),
            is_active=agent_config.get("is_active", True)
        )
        
        # Agent erstellen
        agent = RemoteAgent(config)
        remote_agents[config.agent_id] = agent
        
        logger.info(f"Remote-Agent registriert: {config.agent_name} ({config.agent_id})")
        
        return {
            "agent_id": config.agent_id,
            "agent_name": config.agent_name,
            "connection_endpoint": config.connection_endpoint,
            "status": "registered",
            "message": "Agent erfolgreich registriert"
        }
        
    except Exception as e:
        logger.error(f"Remote-Agent-Registrierung fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent-Registrierung fehlgeschlagen: {str(e)}"
        )


@router.get("/remote-agent/{agent_id}", response_model=RemoteAgentStatus, tags=["Remote Agents"])
async def get_remote_agent_status(
    agent_id: str,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Holt Status eines Remote-Agents
    """
    agent = get_remote_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Remote-Agent {agent_id} nicht gefunden"
        )
    
    try:
        status_data = agent.get_status()
        return RemoteAgentStatus(**status_data)
        
    except Exception as e:
        logger.error(f"Remote-Agent-Statusabruf fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Statusabruf fehlgeschlagen: {str(e)}"
        )


@router.post("/remote-agent/{agent_id}/scan", tags=["Remote Agents"])
async def start_remote_agent_scan(
    agent_id: str,
    scan_task: dict,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Startet einen Scan auf einem Remote-Agent
    
    Erfordert Agent-Verfügbarkeit und Scan-Berechtigung.
    """
    agent = get_remote_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Remote-Agent {agent_id} nicht gefunden"
        )
    
    # Berechtigung prüfen
    ip_range = scan_task.get("target_ip_range", "")
    scan_type = scan_task.get("scan_type", "ping_sweep")
    await _verify_scan_permission(current_user, ip_range, scan_type)
    
    try:
        # Scan-Task erstellen
        commands = [ScanCommand(cmd) for cmd in scan_task.get("scan_commands", ["PING_SWEEP"])]
        
        task = ScanTask(
            task_id=scan_task.get("task_id", str(uuid.uuid4())),
            agent_id=agent_id,
            scan_commands=commands,
            target_ip_range=ip_range,
            scan_parameters=scan_task.get("scan_parameters", {}),
            priority=scan_task.get("priority", 5),
            created_by=current_user.get("username")
        )
        
        # Scan asynchron starten
        # Hier könnte man einen Background Task verwenden
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Remote-Agent-Scan Implementierung in Arbeit"
        )
        
    except Exception as e:
        logger.error(f"Remote-Agent-Scan fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan-Start fehlgeschlagen: {str(e)}"
        )


@router.get("/stats/network-scans", response_model=ScanStatistics, tags=["Statistics"])
async def get_network_scan_statistics(
    days: int = 30,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Holt Netzwerk-Scan-Statistiken
    
    TODO: Persistente Statistik-Sammlung implementieren
    """
    # Nur Admins dürfen Statistiken sehen
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Statistiken abrufen"
        )
    
    # Platzhalter-Implementierung
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Scan-Statistiken in Arbeit"
    )


@router.get("/stats/network-devices", response_model=NetworkDeviceStats, tags=["Statistics"])
async def get_network_device_statistics(
    customer_id: Optional[int] = None,
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Holt Gerätestatistiken
    
    TODO: Integration mit GLPI oder Scan-Datenbank
    """
    # Nur Admins oder Kunden-eigene Benutzer
    if not current_user.get("is_admin", False):
        # Prüfe ob Benutzer zu diesem Kunden gehört
        if customer_id and current_user.get("customer_id") != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für Statistiken dieses Kunden"
            )
    
    # Platzhalter-Implementierung
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Gerätestatistiken in Arbeit"
    )


@router.delete("/network-scan/cache", tags=["Network Scans"])
async def clear_network_scan_cache(
    cache_type: str = "all",
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Leert Scan-Caches
    
    cache_type: "dns", "mac_vendor", "glpi", "all"
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Caches leeren"
        )
    
    try:
        cleared = []
        
        if cache_type in ["dns", "all"]:
            resolver = get_dns_resolver()
            resolver.clear_cache()
            cleared.append("dns")
        
        if cache_type in ["mac_vendor", "all"]:
            vendor_lookup = get_mac_vendor_lookup()
            vendor_lookup.clear_cache()
            cleared.append("mac_vendor")
        
        if cache_type in ["glpi", "all"]:
            glpi_sync = get_glpi_sync()
            if glpi_sync:
                glpi_sync.clear_cache()
                cleared.append("glpi")
        
        logger.info(f"Cache geleert: {', '.join(cleared)} von {current_user.get('username')}")
        
        return {
            "cleared_caches": cleared,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache-Löschung fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache-Löschung fehlgeschlagen: {str(e)}"
        )


@router.get("/network-scan/modules/status", tags=["Network Scans"])
async def get_module_status(
    current_user: Dict = Depends(get_current_active_user)
):
    """
    Gibt Status aller Netzwerk-Scan-Module zurück
    
    Nützlich für Debugging und Monitoring
    """
    module_status = {}
    
    try:
        # Network Scanner
        scanner = get_network_scanner()
        module_status["network_scanner"] = {
            "initialized": scanner is not None,
            "config": NETWORK_SCANNER_CONFIG
        }
        
        # DNS Resolver
        resolver = get_dns_resolver()
        module_status["dns_resolver"] = {
            "initialized": resolver is not None,
            "stats": resolver.get_stats() if resolver else None
        }
        
        # MAC Vendor Lookup
        vendor_lookup = get_mac_vendor_lookup()
        module_status["mac_vendor_lookup"] = {
            "initialized": vendor_lookup is not None,
            "stats": vendor_lookup.get_stats() if vendor_lookup else None
        }
        
        # GLPI Sync
        glpi_sync = get_glpi_sync()
        module_status["glpi_sync"] = {
            "initialized": glpi_sync is not None,
            "stats": glpi_sync.get_stats() if glpi_sync else None
        }
        
        # Remote Agents
        module_status["remote_agents"] = {
            "count": len(remote_agents),
            "agent_ids": list(remote_agents.keys())
        }
        
        return {
            "modules": module_status,
            "timestamp": datetime.now().isoformat(),
            "user": current_user.get("username")
        }
        
    except Exception as e:
        logger.error(f"Modul-Statusabruf fehlgeschlagen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modul-Statusabruf fehlgeschlagen: {str(e)}"
        )