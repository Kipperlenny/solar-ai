#!/bin/bash
# Solar Mining System - Systemd Service Installation
# Richtet automatischen Start beim Boot ein

set -e

PROJECT_DIR="$HOME/solar-mining"
SERVICE_NAME="solar-mining"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "================================================"
echo "  Solar Mining - Autostart Installation"
echo "================================================"
echo ""

# Prüfe ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    echo "Bitte mit sudo ausführen:"
    echo "sudo $0"
    exit 1
fi

# Hole den echten User (nicht root)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo ~$REAL_USER)
PROJECT_DIR="$REAL_HOME/solar-mining"

echo "User: $REAL_USER"
echo "Projekt: $PROJECT_DIR"
echo ""

# Erstelle Systemd Service
echo "Erstelle systemd Service..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Solar Mining System
After=network.target

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/start_solar_mining_pi.sh
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/system.log
StandardError=append:$PROJECT_DIR/logs/system.log

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Service-Datei erstellt: $SERVICE_FILE"

# Setze Ausführungsrechte
chmod +x "$PROJECT_DIR/start_solar_mining_pi.sh"
chmod +x "$PROJECT_DIR/setup_raspberry.sh"

# Reload systemd
echo ""
echo "Lade systemd neu..."
systemctl daemon-reload

# Enable Service
echo "Aktiviere Autostart..."
systemctl enable "$SERVICE_NAME"

echo ""
echo "================================================"
echo "  Installation abgeschlossen!"
echo "================================================"
echo ""
echo "Verfügbare Befehle:"
echo ""
echo "  sudo systemctl start $SERVICE_NAME    - Service starten"
echo "  sudo systemctl stop $SERVICE_NAME     - Service stoppen"
echo "  sudo systemctl status $SERVICE_NAME   - Status anzeigen"
echo "  sudo systemctl restart $SERVICE_NAME  - Service neustarten"
echo ""
echo "  journalctl -u $SERVICE_NAME -f        - Live-Logs anzeigen"
echo "  tail -f $PROJECT_DIR/logs/system.log  - System-Log anzeigen"
echo ""
echo "Der Service startet jetzt automatisch beim Boot!"
echo ""
