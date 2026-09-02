#!/bin/bash
# Minimal Installation für Debian Server
# Einfacher, spezifisch für Debian optimiert

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE} Device Management - Debian Installer${NC}"
echo -e "${BLUE}========================================${NC}"

# Prüfe ob root
if [[ $EUID -eq 0 ]]; then
    echo -e "${YELLOW}Warnung: Nicht als root ausführen${NC}"
    echo "Erstelle stattdessen einen normalen Benutzer:"
    echo "  adduser deviceadmin"
    echo "  usermod -aG sudo deviceadmin"
    echo "  su - deviceadmin"
    exit 1
fi

# System aktualisieren
echo -e "${BLUE}[1/8] System aktualisieren...${NC}"
sudo apt update && sudo apt upgrade -y

# Grundlegende Pakete
echo -e "${BLUE}[2/8] Installiere Grundpakete...${NC}"
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    nginx \
    tesseract-ocr \
    tesseract-ocr-deu \
    nmap \
    poppler-utils \
    libmagic1

# Projektverzeichnis
PROJECT_DIR="/opt/device-management"
echo -e "${BLUE}[3/8] Richte Projektverzeichnis ein...${NC}"

if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Verzeichnis existiert bereits. Überschreiben? (j/N)${NC}"
    read -n 1 -r
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        sudo rm -rf "$PROJECT_DIR"
    else
        exit 1
    fi
fi

sudo mkdir -p "$PROJECT_DIR"
sudo chown -R $USER:$USER "$PROJECT_DIR"

# Repository klonen
echo -e "${BLUE}[4/8] Klone Repository...${NC}"
git clone https://github.com/Markus4771/device-management-system.git "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Python Umgebung
echo -e "${BLUE}[5/8] Python Umgebung einrichten...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Konfiguration
echo -e "${BLUE}[6/8] Konfiguration...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    
    echo
    echo -e "${YELLOW}=== GLPI Konfiguration ===${NC}"
    echo "Bitte GLPI Zugangsdaten eingeben:"
    echo
    read -p "GLPI Base URL (z.B. http://192.168.0.23/glpi): " GLPI_URL
    read -p "GLPI App Token: " GLPI_APP
    read -p "GLPI User Token: " GLPI_USER
    
    # .env aktualisieren
    sed -i "s|^GLPI_BASE_URL=.*|GLPI_BASE_URL=$GLPI_URL|" .env
    sed -i "s|^GLPI_APP_TOKEN=.*|GLPI_APP_TOKEN=$GLPI_APP|" .env
    sed -i "s|^GLPI_USER_TOKEN=.*|GLPI_USER_TOKEN=$GLPI_USER|" .env
    
    # Secret Key generieren
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
    
    # Debug ausschalten
    sed -i "s|^DEBUG=.*|DEBUG=false|" .env
fi

# OCR Verzeichnisse
echo -e "${BLUE}[7/8] OCR Verzeichnisse erstellen...${NC}"
sudo mkdir -p /mnt/samba/glpi-formulare/{eingang,in-bearbeitung,erledigt,fehler,archiv}
sudo chown -R $USER:$USER /mnt/samba/glpi-formulare
sudo chmod -R 775 /mnt/samba/glpi-formulare

# Datenbank initialisieren
echo -e "${BLUE}[8/8] Datenbank initialisieren...${NC}"
python -c "
from device_management.models import Base
from device_management.config import settings
from sqlalchemy import create_engine
engine = create_engine(settings.database_url)
Base.metadata.create_all(bind=engine)
print('Datenbank initialisiert')
"

# Systemd Service
echo -e "${BLUE}Systemd Service einrichten...${NC}"
sudo tee /etc/systemd/system/device-management.service > /dev/null << EOF
[Unit]
Description=Device Management System
After=network.target nginx.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python -m device_management.api.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable device-management.service
sudo systemctl start device-management.service

# Nginx Konfiguration
echo -e "${BLUE}Nginx konfigurieren...${NC}"
sudo tee /etc/nginx/sites-available/device-management > /dev/null << EOF
server {
    listen 80;
    server_name _;
    
    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    
    # Frontend
    location / {
        root $PROJECT_DIR/frontend;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/device-management /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# Abschluss
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Installation abgeschlossen!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Zugriff:"
echo "  Frontend:      http://$(hostname -I | awk '{print $1}')"
echo "  API Docs:      http://$(hostname -I | awk '{print $1}')/api/docs"
echo "  API Health:    http://$(hostname -I | awk '{print $1}')/api/health"
echo
echo "Verzeichnis:     $PROJECT_DIR"
echo "Service Status:  sudo systemctl status device-management"
echo "Logs anzeigen:   sudo journalctl -u device-management -f"
echo
echo "Nächste Schritte:"
echo "1. GLPI API Tokens überprüfen"
echo "2. Frontend unter http://$(hostname -I | awk '{print $1}') testen"
echo "3. OCR testen mit gescannten Formularen in /mnt/samba/glpi-formulare/eingang"
echo
echo "Bei Problemen:"
echo "- Logs: sudo journalctl -u device-management"
echo "- Nginx: sudo tail -f /var/log/nginx/error.log"
echo "- Konfiguration: $PROJECT_DIR/.env"