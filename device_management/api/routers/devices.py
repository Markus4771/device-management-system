"""
Devices Router für Geräteverwaltung
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from ...models import Device, Customer
from ..schemas import DeviceResponse, DeviceCreate, DeviceUpdate
from ..services import DeviceService
from ..dependencies import get_current_active_user, get_current_superuser
from ..dependencies.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Erstellt ein neues Gerät.
    
    Die MAC-Adresse wird automatisch ins Format AA:BB:CC:DD:EE:FF normalisiert.
    IP-Adressen werden validiert. Ungültige Eingaben werden ignoriert.
    """
    try:
        device = DeviceService.create_device(db, device_data, current_user.id)
        return device
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating device: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interner Fehler beim Erstellen des Geräts"
        )


@router.get("/devices", response_model=List[DeviceResponse])
async def get_devices(
    customer_id: Optional[str] = Query(None, description="Filter nach Kunden-ID"),
    search: Optional[str] = Query(None, description="Suchbegriff für PC-Name, Seriennummer, MAC..."),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft alle Geräte ab (mit Filtermöglichkeiten).
    
    - `customer_id`: Filtert nach spezifischem Kunden
    - `search`: Sucht in PC-Name, Seriennummer, MAC-Adresse, Benutzer, Techniker
    - `skip`: Anzahl der übersprungenen Ergebnisse (Pagination)
    - `limit`: Maximale Anzahl der zurückgegebenen Ergebnisse
    """
    try:
        query = db.query(Device).filter(Device.status == "active")
        
        if customer_id:
            # Prüfen ob Kunde existiert
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Kunde nicht gefunden"
                )
            query = query.filter(Device.customer_id == customer_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Device.pc_name.ilike(search_term)) |
                (Device.serial_number.ilike(search_term)) |
                (Device.mac_address.ilike(search_term)) |
                (Device.user.ilike(search_term)) |
                (Device.technician.ilike(search_term)) |
                (Device.ip_address.ilike(search_term))
            )
        
        devices = query.offset(skip).limit(limit).all()
        return devices
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interner Fehler beim Abrufen der Geräte"
        )


@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft ein spezifisches Gerät anhand der ID ab.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gerät nicht gefunden"
        )
    
    # Prüfen ob Benutzer Zugriff auf diesen Kunden hat
    # (Hier könnte zusätzliche Autorisierung implementiert werden)
    
    return device


@router.put("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Aktualisiert ein vorhandenes Gerät.
    """
    try:
        device = DeviceService.update_device(db, device_id, device_data, current_user.id)
        return device
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interner Fehler beim Aktualisieren des Geräts"
        )


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)  # Nur Superuser können löschen
):
    """
    Löscht ein Gerät (Soft Delete).
    
    Das Gerät wird nicht physisch gelöscht, sondern als "archived" markiert.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gerät nicht gefunden"
        )
    
    device.status = "archived"
    device.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"Device {device_id} archived by user {current_user.username}")
    
    return {"message": "Gerät erfolgreich archiviert"}


@router.get("/customers/{customer_id}/devices", response_model=List[DeviceResponse])
async def get_customer_devices(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft alle Geräte eines spezifischen Kunden ab.
    """
    # Prüfen ob Kunde existiert
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kunde nicht gefunden"
        )
    
    devices = DeviceService.get_devices_by_customer(db, customer_id)
    return devices


@router.post("/devices/{device_id}/sync-glpi")
async def sync_device_with_glpi(
    device_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Startet eine manuelle GLPI-Synchronisation für ein Gerät.
    
    Diese Endpoint kann normalerweise automatisch aufgerufen werden,
    ermöglicht aber manuelle Synchronisation bei Bedarf.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gerät nicht gefunden"
        )
    
    customer = db.query(Customer).filter(Customer.id == device.customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde für dieses Gerät nicht gefunden"
        )
    
    # Hier würden wir einen Celery Task starten
    # Für jetzt simulieren wir die Synchronisation
    from datetime import datetime
    device.sync_status = "syncing"
    device.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"GLPI sync started for device {device_id} by user {current_user.username}")
    
    return {
        "message": "GLPI-Synchronisation gestartet",
        "device_id": device_id,
        "sync_status": "syncing"
    }