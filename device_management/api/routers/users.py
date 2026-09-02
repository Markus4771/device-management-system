"""
Users Router für Benutzerverwaltung (Admin)
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import logging

from ...models import User
from ..schemas import UserResponse
from ..dependencies import get_current_superuser
from ..dependencies.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/users", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)
):
    """
    Ruft alle Benutzer ab (nur für Admin).
    """
    query = db.query(User)
    
    if active_only:
        query = query.filter(User.is_active == True)
    
    users = query.offset(skip).limit(limit).all()
    return users


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)
):
    """
    Ruft einen spezifischen Benutzer ab (nur für Admin).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )
    
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    update_data: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)
):
    """
    Aktualisiert einen Benutzer (nur für Admin).
    
    Erlaubte Felder:
    - full_name
    - email
    - is_active
    - is_superuser
    - glpi_user_id
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )
    
    allowed_fields = {"full_name", "email", "is_active", "is_superuser", "glpi_user_id"}
    
    update_dict = {}
    for field, value in update_data.items():
        if field in allowed_fields:
            update_dict[field] = value
    
    # Email uniqueness check
    if "email" in update_dict:
        existing_user = db.query(User).filter(
            User.email == update_dict["email"],
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email bereits vergeben"
            )
    
    for field, value in update_dict.items():
        setattr(user, field, value)
    
    from datetime import datetime
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    logger.info(f"User {user_id} updated by admin {current_user.username}")
    
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)
):
    """
    Löscht einen Benutzer (nur für Admin).
    
    Achtung: Eigener Account kann nicht gelöscht werden.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eigener Account kann nicht gelöscht werden"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )
    
    # Soft Delete (is_active = False)
    user.is_active = False
    from datetime import datetime
    user.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"User {user_id} deactivated by admin {current_user.username}")
    
    return {"message": "Benutzer erfolgreich deaktiviert"}


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_superuser)
):
    """
    Reaktiviert einen deaktivierten Benutzer (nur für Admin).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )
    
    user.is_active = True
    from datetime import datetime
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    logger.info(f"User {user_id} reactivated by admin {current_user.username}")
    
    return {
        "message": "Benutzer erfolgreich reaktiviert",
        "user": UserResponse.from_orm(user)
    }