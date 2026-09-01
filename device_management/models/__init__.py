"""
Datenmodelle für Device Management System
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    """Benutzermodell für lokale Authentifizierung"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Beziehung zu GLPI User ID
    glpi_user_id = Column(Integer, nullable=True)


class Customer(Base):
    """Kunden (Entities aus GLPI)"""
    __tablename__ = "customers"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    glpi_entity_id = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100))
    address = Column(Text)
    phone = Column(String(50))
    email = Column(String(255))
    glpi_data = Column(JSON)  # Original GLPI Daten
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Beziehungen
    devices = relationship("Device", back_populates="customer")
    locations = relationship("Location", back_populates="customer")


class Location(Base):
    """Standorte aus GLPI"""
    __tablename__ = "locations"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    glpi_location_id = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    address = Column(Text)
    glpi_data = Column(JSON)
    
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Beziehungen
    customer = relationship("Customer", back_populates="locations")
    devices = relationship("Device", back_populates="location")


class Device(Base):
    """Gerätemodell mit GLPI-Synchronisation"""
    __tablename__ = "devices"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    # GLPI IDs
    glpi_computer_id = Column(Integer, nullable=True, unique=True)
    glpi_ticket_id = Column(Integer, nullable=True)
    
    # Grunddaten
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False)
    location_id = Column(String(36), ForeignKey("locations.id"), nullable=True)
    
    # Geräteinformationen
    pc_name = Column(String(255), nullable=False)
    user = Column(String(255))
    technician = Column(String(255))
    manufacturer = Column(String(255))
    model = Column(String(255))
    serial_number = Column(String(255))
    mac_address = Column(String(17))  # Format: AA:BB:CC:DD:EE:FF
    ip_address = Column(String(45))  # IPv4 oder IPv6
    operating_system = Column(String(255))
    domain = Column(String(255))  # Domain oder Arbeitsgruppe
    teamviewer_id = Column(String(50))
    rustdesk_id = Column(String(50))
    netlock_rmm_agent = Column(Boolean, default=False)
    antivirus = Column(String(255))
    notes = Column(Text)
    
    # Custom fields (erweiterbar)
    custom_fields = Column(JSON, default=dict)
    
    # Status und Metadaten
    status = Column(String(50), default="active")  # active, inactive, archived
    source = Column(String(50))  # manual, ocr, network_scan
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_sync_with_glpi = Column(DateTime, nullable=True)
    sync_status = Column(String(50), default="pending")  # pending, synced, error
    
    # Beziehungen
    customer = relationship("Customer", back_populates="devices")
    location = relationship("Location", back_populates="devices")
    creator = relationship("User")


class FormDocument(Base):
    """Gescannte Formulardokumente"""
    __tablename__ = "form_documents"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    original_path = Column(String(500))
    file_type = Column(String(10))  # pdf, jpg, png
    file_size = Column(Integer)  # Größe in Bytes
    
    # OCR-Ergebnisse
    ocr_status = Column(String(50), default="pending")  # pending, processing, completed, error
    ocr_text = Column(Text)
    ocr_confidence = Column(Integer)  # Durchschnittliches Konfidenzniveau 0-100
    extracted_data = Column(JSON)  # Strukturierte extrahierte Daten
    
    # Formularvorlage
    template_id = Column(String(36), ForeignKey("form_templates.id"), nullable=True)
    
    # Verarbeitungsstatus
    processing_status = Column(String(50), default="received")  # received, reviewing, approved, rejected
    review_notes = Column(Text)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    
    # Gerätezuordnung
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FormTemplate(Base):
    """Vorlagen für verschiedene Kundenformulare"""
    __tablename__ = "form_templates"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    
    # OCR-Konfiguration
    field_mappings = Column(JSON)  # Mapping von OCR-Positionen zu Datenfeldern
    validation_rules = Column(JSON)  # Validierungsregeln für extrahierte Daten
    sample_image_path = Column(String(500))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NetworkScan(Base):
    """Netzwerkscans"""
    __tablename__ = "network_scans"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False)
    range_start = Column(String(45))
    range_end = Column(String(45))
    subnet = Column(String(45))
    
    # Scan-Ergebnisse
    devices_found = Column(Integer, default=0)
    new_devices = Column(Integer, default=0)
    updated_devices = Column(Integer, default=0)
    scan_data = Column(JSON)  # Rohdaten des Scans
    
    # Status und Metadaten
    status = Column(String(50), default="pending")  # pending, running, completed, error
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    initiated_by = Column(String(36), ForeignKey("users.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Audit-Log für Sicherheitsprotokollierung"""
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(36))
    details = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    
    created_at = Column(DateTime, default=datetime.utcnow)