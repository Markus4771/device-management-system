"""
GLPI Router für direkte GLPI-API Zugriffe
"""

from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from ...modules.glpi_connector.api_client import GLPIAPIClient
from ..dependencies import get_current_active_user, get_current_superuser
from ..schemas import GLPIEntitySchema, GLPILocationSchema, GLPIUserSchema

logger = logging.getLogger(__name__)

router = APIRouter()

from pydantic import BaseModel, Field

class GLPIComputerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    entities_id: int
    serial: Optional[str] = None
    otherserial: Optional[str] = None
    locations_id: Optional[int] = None
    comment: Optional[str] = None
    contact: Optional[str] = None
    contact_num: Optional[str] = None
    operatingsystems_id: Optional[int] = None


@router.post("/glpi/computers")
async def create_glpi_computer(data: GLPIComputerCreateRequest):
    """Legt einen Computer direkt in GLPI an."""
    try:
        with GLPIAPIClient() as client:
            if not client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="GLPI-Verbindung fehlgeschlagen",
                )
            computer_data = data.model_dump(exclude_none=True)
            computer_id = client.create_computer(computer_data)
            if not computer_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Computer konnte in GLPI nicht angelegt werden",
                )
            return {
                "success": True,
                "glpi_computer_id": computer_id,
                "message": "Computer erfolgreich in GLPI angelegt.",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GLPI computer creation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GLPI-Computer konnte nicht angelegt werden: {exc}",
        )




@router.get("/glpi/status")
async def glpi_status():
    """Prüft die konfigurierte GLPI-Verbindung."""
    try:
        with GLPIAPIClient() as client:
            if not client.session_token:
                return {"connected": False, "message": "GLPI nicht erreichbar"}
            entities = client.get_entities(recursive=False)
            return {
                "connected": True,
                "message": "GLPI verbunden",
                "entities_count": len(entities or []),
            }
    except Exception as exc:
        logger.error("GLPI status check failed: %s", exc)
        return {"connected": False, "message": "GLPI nicht erreichbar"}


@router.get("/glpi/entities", response_model=List[GLPIEntitySchema])
async def get_glpi_entities(
    current_user = None
):
    """
    Ruft alle GLPI Entities (Kunden) direkt von GLPI ab.
    
    Diese Endpoint ermöglicht es, die aktuellsten Entity-Daten
    direkt von GLPI zu beziehen, ohne lokale Synchronisation.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            entities = glpi_client.get_entities(recursive=True)
            if not entities:
                return []
            
            # Konvertiere GLPI-Daten in Schema
            result = []
            for entity in entities:
                result.append(GLPIEntitySchema(**entity))
            
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching GLPI entities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der GLPI Entities: {str(e)}"
        )


@router.get("/glpi/locations", response_model=List[GLPILocationSchema])
async def get_glpi_locations(
    entity_id: Optional[int] = Query(None, description="Filter nach GLPI Entity ID"),
    current_user = None
):
    """
    Ruft GLPI Locations (Standorte) direkt von GLPI ab.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            locations = glpi_client.get_locations(entity_id=entity_id)
            if not locations:
                return []
            
            result = []
            for location in locations:
                result.append(GLPILocationSchema(**location))
            
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching GLPI locations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der GLPI Locations: {str(e)}"
        )


@router.get("/glpi/users", response_model=List[GLPIUserSchema])
async def get_glpi_users(
    entity_id: Optional[int] = Query(None, description="Filter nach GLPI Entity ID"),
    current_user = None
):
    """
    Ruft GLPI Users (Benutzer) direkt von GLPI ab.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            users = glpi_client.get_users(entity_id=entity_id)
            if not users:
                return []
            
            result = []
            for user in users:
                result.append(GLPIUserSchema(**user))
            
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching GLPI users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der GLPI Users: {str(e)}"
        )


@router.get("/glpi/technicians", response_model=List[GLPIUserSchema])
async def get_glpi_technicians(
    entity_id: Optional[int] = Query(None, description="Filter nach GLPI Entity ID"),
    current_user = None
):
    """
    Ruft GLPI Technicians (Techniker) direkt von GLPI ab.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            technicians = glpi_client.get_technicians(entity_id=entity_id)
            if not technicians:
                return []
            
            result = []
            for tech in technicians:
                result.append(GLPIUserSchema(**tech))
            
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching GLPI technicians: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der GLPI Technicians: {str(e)}"
        )


@router.get("/glpi/computers/search")
async def search_glpi_computers(
    serial: Optional[str] = Query(None, description="Seriennummer"),
    mac_address: Optional[str] = Query(None, description="MAC-Adresse"),
    pc_name: Optional[str] = Query(None, description="PC-Name"),
    entity_id: Optional[int] = Query(None, description="GLPI Entity ID"),
    current_user = None
):
    """
    Sucht Computer in GLPI basierend auf Suchkriterien.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            search_criteria = {}
            if serial:
                search_criteria["serial"] = serial
            if mac_address:
                search_criteria["otherserial"] = mac_address
            if pc_name:
                search_criteria["name"] = {"searchtype": "contains", "value": pc_name}
            if entity_id:
                search_criteria["entities_id"] = entity_id
            
            computers = glpi_client.search_computers(search_criteria)
            return computers
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching GLPI computers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler bei GLPI-Computersuche: {str(e)}"
        )


@router.post("/glpi/test-connection")
async def test_glpi_connection(
    current_user = Depends(get_current_superuser)  # Nur Admin kann testen
):
    """
    Testet die GLPI-Verbindung und gibt Statusinformationen zurück.
    """
    try:
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            # Einfache API-Abfrage testen
            entities = glpi_client.get_entities(recursive=False)
            
            return {
                "status": "connected",
                "message": "GLPI-Verbindung erfolgreich",
                "entities_count": len(entities) if entities else 0,
                "session_token": glpi_client.session_token[-10:] + "..." if glpi_client.session_token else None
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GLPI connection test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GLPI-Verbindungstest fehlgeschlagen: {str(e)}"
        )