"""
Authentication Router für Benutzer-Login und Token-Verwaltung
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import jwt as pyjwt
from passlib.context import CryptContext
import logging

from ...config import settings
from ...models import User
from ..schemas import UserCreate, UserResponse, Token, TokenData
from ..dependencies import get_current_user
from ..dependencies.database import get_db as db_dep

logger = logging.getLogger(__name__)

router = APIRouter()

# Passwort-Hashing Kontext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Überprüft ein Passwort gegen den Hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Erzeugt einen Passwort-Hash."""
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authentifiziert einen Benutzer."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Erstellt ein JWT Access Token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm
    )
    return encoded_jwt


@router.post("/login", response_model=Token, tags=["Authentication"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(db_dep)
):
    """
    Authentifiziert einen Benutzer und gibt ein JWT Token zurück.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falscher Benutzername oder Passwort",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "is_superuser": user.is_superuser
        },
        expires_delta=access_token_expires
    )
    
    logger.info(f"User {user.username} logged in successfully")
    return {"access_token": access_token, "token_type": "bearer", "expires_in": settings.access_token_expire_minutes * 60}


@router.post("/register", response_model=UserResponse, tags=["Authentication"])
async def register_user(
    user_data: UserCreate,
    db: Session = Depends(db_dep)
):
    """
    Registriert einen neuen Benutzer.
    """
    # Prüfen ob Benutzername bereits existiert
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzername bereits vergeben"
        )
    
    # Prüfen ob Email bereits existiert
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email bereits registriert"
        )
    
    # Benutzer erstellen
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        glpi_user_id=user_data.glpi_user_id,
        is_active=True,
        is_superuser=False
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"New user registered: {db_user.username}")
    return db_user


@router.get("/me", response_model=UserResponse, tags=["Authentication"])
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Gibt die Daten des aktuell authentifizierten Benutzers zurück.
    """
    return current_user


@router.post("/logout", tags=["Authentication"])
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout-Endpoint (client-seitiges Token-Löschen).
    """
    logger.info(f"User {current_user.username} logged out")
    return {"message": "Successfully logged out"}


@router.put("/me", response_model=UserResponse, tags=["Authentication"])
async def update_user(
    user_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(db_dep)
):
    """
    Aktualisiert die Daten des aktuellen Benutzers.
    """
    allowed_fields = {"full_name", "email"}
    
    update_data = {}
    for field, value in user_data.items():
        if field in allowed_fields:
            update_data[field] = value
    
    if "email" in update_data:
        # Prüfen ob neue Email bereits existiert
        existing_email = db.query(User).filter(
            User.email == update_data["email"],
            User.id != current_user.id
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email bereits registriert"
            )
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"User {current_user.username} updated their profile")
    return current_user


@router.post("/change-password", tags=["Authentication"])
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(db_dep)
):
    """
    Ändert das Passwort des aktuellen Benutzers.
    """
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Altes Passwort ist falsch"
        )
    
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Neues Passwort muss mindestens 8 Zeichen lang sein"
        )
    
    current_user.hashed_password = get_password_hash(new_password)
    current_user.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"User {current_user.username} changed their password")
    return {"message": "Passwort erfolgreich geändert"}