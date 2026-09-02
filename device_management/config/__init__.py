"""
Konfigurationsmodul für Device Management System
"""

from pydantic_settings import BaseSettings
from typing import Optional, Dict, Any
import os


class Settings(BaseSettings):
    """Haupteinstellungen der Anwendung"""
    
    # API Settings
    api_title: str = "Device Management System API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    
    # Database
    database_url: str = "sqlite:///./device_management.db"
    database_test_url: str = "sqlite:///./test_device_management.db"
    
    # Authentication
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # GLPI Configuration
    glpi_base_url: str = "http://localhost/glpi/"
    glpi_app_token: str = ""
    glpi_user_token: str = ""
    
    # OCR Configuration
    ocr_language: str = "deu+eng"
    ocr_engine: str = "tesseract"  # tesseract, paddlocr, ocrmypdf
    ocr_preferred_engine: str = "tesseract"
    ocr_input_watch_path: str = "/mnt/samba/glpi-formulare/eingang"
    ocr_processing_path: str = "/mnt/samba/glpi-formulare/in-bearbeitung"
    ocr_done_path: str = "/mnt/samba/glpi-formulare/erledigt"
    ocr_error_path: str = "/mnt/samba/glpi-formulare/fehler"
    ocr_archive_path: str = "/mnt/samba/glpi-formulare/archiv"
    ocr_template_dir: str = "./ocr_templates"
    
    # Network Scanning
    default_scan_timeout: int = 5
    mac_vendor_db_url: str = "https://standards-oui.ieee.org/oui/oui.txt"
    
    # Security
    enable_audit_log: bool = True
    audit_log_path: str = "./logs/audit.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """Gibt die aktuelle Konfiguration zurück"""
    return Settings()


# Globale Konfigurationsinstanz
settings = get_settings()