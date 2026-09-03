# Device Management System - Phase 1

Modulare Software zur Erfassung und Verwaltung von Kundengeräten mit GLPI-Integration.

## 📋 Funktionen der Phase 1

### ✅ **Manuelle Geräteerfassung** 
- Webformular mit dynamischer Auswahl aus GLPI
- Automatische MAC-Adressen-Normalisierung (AA:BB:CC:DD:EE:FF)
- IP-Adressen-Validierung
- Direkte Anlage in GLPI über API

### ✅ **OCR-Formularverarbeitung**
- Automatische Überwachung von Samba-Freigaben
- OCR mit Tesseract/PaddleOCR
- Erweiterbare Formular-Vorlagen
- Prüfansicht mit manueller Korrektur

### ✅ **GLPI-Integration**
- Dynamisches Laden von Kunden, Standorten, Benutzern
- Automatische Anlage in korrektem Tenant
- Synchronisation über GLPI-API

## 🚀 Schnellstart

### 1. Installation
```bash
# Python-Abhängigkeiten installieren
pip install -r requirements.txt

# Datenbank initialisieren
python -c "from device_management.models import Base; from device_management.config import settings; from sqlalchemy import create_engine; engine = create_engine(settings.database_url); Base.metadata.create_all(bind=engine)"
```

### 2. Konfiguration
```bash
# GLPI-Zugangsdaten setzen
export GLPI_BASE_URL="http://deine-glpi-instanz"
export GLPI_APP_TOKEN="dein-app-token"
export GLPI_USER_TOKEN="dein-user-token"
```

### 3. System starten
```bash
# Backend-API starten (Port 8000)
python -m device_management.api.main

# Frontend starten (Port 3000)
python -m http.server 3000 --directory frontend/
```

## 🌐 Zugriff

- **Frontend**: http://localhost:3000
- **API-Dokumentation**: http://localhost:8000/docs
- **OpenAPI-Schema**: http://localhost:8000/openapi.json

## 📊 Architektur

```
device_management/
├── api/              # FastAPI REST-API
├── modules/          # Modulare Komponenten
│   ├── glpi_connector/     # GLPI-Modul
│   ├── ocr_processor/      # OCR-Verarbeitung
│   └── samba_monitor/      # Samba-Überwachung
├── web/              # Frontend-UI
└── tests/            # Unit-Tests
```

## 🔧 API-Endpoints (Phase 1)

- `POST /api/v1/devices` - Gerät erstellen
- `GET /api/v1/customers` - Kunden aus GLPI laden
- `POST /api/v1/ocr/upload` - OCR-Datei hochladen
- `POST /api/v1/ocr/process-samba-files` - Samba-Dateien verarbeiten
- `GET /api/v1/glpi/entities` - GLPI-Entities abrufen

## 🔒 Sicherheitsfeatures

- JWT-Authentifizierung
- SSL/TLS-Unterstützung
- Rollenbasierte Berechtigungen
- Audit-Logging aller Änderungen

## 📈 Phase 2-Vorbereitung

Die Phase 1 ist bereits vollständig mit den Phase-2-Modulen integriert:
- **DNS Resolver** für Domänen-Erkennung
- **MAC Vendor Lookup** für Hersteller-Identifikation  
- **Network Scanner** für automatische Geräteerkennung
- **GLPI Sync** für Batch-Synchronisation

## 🐛 Fehlerbehebung

**API nicht erreichbar?**
- Prüfe ob Python-Prozess läuft (Port 8000)
- Prüfe GLPI-Zugangsdaten in Konfiguration

**OCR funktioniert nicht?**
- Tesseract muss installiert sein: `apt-get install tesseract-ocr tesseract-ocr-deu`
- Samba-Freigaben müssen konfiguriert sein

**GLPI-Integration fehlgeschlagen?**
- API-Tokens müssen korrekt konfiguriert sein
- GLPI 11 muss installiert und erreichbar sein

## 📄 Lizenz

Proprietär - Für den internen Gebrauch entwickelt.


## 🌐 GLPI-Konfiguration über die GUI

Der Installer fragt die GLPI-Zugangsdaten nicht mehr in der Console ab. Nach der Installation:

1. Die IP-Adresse des Servers im Browser öffnen.
2. **Ersteinrichtung** unter `http://SERVER-IP/setup` öffnen.
3. GLPI-Adresse, Application Token und User Token eingeben.
4. **Verbindung testen** auswählen.
5. Die Konfiguration speichern.

Die GLPI-Zugangsdaten werden in der lokalen `.env`-Datei gespeichert. Der webbasierte Assistent ist nur verfügbar, solange noch keine gültige GLPI-Konfiguration hinterlegt ist.

