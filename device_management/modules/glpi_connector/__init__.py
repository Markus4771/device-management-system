"""
GLPI API Connector für Device Management System

Dieses Modul stellt eine Schnittstelle zur GLPI REST API bereit.
"""

from typing import Dict, List, Optional, Any
import httpx
from datetime import datetime
from pydantic import BaseModel


class GLPIComputer(BaseModel):
    """GLPI Computer-Objekt"""
    id: Optional[int] = None
    name: str
    serial: Optional[str] = None
    otherserial: Optional[str] = None
    manufacturers_id: Optional[int] = None
    computermodels_id: Optional[int] = None
    entities_id: int
    locations_id: Optional[int] = None
    users_id: Optional[int] = None
    users_id_tech: Optional[int] = None
    contact: Optional[str] = None
    contact_num: Optional[str] = None
    comment: Optional[str] = None
    
    # Network
    networks: Optional[List[Dict]] = None
    
    # OS
    operatingsystems_id: Optional[int] = None
    
    # Custom Fields
    custom_fields: Optional[Dict[str, Any]] = None


class GLPIEntity(BaseModel):
    """GLPI Entity (Kunde)"""
    id: int
    name: str
    level: int
    entities_id: int  # Parent Entity ID
    completename: str
    comment: Optional[str] = None


class GLPILocation(BaseModel):
    """GLPI Location (Standort)"""
    id: int
    name: str
    entities_id: int
    completename: str
    address: Optional[str] = None
    comment: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class GLPIUser(BaseModel):
    """GLPI User"""
    id: int
    name: str
    realname: Optional[str] = None
    firstname: Optional[str] = None
    entities_id: int
    email: Optional[str] = None
    phone: Optional[str] = None
    comment: Optional[str] = None


class GLPITechnician(BaseModel):
    """GLPI Technician"""
    id: int
    name: str
    realname: Optional[str] = None
    firstname: Optional[str] = None
    entities_id: int
    email: Optional[str] = None
    phone: Optional[str] = None