# Device Management System (Geräteerfassung und -verwaltung)

Modulare Software zur Erfassung und Verwaltung von Kundengeräten mit GLPI-Integration.

## Übersicht

Diese Software ermöglicht:
- Manuelle Geräteerfassung über Webformular
- Automatische Erfassung via OCR aus gescannten Formularen
- Integration mit GLPI 11 API
- Netzwerk- und Domänenerkennung (Phase 2)
- Integration in bestehende Supportsoftware (Phase 3)

## Phasenplan

### Phase 1: Manuelle Geräteerfassung
- Webformular zur manuellen Geräteerfassung
- Dynamische Daten aus GLPI (Kunden, Standorte, Benutzer, Techniker)
- GLPI-API Integration zur automatischen Erstellung von Computer-Einträgen

### Phase 1b: OCR-Erfassung von eingescannten Formularen
- Automatische Überwachung von Samba-Freigaben
- OCR-Verarbeitung (Tesseract/OCRmyPDF/PaddleOCR)
- Formularvorlagensystem für verschiedene Kundenformulare
- Prüfansicht mit Korrekturmöglichkeit

### Phase 2: Automatische Netzwerk- und Domänenerkennung
- Netzwerkscans für IP-Bereiche
- Automatische Geräteerkennung und -erfassung
- Active Directory/LDAP Integration
- Sicherheitsprotokollierung

### Phase 3: Integration in Supportsoftware
- Nahtlose Integration in bestehende Supportsoftware
- Ticketverknüpfung mit Geräten
- Kundenbereich mit Geräteinformationen

## Technischer Stack

### Backend
- **Framework**: FastAPI (Python)
- **Datenbank**: PostgreSQL (Produktion) / SQLite (Entwicklung)
- **ORM**: SQLAlchemy
- **Authentifizierung**: JWT / OAuth2
- **Task Queue**: Celery (für Hintergrundaufgaben)

### Frontend
- **Framework**: React mit TypeScript oder Vue.js
- **UI-Komponenten**: Material-UI oder Ant Design
- **Formularverarbeitung**: Formik oder React Hook Form

### OCR & Dateiverarbeitung
- **OCR Engine**: Tesseract 5 + OCRmyPDF
- **Dateiüberwachung**: Watchdog (Python)
- **PDF-Verarbeitung**: PyPDF2 / pdf2image

### Netzwerk-Scanning
- **Netzwerkscan**: Nmap (Python nmap wrapper)
- **LDAP/AD**: python-ldap / ldap3
- **MAC-Vendor-DB**: manuf Bibliothek

## Projektstruktur

```
device_management/
├── modules/                    # Unabhängige Module
│   ├── user_management/        # Benutzerverwaltung
│   ├── customer_management/    # Kunden- und Einheitenverwaltung
│   ├── device_registration/    # Geräteerfassung
│   ├── glpi_connector/         # GLPI-API Integration
│   ├── form_processing/        # Formularverarbeitung
│   ├── ocr_module/            # OCR-Verarbeitung
│   ├── network_scanner/       # Netzwerk-Scanner
│   ├── ad_connector/          # Active Directory/LDAP
│   └── audit_module/          # Protokollierung
├── api/                       # REST API (FastAPI)
├── models/                    # Datenmodelle
├── web/                       # Frontend (React/Vue)
├── config/                    # Konfiguration
├── tests/                     # Tests
└── scripts/                   # Hilfsskripte
```

## Installation

Siehe [INSTALLATION.md](INSTALLATION.md) für detaillierte Installationsanleitung.

## Konfiguration

1. GLPI-Zugangsdaten in `config/glpi_config.yaml` eintragen
2. Datenbankverbindung konfigurieren
3. Samba-Freigabepfade für OCR-Modul einstellen

## Entwicklung

```bash
# Virtuelle Umgebung erstellen
python -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Entwicklungsserver starten
python -m api.main
```

## GLPI Integration

Die Software verwendet die GLPI REST API für:
- Abruf von Kunden/Entities
- Abruf von Standorten (Locations)
- Abruf von Benutzern (Users)
- Abruf von Technikern (Technicians)
- Erstellung von Computer-Einträgen
- Aktualisierung von Geräteinformationen

## API Dokumentation

Nach Start des Servers: http://localhost:8000/docs

## Lizenz

Proprietär