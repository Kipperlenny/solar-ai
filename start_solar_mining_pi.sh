#!/bin/bash
# Solar Mining System - Raspberry Pi Start Script
# Startet das System mit automatischer venv-Aktivierung

PROJECT_DIR="$HOME/solar-mining"
cd "$PROJECT_DIR" || exit 1

# Aktiviere Virtual Environment
source "$PROJECT_DIR/.venv/bin/activate"

# Starte Python Script
python3 solar_mining_pi.py

# Bei Fehler, warte kurz bevor Neustart
if [ $? -ne 0 ]; then
    echo "Script beendet mit Fehler. Warte 10 Sekunden..."
    sleep 10
fi
