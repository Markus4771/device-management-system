#!/bin/bash
# Device Management System Installation Script für Debian/Ubuntu
# Version: 1.0

set -e  # Exit on error

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funktionen
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Das Script sollte nicht als root ausgeführt werden"
        read -p "Trotzdem fortfahren? (j/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Jj]$ ]]; then
            exit 1
        fi
    fi
}

check_system() {
    log_info "Prüfe Systemvoraussetzungen..."
    
    # Check OS
    if [[ -f /etc/debian_version ]]; then
        OS="debian"
        OS_VERSION=$(cat /etc/debian_version)
        log_info "Debian $OS_VERSION erkannt"
    elif [[ -f /etc/lsb-release ]]; then
        . /etc/lsb-release
        OS="ubuntu"
        OS_VERSION=$DISTRIB_RELEASE
        log_info "Ubuntu $OS_VERSION erkannt"
    else
        log_error "Nur Debian/Ubuntu werden unterstützt"
        exit 1
    fi
    
    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        log_info "Python $PYTHON_VERSION gefunden"
    else
        log_error "Python3 nicht installiert"
        exit 1
    fi
}

install_system_packages() {
    log_info "Installiere Systempakete..."
    
    sudo apt-get update
    
    # Grundlegende Pakete
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        curl \
        wget
    
    # OCR-Abhängigkeiten
    sudo apt-get install -y \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        poppler-utils \
        libmagic1 \
        libsmbclient \
        libgl1 \
        libglib2.0-0
    
    # Netzwerk-Scanning
    sudo apt-get install -y \
        nmap \
        python3-nmap
    
    # Optional: Für PostgreSQL
    if [[ "$INSTALL_POSTGRESQL" == "true" ]]; then
        log_info "Installiere PostgreSQL..."
        sudo apt-get install -y \
            postgresql \
            postgresql-contrib \
            libpq-dev
    fi
    
    log_success "Systempakete installiert"
}

setup_project() {
    log_info "Richte Projekt ein..."
    
    # Projektverzeichnis
    PROJECT_DIR="/opt/device-management"
    
    if [[ -d "$PROJECT_DIR" ]]; then
        log_warning "Projektverzeichnis existiert bereits: $PROJECT_DIR"
        read -p "Überschreiben? (j/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Jj]$ ]]; then
            log_info "Beende Installation"
            exit 0
        fi
        # Das Projektverzeichnis darf nicht das aktuelle Arbeitsverzeichnis sein,
        # da Git sonst nach dem Löschen keinen gültigen Arbeitsort mehr hat.
        cd /
        sudo rm -rf "$PROJECT_DIR"
    fi
    
    # Verzeichnis erstellen
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown -R $(whoami):$(whoami) "$PROJECT_DIR"
    
    # Repository klonen
    if [[ "$CLONE_FROM_GITHUB" == "true" ]]; then
        log_info "Klonen von GitHub Repository..."
        git clone https://github.com/Markus4771/device-management-system.git "$PROJECT_DIR"
    else
        log_info "Kopiere lokale Projektdateien..."
        cp -r /workspace/project/* "$PROJECT_DIR"/
        cp -r /workspace/project/.env.example "$PROJECT_DIR"/ 2>/dev/null || true
    fi
    
    cd "$PROJECT_DIR"
    
    # Virtuelle Umgebung
    log_info "Erstelle virtuelle Python-Umgebung..."
    python3 -m venv venv
    
    # Abhängigkeiten installieren
    log_info "Installiere Python-Abhängigkeiten..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    log_success "Projekt eingerichtet in $PROJECT_DIR"
}

setup_database() {
    log_info "Richte Datenbank ein..."
    
    cd "$PROJECT_DIR"
    source venv/bin/activate
    
    if [[ "$INSTALL_POSTGRESQL" == "true" ]]; then
        # PostgreSQL Setup
        log_info "Konfiguriere PostgreSQL..."
        
        # PostgreSQL Benutzer und Datenbank erstellen
        sudo -u postgres psql -c "CREATE USER device_management WITH PASSWORD '$DB_PASSWORD';" || true
        sudo -u postgres psql -c "CREATE DATABASE device_management OWNER device_management;" || true
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE device_management TO device_management;" || true
        
        # .env Datei aktualisieren
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://device_management:$DB_PASSWORD@localhost/device_management|" .env
    else
        # SQLite Setup
        log_info "Verwende SQLite Datenbank..."
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=sqlite:///./device_management.db|" .env
    fi
    
    # Datenbank initialisieren
    log_info "Initialisiere Datenbank..."
    python -c "
from device_management.models import Base
from device_management.config import settings
from sqlalchemy import create_engine
engine = create_engine(settings.database_url)
Base.metadata.create_all(bind=engine)
print('Datenbank initialisiert')
"
    
    log_success "Datenbank eingerichtet"
}

setup_ocr_directories() {
    log_info "Richte OCR-Verzeichnisse ein..."
    
    OCR_BASE="/mnt/samba/glpi-formulare"
    
    # Verzeichnisse erstellen
    sudo mkdir -p "$OCR_BASE"/{eingang,in-bearbeitung,erledigt,fehler,archiv}
    
    # Berechtigungen setzen
    sudo chown -R $(whoami):$(whoami) "$OCR_BASE"
    sudo chmod -R 775 "$OCR_BASE"
    
    # .env Datei aktualisieren
    sed -i "s|^OCR_INPUT_WATCH_PATH=.*|OCR_INPUT_WATCH_PATH=$OCR_BASE/eingang|" .env
    sed -i "s|^OCR_PROCESSING_PATH=.*|OCR_PROCESSING_PATH=$OCR_BASE/in-bearbeitung|" .env
    sed -i "s|^OCR_DONE_PATH=.*|OCR_DONE_PATH=$OCR_BASE/erledigt|" .env
    sed -i "s|^OCR_ERROR_PATH=.*|OCR_ERROR_PATH=$OCR_BASE/fehler|" .env
    sed -i "s|^OCRRCHIVE_PATH=.*|OCRRCHIVE_PATH=$OCR_BASE/archiv|" .env
    
    log_success "OCR-Verzeichnisse eingerichtet in $OCR_BASE"
}

setup_systemd_services() {
    log_info "Richte Systemd Services ein..."
    
    # Backend API Service
    sudo tee /etc/systemd/system/device-management-api.service > /dev/null << EOF
[Unit]
Description=Device Management System API
After=network.target
Wants=network.target

[Service]
Type=simple
User=$(whoami)
Group=$(whoami)
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python -m device_management.api.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=device-management-api

[Install]
WantedBy=multi-user.target
EOF
    
    # OCR Worker Service (optional)
    sudo tee /etc/systemd/system/device-management-ocr.service > /dev/null << EOF
[Unit]
Description=Device Management OCR Worker
After=device-management-api.service
Requires=device-management-api.service

[Service]
Type=simple
User=$(whoami)
Group=$(whoami)
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/celery -A device_management.modules.ocr_worker worker --loglevel=info
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=device-management-ocr

[Install]
WantedBy=multi-user.target
EOF
    
    # Services aktivieren
    sudo systemctl daemon-reload
    sudo systemctl enable device-management-api.service
    
    if [[ "$ENABLE_OCR_WORKER" == "true" ]]; then
        sudo systemctl enable device-management-ocr.service
    fi
    
    log_success "Systemd Services eingerichtet"
}

setup_nginx() {
    log_info "Richte Nginx ein..."
    
    # Nginx installieren
    sudo apt-get install -y nginx
    
    # Nginx Konfiguration
    sudo tee /etc/nginx/sites-available/device-management > /dev/null << EOF
server {
    listen 80;
    server_name _;
    
    # API Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Frontend
    location / {
        root $PROJECT_DIR/frontend;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }
    
    # Static files
    location /static {
        root $PROJECT_DIR/frontend;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
EOF
    
    # Konfiguration aktivieren
    sudo ln -sf /etc/nginx/sites-available/device-management /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Nginx testen und starten
    sudo nginx -t
    sudo systemctl restart nginx
    
    log_success "Nginx eingerichtet"
}

configure_environment() {
    log_info "Konfiguriere Umgebungsvariablen..."
    
    cd "$PROJECT_DIR"
    
    # .env Datei erstellen falls nicht vorhanden
    if [[ ! -f .env ]]; then
        cp .env.example .env
    fi
    
    # GLPI Konfiguration abfragen
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo
        echo "=== GLPI Konfiguration ==="
        echo "Bitte GLPI Zugangsdaten eingeben:"
        
        read -p "GLPI Base URL (z.B. http://192.168.0.23/glpi): " GLPI_BASE_URL
        read -p "GLPI App Token: " GLPI_APP_TOKEN
        read -p "GLPI User Token: " GLPI_USER_TOKEN
        
        sed -i "s|^GLPI_BASE_URL=.*|GLPI_BASE_URL=$GLPI_BASE_URL|" .env
        sed -i "s|^GLPI_APP_TOKEN=.*|GLPI_APP_TOKEN=$GLPI_APP_TOKEN|" .env
        sed -i "s|^GLPI_USER_TOKEN=.*|GLPI_USER_TOKEN=$GLPI_USER_TOKEN|" .env
    fi
    
    # Secret Key generieren
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
    
    # Debug Modus
    sed -i "s|^DEBUG=.*|DEBUG=false|" .env
    
    log_success "Umgebungsvariablen konfiguriert"
}

start_services() {
    log_info "Starte Services..."
    
    sudo systemctl start device-management-api.service
    
    if [[ "$ENABLE_OCR_WORKER" == "true" ]]; then
        sudo systemctl start device-management-ocr.service
    fi
    
    sudo systemctl restart nginx
    
    log_success "Services gestartet"
}

show_summary() {
    log_success "=== Installation abgeschlossen ==="
    echo
    echo "Projektverzeichnis: $PROJECT_DIR"
    echo "API Service:        http://localhost:8000"
    echo "Frontend:           http://localhost"
    echo "API Dokumentation:  http://localhost/api/docs"
    echo
    echo "=== Wichtige Befehle ==="
    echo "API Logs anzeigen:    sudo journalctl -u device-management-api -f"
    echo "API Status prüfen:    sudo systemctl status device-management-api"
    echo "Nginx Logs:           sudo tail -f /var/log/nginx/access.log"
    echo "Datenbank Backup:     $PROJECT_DIR/scripts/backup_database.sh"
    echo
    echo "=== Nächste Schritte ==="
    echo "1. GLPI API Tokens in GLPI erstellen"
    echo "2. .env Datei in $PROJECT_DIR/.env überprüfen"
    echo "3. Frontend unter http://localhost testen"
    echo "4. API unter http://localhost/api/docs testen"
    echo
    echo "Bei Problemen Logs prüfen:"
    echo "sudo journalctl -u device-management-api"
    echo "sudo tail -f /var/log/nginx/error.log"
}

# Hauptprogramm
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE} Device Management System Installer${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    # Variablen
    PROJECT_DIR="/opt/device-management"
    INTERACTIVE="true"
    CLONE_FROM_GITHUB="true"   # Installation aus dem GitHub-Repository
    INSTALL_POSTGRESQL="false" # SQLite für einfache Installation
    ENABLE_OCR_WORKER="false"  # OCR Worker optional
    DB_PASSWORD="$(openssl rand -hex 16)"
    
    # Optionen parsen
    while [[ $# -gt 0 ]]; do
        case $1 in
            --non-interactive)
                INTERACTIVE="false"
                shift
                ;;
            --postgresql)
                INSTALL_POSTGRESQL="true"
                shift
                ;;
            --ocr-worker)
                ENABLE_OCR_WORKER="true"
                shift
                ;;
            --clone)
                CLONE_FROM_GITHUB="true"
                shift
                ;;
            --directory=*)
                PROJECT_DIR="${1#*=}"
                shift
                ;;
            --help)
                echo "Verwendung: $0 [OPTIONEN]"
                echo
                echo "Optionen:"
                echo "  --non-interactive    Nicht-interaktive Installation"
                echo "  --postgresql         PostgreSQL statt SQLite verwenden"
                echo "  --ocr-worker         OCR Worker Service aktivieren"
                echo "  --clone              Von GitHub klonen statt lokale Dateien"
                echo "  --directory=PATH     Installationsverzeichnis (Standard: /opt/device-management)"
                echo "  --help               Diese Hilfe anzeigen"
                exit 0
                ;;
            *)
                log_error "Unbekannte Option: $1"
                exit 1
                ;;
        esac
    done
    
    # Prüfungen
    check_root
    check_system
    
    # Installation
    install_system_packages
    setup_project
    configure_environment
    setup_database
    setup_ocr_directories
    setup_systemd_services
    setup_nginx
    start_services
    show_summary
}

# Skript ausführen
main "$@"