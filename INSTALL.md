# Installationsanleitung für Device Management System

Diese Anleitung beschreibt die Installation der modularen Geräteerfassungs-Software mit GLPI-Integration.

## 📋 Systemvoraussetzungen

### Mindestanforderungen
- **Betriebssystem**: Ubuntu 22.04 LTS oder Debian 11/12
- **CPU**: 2+
- **RAM**: 4 GB
- **Festplatte**: 10 GB freier Speicher
- **Python**: 3.9 oder höher

### Empfohlene Umgebung
- Ubuntu Server 22.04 LTS
- 8 GB RAM für OCR-Verarbeitung
- PostgreSQL statt SQLite für Produktion
- Separate OCR-Worker-Maschine bei hoher Last

## 🔧 Schritt-für-Schritt Installation

### 1. Systempakete installieren

```bash
# Systemaktualisierung
sudo apt update && sudo apt upgrade -y

# Grundlegende Abhängigkeiten
sudo apt install -y python3-pip python3-venv python3-dev

# OCR-Abhängigkeiten
sudo apt install -y tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
sudo apt install -y poppler-utils libmagic1 libsmbclient

# Für PaddleOCR (optional)
sudo apt install -y libgl1-mesa-glx libglib2.0-0

# Netzwerk-Scanning (Phase 2)
sudo apt install -y nmap python3-nmap
```

### 2. Projekt herunterladen

```bash
# Repository klonen (angenommen du hast Zugriff)
git clone https://github.com/dein-repository/device-management.git
cd device-management

# Alternativ: Manuelle Dateistruktur erstellen
mkdir -p /opt/device-management
cp -r /pfad/zum/projekt/* /opt/device-management/
cd /opt/device-management
```

### 3. Python-Umgebung einrichten

```bash
# Virtuelle Umgebung erstellen
python3 -m venv venv

# Aktivieren
source venv/bin/activate  # Linux/macOS
# oder auf Windows: venv\Scripts\activate

# Abhängigkeiten installieren
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Konfiguration

```bash
# Konfigurationsdatei kopieren
cp .env.example .env

# .env Datei bearbeiten mit deinen Daten
nano .env
```

**Beispiel .env:**

```ini
# GLPI Konfiguration
GLPI_BASE_URL=http://192.168.1.100/glpi
GLPI_APP_TOKEN=dein_glpi_app_token
GLPI_USER_TOKEN=dein_glpi_user_token

# Datenbank (SQLite für Test, PostgreSQL für Produktion)
DATABASE_URL=sqlite:///./device_management.db
# DATABASE_URL=postgresql://user:password@localhost/device_management

# Samba Pfade
OCR_INPUT_WATCH_PATH=/mnt/samba/glpi-formulare/eingang
OCR_PROCESSING_PATH=/mnt/samba/glpi-formulare/in-bearbeitung
OCR_DONE_PATH=/mnt/samba/glpi-formulare/erledigt
OCR_ERROR_PATH=/mnt/samba/glpi-formulare/fehler
OCRRCHIVE_PATH=/mnt/samba/glpi-formulare/archiv

# Sicherheit
SECRET_KEY=dein_sicheres_geheimnis_hier
DEBUG=False
```

### 5. Samba-Freigaben einrichten

```bash
# Verzeichnisstruktur erstellen
sudo mkdir -p /mnt/samba/glpi-formulare/{eingang,in-bearbeitung,erledigt,fehler,archiv}

# Berechtigungen setzen
sudo chown -R www-data:www-data /mnt/samba/glpi-formulare/
sudo chmod -R 775 /mnt/samba/glpi-formulare/

# Samba-Konfiguration (falls lokal)
# /etc/samba/smb.conf hinzufügen:
[glpi-formulare]
    path = /mnt/samba/glpi-formulare
    valid users = @smbusers
    read only = no
    create mask = 0775
    directory mask = 0775
```

### 6. Datenbank initialisieren

```bash
# Datenbanktabellen erstellen
python -c "
from device_management.models import Base
from device_management.config import settings
from sqlalchemy import create_engine

engine = create_engine(settings.database_url)
Base.metadata.create_all(bind=engine)
print('Datenbank erfolgreich initialisiert')
"

# Optional: Demodaten laden
python scripts/seed_database.py
```

### 7. System starten

#### Option A: Entwicklungsmodus (manuell)

```bash
# Backend-API starten
python -m device_management.api.main

# Frontend-Server starten (in neuem Terminal)
python -m http.server 3000 --directory frontend/
```

#### Option B: Systemd Service (Produktion)

**Backend-Service:**
```bash
sudo cat > /etc/systemd/system/device-management-api.service << EOF
[Unit]
Description=Device Management System API
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/device-management
Environment="PATH=/opt/device-management/venv/bin"
ExecStart=/opt/device-management/venv/bin/python -m device_management.api.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**Frontend-Service (nginx empfohlen):**
```bash
# Nginx installieren
sudo apt install -y nginx

# Nginx-Konfiguration
sudo cat > /etc/nginx/sites-available/device-management << EOF
server {
    listen 80;
    server_name geräteverwaltung.local;

    # Backend-API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # Frontend
    location / {
        root /opt/device-management/frontend;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # Static files
    location /static {
        root /opt/device-management/frontend;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/device-management /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

### 8. OCR-Worker starten (optional)

```bash
# Celery Worker für Hintergrund-OCR
venv/bin/celery -A device_management.modules.ocr_worker worker --loglevel=info
```

## 🔍 Installation verifizieren

```bash
# API testen
curl http://localhost:8000/health

# Frontend testen  
curl http://localhost:3000/

# Datenbank prüfen
sqlite3 device_management.db "SELECT COUNT(*) FROM devices;"
```

## 🐛 Fehlerbehebung

### "GLPI Connection Failed"
- GLPI-URL korrekt?
- API-Tokens in GLPI erstellt?
- GLPI 11 installiert?

### "OCR nicht verfügbar"
- Tesseract installiert? `tesseract --version`
- Samba-Pfade existieren?
- Berechtigungen korrekt?

### "Port bereits belegt"
```bash
sudo netstat -tulpn | grep :8000
sudo kill -9 <PID>
```

### Python-Paketfehler
```bash
# Virtuelle Umgebung neu erstellen
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 📊 Monitoring

### Logs überwachen
```bash
# API-Logs
tail -f /opt/device-management/logs/api.log

# OCR-Verarbeitung
tail -f /opt/device-management/logs/ocr.log

# Systemd Logs
sudo journalctl -u device-management-api -f
```

### Gesundheitstests
```bash
# API Endpoints prüfen
curl http://localhost:8000/api/v1/health

# GLPI-Verbindung testen
curl http://localhost:8000/api/v1/glpi/test-connection

# OCR-Status
curl http://localhost:8000/api/v1/ocr/status
```

## 🔄 Updates

```bash
# Projekt aktualisieren
cd /opt/device-management
git pull origin main

# Abhängigkeiten aktualisieren
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Datenbank-Migration
alembic upgrade head

# Services neu starten
sudo systemctl restart device-management-api
```

## 🔒 Sicherheitshinweise

1. **Nie** SECRET_KEY im Code belassen
2. GLPI-Tokens regelmäßig rotieren
3. Samba-Freigaben mit Passwortschutz
4. HTTPS/SSL für Produktion
5. Regelmäßige Backups der Datenbank
6. Access-Logging aktivieren

## 📞 Support

Bei Problemen:
1. Logs prüfen: `cat logs/*.log`
2. Issue im Repository öffnen
3. GLPI-Log prüfen
4. Konfiguration verifizieren

**Installation abgeschlossen!** Das System ist jetzt unter `http://dein-server` verfügbar.