"""
Pydantic Schemas für API Requests und Responses
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, validator, Field, HttpUrl


class DeviceBase(BaseModel):
    """Basis-Schema für Geräte"""
    pc_name: str = Field(..., min_length=1, max_length=255, description="PC-Bezeichnung")
    customer_id: str = Field(..., description="Kunden-ID")
    location_id: Optional[str] = None
    user: Optional[str] = Field(None, max_length=255)
    technician: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    serial_number: Optional[str] = Field(None, max_length=255)
    mac_address: Optional[str] = Field(None, max_length=17)
    ip_address: Optional[str] = Field(None, max_length=45)
    operating_system: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    teamviewer_id: Optional[str] = Field(None, max_length=50)
    rustdesk_id: Optional[str] = Field(None, max_length=50)
    netlock_rmm_agent: Optional[bool] = False
    antivirus: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DeviceCreate(DeviceBase):
    """Schema für Geräteerstellung"""
    pass


class DeviceUpdate(BaseModel):
    """Schema für Geräteaktualisierung"""
    pc_name: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_id: Optional[str] = None
    location_id: Optional[str] = None
    user: Optional[str] = Field(None, max_length=255)
    technician: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    serial_number: Optional[str] = Field(None, max_length=255)
    mac_address: Optional[str] = Field(None, max_length=17)
    ip_address: Optional[str] = Field(None, max_length=45)
    operating_system: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    teamviewer_id: Optional[str] = Field(None, max_length=50)
    rustdesk_id: Optional[str] = Field(None, max_length=50)
    netlock_rmm_agent: Optional[bool] = None
    antivirus: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class DeviceResponse(DeviceBase):
    """Schema für Geräteantwort"""
    id: str
    status: str
    source: Optional[str]
    glpi_computer_id: Optional[int]
    glpi_ticket_id: Optional[int]
    sync_status: str
    created_at: datetime
    updated_at: datetime
    last_sync_with_glpi: Optional[datetime]
    
    class Config:
        from_attributes = True


class CustomerBase(BaseModel):
    """Basis-Schema für Kunden"""
    glpi_entity_id: int = Field(..., description="GLPI Entity ID")
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)


class CustomerResponse(CustomerBase):
    """Schema für Kundenantwort"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LocationBase(BaseModel):
    """Basis-Schema für Standorte"""
    glpi_location_id: int = Field(..., description="GLPI Location ID")
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None


class LocationResponse(LocationBase):
    """Schema für Standortantwort"""
    id: str
    customer_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Basis-Schema für Benutzer"""
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    glpi_user_id: Optional[int] = None


class UserCreate(UserBase):
    """Schema für Benutzererstellung"""
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """Schema für Benutzerantwort"""
    id: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema für Authentifizierungstoken"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Daten im JWT Token"""
    username: Optional[str] = None
    user_id: Optional[str] = None
    is_superuser: bool = False


class GLPIEntitySchema(BaseModel):
    """Schema für GLPI Entities"""
    id: int
    name: str
    completename: str
    level: int
    entities_id: Optional[int] = None
    comment: Optional[str] = None


class GLPILocationSchema(BaseModel):
    """Schema für GLPI Locations"""
    id: int
    name: str
    completename: str
    address: Optional[str] = None
    entities_id: int


class GLPIUserSchema(BaseModel):
    """Schema für GLPI Users"""
    id: int
    name: str
    realname: Optional[str] = None
    firstname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    entities_id: int


class FormDocumentBase(BaseModel):
    """Basis-Schema für Formulardokumente"""
    filename: str
    file_type: Optional[str] = None
    template_id: Optional[str] = None


class FormDocumentResponse(FormDocumentBase):
    """Schema für Formulardokumentantwort"""
    id: str
    ocr_status: str
    processing_status: str
    ocr_confidence: Optional[int]
    device_id: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class NetworkScanCreate(BaseModel):
    """Schema für Netzwerkscan-Erstellung"""
    customer_id: str
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    subnet: Optional[str] = None


class NetworkScanResponse(NetworkScanCreate):
    """Schema für Netzwerkscan-Antwort"""
    id: str
    status: str
    devices_found: int = 0
    new_devices: int = 0
    updated_devices: int = 0
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OCRProcessResult(BaseModel):
    """Schema für OCR-Verarbeitungsergebnisse"""
    filename: str
    status: str
    ocr_confidence: Optional[float] = 0.0
    processing_time: Optional[str] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    raw_text_preview: Optional[str] = None
    template_applied: Optional[str] = None
    source_file_url: Optional[str] = None
    source_file_type: Optional[str] = None
    
    class Config:
        from_attributes = True


class OCRTemplateInfo(BaseModel):
    """Schema für OCR-Vorlageninformationen"""
    id: str
    name: str
    description: Optional[str] = None
    field_count: int = 0
    
    class Config:
        from_attributes = True


class OCRProcessingStatus(BaseModel):
    """Schema für OCR-Verarbeitungsstatus"""
    service_running: bool
    total_files_processed: int = 0
    last_updated: str
    available_templates: int = 0
    watch_path: Optional[str] = None
    
    class Config:
        from_attributes = True


class OCRCreateDeviceRequest(BaseModel):
    """Schema für Geräteerstellung aus OCR-Ergebnissen"""
    ocr_result_id: str
    user_data: Dict[str, Any] = Field(default_factory=dict)
    
    @validator("ocr_result_id")
    def validate_ocr_result_id(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("OCR result ID must be a non-empty string")
        return v


class OCRUploadRequest(BaseModel):
    """Schema für OCR-Datei-Upload"""
    template_id: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "template_id": "standard_customer_form"
            }
        }