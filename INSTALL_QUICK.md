# Schnellinstallation - Device Management System

## ⚡ Express-Installation (5 Minuten)

```bash
# 1. Grundlegende Abhängigkeiten
sudo apt update
sudo apt install -y python3-pip python3-venv tesseract-ocr tesseract-ocr-deu nmap

# 2. Projektordner erstellen
mkdir -p ~/device-management
cd ~/device-management

# 3. Projektdateien kopieren (von diesem Verzeichnis)
# Alle Dateien aus /workspace/project hierher kopieren

# 4. Virtuelle Umgebung und Abhängigkeiten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Konfiguration
cp .env.example .env
# .env Datei bearbeiten mit GLPI-Zugangsdaten

# 6. Datenbank initialisieren
python -c "
from device_management.models import Base
from device_management.config import settings
from sqlalchemy import create_engine
engine = create_engine(settings.database_url)
Base.metadata.create_all(bind=engine)
print('✅ Datenbank bereit')
"

# 7. OCR-Verzeichnisse erstellen
mkdir -p /tmp/glpi-formulare/{eingang,in-bearbeitung,erledigt,fehler,archiv}

# 8. System starten
# Terminal 1 - Backend
python -m device_management.api.main

# Terminal 2 - Frontend  
python -m http.server 3000 --directory frontend/
```

## 🔗 Zugriff

- **Frontend:** http://localhost:3000
- **API-Doku:** http://localhost:8000/docs
- **API-Health:** http://localhost:8000/health

## 🛠️ Minimal-Konfiguration (.env)

```ini
# GLPI - ESSENTIELL für Produktion
GLPI_BASE_URL=http://deine-glpi-instanz
GLPI_APP_TOKEN=dein_app_token_aus_glpi
GLPI_USER_TOKEN=dein_user_token_aus_glpi

# Datenbank (SQLite für Test)
DATABASE_URL=sqlite:///./device_management.db

# OCR-Pfade (lokal für Test)
OCR_INPUT_WATCH_PATH=/tmp/glpi-formulare/eingang
OCR_PROCESSING_PATH=/tmp/glpi-formulare/in-bearbeitung

# Sicherheit
SECRET_KEY=<generiere_ein_sicheres_passwort>
DEBUG=True  # Für Test, auf False für Produktion
```

## 📋 GLPI-Vorbereitung (wichtig!)

Vor der Installation in GLPI 11:
1. **Application Token erstellen**: `Einstellungen → Allgemein → API → Application Token`
2. **User Token erstellen**: `Einstellungen → Mein Profil → API → Token`
3. **API aktivieren**: `Einstellungen → Allgemein → API → API aktivieren`

## ✅ Verifizierung

```bash
# API läuft?
curl http://localhost:8000/health
# Sollte: {"status":"healthy","service":"device-management-api"}

# Datenbank-Tabellen?
sqlite3 device_management.db ".tables"

# OCR funktioniert?
tesseract --version
# Sollte: tesseract 5.3.0
```

## 🆘 Bei Problemen

**Fehler: "ModuleNotFoundError"**
```bash
# Virtuelle Umgebung aktivieren
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

**Fehler: "Port belegt"**
```bash
# Port 8000 oder 3000 freigeben
sudo lsof -i :8000
sudo kill -9 <PID>
```

**Fehler: "GLPI connection failed"**
- GLPI-URL prüfen
- API-Tokens überprüfen
- GLPI 11 muss installiert sein

**Fehler: "OCR nicht verfügbar"**
```bash
sudo apt install tesseract-ocr tesseract-ocr-deu
```

## 🚀 Produktion (erweiterte Schritte)

Für Produktionsumgebung zusätzlich:
1. Nginx statt Python HTTP Server
2. PostgreSQL statt SQLite
3. Systemd Services
4. SSL/HTTPS
5. Regelmäßige Backups

Siehe vollständige Installationsanleitung in `INSTALL.md`.