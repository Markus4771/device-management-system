"""
Customers Router für Kundenverwaltung
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import logging

from ...models import Customer, Location
from ..schemas import CustomerResponse
from ..dependencies import get_current_active_user, get_current_superuser
from ..dependencies.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/customers", response_model=List[CustomerResponse])
async def get_customers(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft alle Kunden ab.
    """
    customers = db.query(Customer).all()
    return customers


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft einen spezifischen Kunden anhand der ID ab.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kunde nicht gefunden"
        )
    
    return customer


@router.get("/customers/{customer_id}/locations", response_model=List[dict])
async def get_customer_locations(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Ruft alle Standorte eines Kunden ab.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kunde nicht gefunden"
        )
    
    locations = db.query(Location).filter(Location.customer_id == customer_id).all()
    
    return [
        {
            "id": loc.id,
            "glpi_location_id": loc.glpi_location_id,
            "name": loc.name,
            "address": loc.address
        }
        for loc in locations
    ]


@router.post("/customers/sync-from-glpi")
async def sync_customers_from_glpi(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)  # Nur Superuser kann synchronisieren
):
    """
    Synchronisiert Kunden von GLPI.
    
    Ruft alle Entities von GLPI ab und aktualisiert die lokale Datenbank.
    """
    try:
        from ...modules.glpi_connector.api_client import GLPIAPIClient
        
        with GLPIAPIClient() as glpi_client:
            if not glpi_client.session_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="GLPI-Konnektivität fehlgeschlagen"
                )
            
            # GLPI Entities abrufen
            glpi_entities = glpi_client.get_entities(recursive=True)
            
            if not glpi_entities:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Keine Entities von GLPI erhalten"
                )
            
            updated_count = 0
            created_count = 0
            
            for glpi_entity in glpi_entities:
                if not isinstance(glpi_entity, dict):
                    continue
                
                glpi_id = glpi_entity.get("id")
                name = glpi_entity.get("name")
                completename = glpi_entity.get("completename")
                
                if not glpi_id or not name:
                    continue
                
                # Prüfen ob Kunde bereits existiert
                existing_customer = db.query(Customer).filter(
                    Customer.glpi_entity_id == glpi_id
                ).first()
                
                if existing_customer:
                    # Update
                    existing_customer.name = name
                    existing_customer.glpi_data = glpi_entity
                    updated_count += 1
                else:
                    # Create
                    new_customer = Customer(
                        glpi_entity_id=glpi_id,
                        name=name,
                        glpi_data=glpi_entity,
                        code=f"GLPI-{glpi_id}"
                    )
                    db.add(new_customer)
                    created_count += 1
            
            db.commit()
            
            logger.info(f"Customers synced from GLPI: {created_count} created, {updated_count} updated")
            
            return {
                "message": "Kunden erfolgreich von GLPI synchronisiert",
                "created": created_count,
                "updated": updated_count,
                "total": len(glpi_entities)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing customers from GLPI: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler bei GLPI-Synchronisation: {str(e)}"
        )