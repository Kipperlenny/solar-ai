"""
Solar Mining Controller with GPU Monitoring
============================================
Automatic crypto mining based on available solar energy.

Features:
- Starts/stops mining based on solar surplus
- Automatically pauses when other software needs GPU (gaming, Stable Diffusion, etc.)
- Excavator API control (fast start/stop times)
- NiceHash earnings tracking
- Auto-start of Excavator

GPU Monitoring:
- Detects when other processes use the GPU (>10% load)
- Automatically pauses mining for Rocket League, Stable Diffusion, etc.
- Resumes mining when GPU is available again
- GPU_CHECK_ENABLED = True/False to enable/disable feature
"""

import asyncio
import json
import subprocess
import os
import sys
import importlib
import requests
from huawei_solar import create_tcp_bridge
from datetime import datetime
import time
import GPUtil
import psutil
import logging
import traceback
import csv
from pathlib import Path
from dotenv import load_dotenv
import shutil
import zipfile
import tempfile
from urllib.parse import urlparse
import pkg_resources
from packaging import version

# Import shared components
from solar_core import (
    WeatherAPI,
    InverterConnection,
    AlarmParser,
    CSVLogger,
    AlarmDiagnostics,
    setup_logging as core_setup_logging,
    CSV_COLUMNS_FULL
)

# Import translation system
from translations import t

# Load .env file
load_dotenv()

# CONFIGURATION (from .env)
# QuickMiner (preferred)
QUICKMINER_PATH = os.getenv("QUICKMINER_PATH", r"H:\miner\NiceHashQuickMiner.exe")
QUICKMINER_API_HOST = os.getenv("QUICKMINER_API_HOST", "127.0.0.1")
QUICKMINER_API_PORT = int(os.getenv("QUICKMINER_API_PORT", "18000"))

# Excavator (fallback)
EXCAVATOR_PATH = os.getenv("EXCAVATOR_PATH", r"H:\miner\excavator.exe")
EXCAVATOR_API_HOST = os.getenv("EXCAVATOR_API_HOST", "127.0.0.1")
EXCAVATOR_API_PORT = int(os.getenv("EXCAVATOR_API_PORT", "3456"))

INVERTER_HOST = os.getenv("INVERTER_HOST", "192.168.18.206")
INVERTER_PORT = int(os.getenv("INVERTER_PORT", "6607"))

# GPU settings
DEVICE_ID = os.getenv("DEVICE_ID", "0")
DEVICE_IDS = [id.strip() for id in DEVICE_ID.split(",")]  # Support multiple GPUs
ALGORITHM = os.getenv("ALGORITHM", "daggerhashimoto")
STRATUM_URL = os.getenv("STRATUM_URL", "nhmp-ssl.eu.nicehash.com:443")
NICEHASH_WALLET = os.getenv("NICEHASH_WALLET", "YOUR_WALLET_ADDRESS.worker_name")

# NiceHash API (for earnings)
NICEHASH_API_URL = "https://api2.nicehash.com/main/api/v2/mining/external"

# Weather API (Open-Meteo - free, no API key needed)
WEATHER_ENABLED = os.getenv("WEATHER_ENABLED", "True").lower() == "true"
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "37.6931"))  # Los Nietos, Spain
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "-0.8481"))
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Power thresholds
MIN_POWER_TO_START = int(os.getenv("MIN_POWER_TO_START", "200"))
MIN_POWER_TO_KEEP = int(os.getenv("MIN_POWER_TO_KEEP", "150"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
ALARM_CHECK_INTERVAL = int(os.getenv("ALARM_CHECK_INTERVAL", "5"))

# Hysteresis
START_CONFIRMATIONS_NEEDED = int(os.getenv("START_CONFIRMATIONS_NEEDED", "3"))
STOP_CONFIRMATIONS_NEEDED = int(os.getenv("STOP_CONFIRMATIONS_NEEDED", "5"))

# GPU usage monitoring
GPU_USAGE_THRESHOLD = int(os.getenv("GPU_USAGE_THRESHOLD", "10"))
GPU_CHECK_ENABLED = os.getenv("GPU_CHECK_ENABLED", "True").lower() == "true"

# Modbus timeout settings (for improved reliability)
MODBUS_READ_TIMEOUT = int(os.getenv("MODBUS_READ_TIMEOUT", "10"))  # Timeout for non-critical reads
MODBUS_CRITICAL_TIMEOUT = int(os.getenv("MODBUS_CRITICAL_TIMEOUT", "15"))  # Timeout for critical reads (solar power)

# LOGGING CONFIGURATION
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG_FILE = LOG_DIR / "errors.log"
DATA_LOG_FILE = LOG_DIR / "solar_data.csv"
GPU_HEALTH_LOG = LOG_DIR / "gpu_health.csv"

# Setup Error Logger
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.DEBUG)
from logging.handlers import RotatingFileHandler

# Use rotating logs to avoid huge files
error_handler = RotatingFileHandler(ERROR_LOG_FILE, encoding='utf-8', maxBytes=5*1024*1024, backupCount=5)
error_handler.setLevel(logging.DEBUG)
error_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
error_handler.setFormatter(error_formatter)
error_logger.addHandler(error_handler)

# GPU Health Logger - tracks stuck GPU events for analysis
GPU_HEALTH_LOG_FILE = LOG_DIR / "gpu_health.csv"

def init_gpu_health_log():
    """Initialize CSV file for GPU health logging if it doesn't exist."""
    if not GPU_HEALTH_LOG_FILE.exists():
        with open(GPU_HEALTH_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp',
                'unix_timestamp',
                'event_type',  # 'stuck_detected', 'fix_attempted', 'fix_success', 'fix_failed', 'recovered'
                'gpu_id',
                'gpu_name',
                'stuck_algorithm',
                'target_algorithm',
                'stuck_duration_seconds',
                'hashrate_before',
                'hashrate_after',
                'miner_type',  # QuickMiner or Excavator
                'notes'
            ])

init_gpu_health_log()

# Prepare excavator-specific logs
EXCAVATOR_LOG_DIR = LOG_DIR / "excavator"
EXCAVATOR_LOG_DIR.mkdir(exist_ok=True)
EXCAVATOR_STDOUT = EXCAVATOR_LOG_DIR / "excavator_out.log"
EXCAVATOR_STDERR = EXCAVATOR_LOG_DIR / "excavator_err.log"

# Data Logger Setup
def init_data_log():
    """Initialize CSV file for data logging if it doesn't exist."""
    if not DATA_LOG_FILE.exists():
        with open(DATA_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                # Basis
                'timestamp',
                'unix_timestamp',
                # Solar/Grid
                'solar_production_w',
                'grid_power_w',
                'house_consumption_w',
                'grid_feed_in_w',
                'grid_import_w',
                'available_for_mining_w',
                # Mining
                'mining_active',
                'mining_paused',
                'hashrate_mhs',
                'excavator_errors',
                'start_confirmations',
                'stop_confirmations',
                # GPU
                'gpu_usage_percent',
                'gpu_temp_c',
                # String-Daten (PV)
                'pv_01_voltage_v',
                'pv_01_current_a',
                'pv_01_power_w',
                'pv_02_voltage_v',
                'pv_02_current_a',
                'pv_02_power_w',
                # Grid Details (3 Phasen)
                'grid_A_voltage_v',
                'grid_B_voltage_v',
                'grid_C_voltage_v',
                'grid_A_current_a',
                'grid_B_current_a',
                'grid_C_current_a',
                'grid_A_power_w',
                'grid_B_power_w',
                'grid_C_power_w',
                # Inverter Status
                'internal_temp_c',
                'efficiency_percent',
                'daily_yield_kwh',
                'total_yield_kwh',
                # Batterie (optional)
                'battery_power_w',
                'battery_soc_percent',
                # Wetter
                'weather_temp_c',
                'weather_cloud_cover_percent',
                'weather_wind_speed_kmh',
                'weather_precipitation_mm',
                'weather_global_radiation_wm2',
                'weather_direct_radiation_wm2',
                'weather_diffuse_radiation_wm2',
                # Inverter Alarms
                'inverter_alarm_1',
                'inverter_alarm_2',
                'inverter_alarm_3',
                'inverter_device_status'
            ])

init_data_log()

def init_gpu_health_log():
    """Initialize GPU health CSV used for offline analysis."""
    if not GPU_HEALTH_LOG.exists():
        with open(GPU_HEALTH_LOG, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp',
                'device_id',
                'device_uuid',
                'action',        # monitor_start / fix_attempt / fix_success / fix_failed / recovered
                'algorithm',
                'result',        # ok / failed / observed
                'error',
                'zero_duration_s',
                'note'
            ])

init_gpu_health_log()

def log_gpu_health_event(timestamp, device_id, device_uuid, action, algorithm, result, error, zero_duration_s, note):
    """Append a structured GPU health event to the CSV log.

    timestamp: ISO string
    device_id: string
    device_uuid: string or empty
    action: short action code
    algorithm: algorithm name
    result: ok/failed/observed
    error: error message or empty
    zero_duration_s: seconds GPU was at 0 hashrate (int)
    note: additional text
    """
    try:
        with open(GPU_HEALTH_LOG, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                device_id,
                device_uuid or "",
                action,
                algorithm or "",
                result or "",
                (error or "").replace('\n', ' '),
                int(zero_duration_s) if zero_duration_s is not None else "",
                note or ""
            ])
    except Exception as e:
        error_logger.error(f"Failed to write gpu health log: {e}")

# WeatherAPI wird jetzt aus solar_core importiert (siehe oben)

# ============================================================================
# AUTO-UPDATE FUNCTIONS
# ============================================================================

def check_and_update_excavator(excavator_path):
    """
    Check for updates to NiceHash Excavator and auto-update if available.
    
    Returns:
        bool: True if update was performed or not needed, False if error occurred
    """
    try:
        print("\n🔍 Prüfe auf Excavator-Updates...")
        error_logger.info("Checking for Excavator updates")
        
        # GitHub API für NiceHash Excavator Releases
        api_url = "https://api.github.com/repos/nicehash/excavator/releases/latest"
        
        # Get latest release info
        response = requests.get(api_url, timeout=10)
        if response.status_code != 200:
            print(f"   ⚠️  GitHub API nicht erreichbar (Status {response.status_code})")
            error_logger.warning(f"GitHub API returned status {response.status_code}")
            return True  # Not a critical error, continue
        
        release_data = response.json()
        latest_version = release_data.get('tag_name', '').replace('v', '')
        
        if not latest_version:
            print(f"   ⚠️  Keine Version gefunden")
            return True
        
        # Get current version from excavator
        current_version = None
        try:
            # Try to get version from running excavator or file
            if os.path.exists(excavator_path):
                # We can't easily determine version without running it
                # For now, we'll check if there's a version file
                version_file = Path(excavator_path).parent / "version.txt"
                if version_file.exists():
                    current_version = version_file.read_text().strip()
                else:
                    # No version file means we should update
                    current_version = "0.0.0"
            else:
                current_version = "0.0.0"  # No excavator installed
        except Exception as e:
            error_logger.debug(f"Could not determine current version: {e}")
            current_version = "0.0.0"
        
        print(f"   Installiert: {current_version}")
        print(f"   Verfügbar:   {latest_version}")
        
        # Compare versions - handle versions with letters like "1.7.1d"
        try:
            # Normalize versions by removing letter suffixes for comparison
            def normalize_version(v):
                """Remove letter suffixes like 'd', 'a', 'b' from version string."""
                import re
                # Extract just the numeric version (e.g., "1.7.1d" -> "1.7.1")
                match = re.match(r'(\d+\.\d+\.\d+)', v)
                return match.group(1) if match else v
            
            current_normalized = normalize_version(current_version)
            latest_normalized = normalize_version(latest_version)
            
            # If normalized versions are equal, compare the full strings
            if current_normalized == latest_normalized:
                # Same base version - compare full strings including letters
                if current_version == latest_version:
                    print(f"   ✅ Excavator ist aktuell")
                    return True
            elif version.parse(current_normalized) > version.parse(latest_normalized):
                # Current version is newer
                print(f"   ✅ Excavator ist aktuell")
                return True
        except Exception as e:
            error_logger.debug(f"Version comparison failed: {e}, will update")
        
        # Check if Excavator is running before attempting update
        excavator_running = False
        excavator_proc = None
        try:
            for proc in psutil.process_iter(['name', 'exe', 'pid']):
                if proc.info['name'] and 'excavator' in proc.info['name'].lower():
                    excavator_running = True
                    excavator_proc = proc
                    break
        except:
            pass
        
        if excavator_running:
            # Check if AUTO_UPDATE_EXCAVATOR_STOP is enabled
            auto_stop = os.getenv('AUTO_UPDATE_EXCAVATOR_STOP', 'False').lower() in ('1', 'true', 'yes')
            
            if not auto_stop:
                print(f"   ⚠️  Excavator läuft bereits - Update wird übersprungen")
                print(f"   💡 TIPP: Setze AUTO_UPDATE_EXCAVATOR_STOP=True in .env für automatisches Stop-Update-Restart")
                print(f"   💡 ODER: Beende Excavator manuell und starte Script neu")
                error_logger.warning(f"Excavator update skipped - process is running (version {current_version} -> {latest_version} available)")
                return True
            
            # Auto-stop is enabled - stop Excavator for update
            print(f"   ⚠️  Excavator läuft (PID {excavator_proc.info['pid']})")
            print(f"   🛑 Stoppe Excavator für Update (AUTO_UPDATE_EXCAVATOR_STOP=True)...")
            error_logger.info(f"Stopping Excavator (PID {excavator_proc.info['pid']}) for auto-update")
            
            try:
                # Try graceful shutdown via API first
                try:
                    api_response = requests.post(
                        f'http://{os.getenv("EXCAVATOR_API_HOST", "127.0.0.1")}:{os.getenv("EXCAVATOR_API_PORT", "3456")}',
                        json={"id": 1, "method": "quit", "params": []},
                        timeout=5
                    )
                    print(f"   ✓ API quit command sent")
                    time.sleep(3)  # Wait for graceful shutdown
                except Exception as api_err:
                    error_logger.debug(f"API quit failed: {api_err}")
                
                # Check if still running, terminate if needed
                if excavator_proc.is_running():
                    print(f"   ⏳ Beende Prozess...")
                    excavator_proc.terminate()
                    try:
                        excavator_proc.wait(timeout=10)
                        print(f"   ✓ Excavator gestoppt")
                    except psutil.TimeoutExpired:
                        print(f"   ⚠️  Timeout - force kill...")
                        excavator_proc.kill()
                        excavator_proc.wait(timeout=5)
                        print(f"   ✓ Excavator beendet")
                else:
                    print(f"   ✓ Excavator bereits gestoppt")
                    
                error_logger.info("Excavator stopped successfully for update")
                
            except Exception as stop_err:
                print(f"   ❌ Fehler beim Stoppen: {stop_err}")
                error_logger.error(f"Failed to stop Excavator: {stop_err}")
                print(f"   ⚠️  Update wird übersprungen")
                return True
        
        # Update needed
        print(f"\n📥 Lade Excavator {latest_version} herunter...")
        
        # Find Windows download
        download_url = None
        for asset in release_data.get('assets', []):
            if 'windows' in asset['name'].lower() or asset['name'].endswith('.zip'):
                download_url = asset['browser_download_url']
                break
        
        if not download_url:
            print(f"   ❌ Keine Windows-Version gefunden")
            error_logger.error("No Windows download found in release")
            return True  # Continue anyway
        
        # Download to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            zip_path = temp_dir_path / "excavator.zip"
            
            print(f"   Downloading from {download_url}...")
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"   ✅ Download abgeschlossen")
            
            # Extract
            print(f"   📦 Extrahiere Archiv...")
            extract_dir = temp_dir_path / "extract"
            extract_dir.mkdir()
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find excavator.exe in extracted files
            new_excavator = None
            for root, dirs, files in os.walk(extract_dir):
                if 'excavator.exe' in files:
                    new_excavator = Path(root) / 'excavator.exe'
                    break
            
            if not new_excavator or not new_excavator.exists():
                print(f"   ❌ excavator.exe nicht im Archiv gefunden")
                error_logger.error("excavator.exe not found in downloaded archive")
                return True
            
            # Backup old version
            excavator_path_obj = Path(excavator_path)
            if excavator_path_obj.exists():
                backup_path = excavator_path_obj.parent / f"excavator_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.exe"
                print(f"   💾 Sichere alte Version nach {backup_path.name}...")
                shutil.copy2(excavator_path, backup_path)
            
            # Replace with new version
            print(f"   📥 Installiere neue Version...")
            shutil.copy2(new_excavator, excavator_path)
            
            # Save version file
            version_file = excavator_path_obj.parent / "version.txt"
            version_file.write_text(latest_version)
            
            print(f"   ✅ Excavator erfolgreich aktualisiert auf {latest_version}!")
            error_logger.info(f"Excavator updated to version {latest_version}")
            
            return True
            
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️  Netzwerkfehler beim Update-Check: {e}")
        error_logger.warning(f"Network error during update check: {e}")
        return True  # Continue anyway
    except Exception as e:
        print(f"   ❌ Fehler beim Excavator-Update: {e}")
        error_logger.error(f"Excavator update failed: {e}")
        error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return True  # Continue anyway, don't block startup


def check_and_update_huawei_solar():
    """
    Check for updates to huawei-solar Python package and auto-update if available.
    
    Returns:
        bool: True if update was performed or not needed, False if error occurred
    """
    try:
        print("\n🔍 Prüfe auf huawei-solar Updates...")
        error_logger.info("Checking for huawei-solar package updates")
        
        # Get currently installed version
        try:
            current_version = pkg_resources.get_distribution('huawei-solar').version
            print(f"   Installiert: {current_version}")
        except Exception as e:
            print(f"   ⚠️  Konnte installierte Version nicht ermitteln: {e}")
            current_version = "0.0.0"
        
        # Check latest version on PyPI and pick newest compatible release for this Python
        try:
            response = requests.get('https://pypi.org/pypi/huawei-solar/json', timeout=10)
            if response.status_code == 200:
                pypi_data = response.json()
                latest_version = pypi_data['info']['version']

                # Determine the newest release that has files compatible with current Python
                releases = pypi_data.get('releases', {})
                from packaging.specifiers import SpecifierSet
                py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

                compatible_versions = []
                # Iterate versions in descending order to find compatible releases
                from packaging.version import parse as vparse
                sorted_versions = sorted(releases.keys(), key=vparse, reverse=True)
                for ver in sorted_versions:
                    files = releases.get(ver, [])
                    for f in files:
                        req_py = f.get('requires_python') or pypi_data['info'].get('requires_python') or ''
                        if not req_py:
                            # No restriction, assume compatible
                            compatible_versions.append(ver)
                            break
                        try:
                            spec = SpecifierSet(req_py)
                            if spec.contains(py_version):
                                compatible_versions.append(ver)
                                break
                        except Exception:
                            # If parsing fails, skip this file
                            continue

                if not compatible_versions:
                    # No compatible release found
                    print(f"   ⚠️  Keine mit Python {sys.version_info.major}.{sys.version_info.minor} kompatible Version auf PyPI gefunden")
                    error_logger.warning(f"No compatible huawei-solar release for Python {py_version}")
                    return True

                # Prefer stable (non-prerelease) versions first
                def is_prerelease(ver_str):
                    try:
                        pv = version.parse(ver_str)
                        return pv.is_prerelease
                    except Exception:
                        # Fallback: consider versions containing letters as prerelease
                        return any(x in ver_str for x in ['a', 'b', 'rc'])

                stable_versions = [v for v in compatible_versions if not is_prerelease(v)]
                latest_compatible = stable_versions[0] if stable_versions else compatible_versions[0]
                print(f"   Verfügbar (neueste kompatible): {latest_compatible}")
            else:
                print(f"   ⚠️  PyPI nicht erreichbar (Status {response.status_code})")
                return True
        except Exception as e:
            print(f"   ⚠️  Konnte PyPI nicht abfragen: {e}")
            error_logger.warning(f"PyPI query failed: {e}")
            return True
        
        # Compare versions - use the newest compatible version
        try:
            installed_ver = version.parse(current_version)
            target_ver = version.parse(latest_compatible)

            # If installed is a prerelease (beta/rc) and newer than the latest stable compatible,
            # don't automatically downgrade unless explicitly allowed via env var AUTO_UPDATE_FORCE_STABLE
            if installed_ver.is_prerelease and installed_ver > target_ver:
                force_stable = os.getenv('AUTO_UPDATE_FORCE_STABLE', 'False').lower() in ('1', 'true', 'yes')
                print(f"   ⚠️  Installierte Version ist eine Pre-Release: {current_version}")
                print(f"   Neueste stabile kompatible Version: {latest_compatible}")
                if not force_stable:
                    print("   ⏭️  Downgrade wird übersprungen. Setze AUTO_UPDATE_FORCE_STABLE=True in .env um automatisch auf stabile Versionen zu wechseln.")
                    error_logger.info("Skipping downgrade from prerelease to stable (AUTO_UPDATE_FORCE_STABLE not set)")
                    return True
                else:
                    print("   ⚠️  AUTO_UPDATE_FORCE_STABLE=true - Downgrading to latest stable compatible version...")

            if installed_ver >= target_ver:
                print(f"   ✅ huawei-solar ist aktuell (installed: {current_version})")
                return True
        except Exception as e:
            error_logger.debug(f"Version comparison failed: {e}, will attempt update")

        # Update needed
        print(f"\n📥 Aktualisiere huawei-solar auf {latest_compatible}...")
        
        # Run pip upgrade using sys.executable (correct Python interpreter)
        # Install the specific compatible version (pin to avoid pre-release incompatibles)
        try:
            install_target = f"huawei-solar=={latest_compatible}"
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', install_target],
                capture_output=True,
                text=True,
                timeout=240
            )
        except Exception as e:
            print(f"   ❌ Fehler beim Ausführen von pip: {e}")
            error_logger.error(f"pip execution failed: {e}")
            return True
        
        if result.returncode == 0:
            print(f"   ✅ huawei-solar erfolgreich aktualisiert!")
            error_logger.info(f"huawei-solar updated to version {latest_version}")

            # Verify new version using pip show via the same interpreter (avoids pkg_resources cache issues)
            try:
                proc = subprocess.run(
                    [sys.executable, '-m', 'pip', 'show', 'huawei-solar'],
                    capture_output=True, text=True, timeout=30
                )
                if proc.returncode == 0 and proc.stdout:
                    for line in proc.stdout.splitlines():
                        if line.startswith('Version:'):
                            new_version = line.split(':', 1)[1].strip()
                            print(f"   Neue Version: {new_version}")
                            break
                else:
                    # Fallback to pkg_resources
                    import importlib
                    importlib.reload(pkg_resources)
                    new_version = pkg_resources.get_distribution('huawei-solar').version
                    print(f"   Neue Version: {new_version}")
            except Exception as e:
                print(f"   ⚠️  Konnte neue Version nicht überprüfen: {e}")

            return True
        else:
            print(f"   ❌ Update fehlgeschlagen:")
            print(f"   {result.stderr}")
            error_logger.error(f"huawei-solar update failed: {result.stderr}")
            return True  # Continue anyway
            
    except subprocess.TimeoutExpired:
        print(f"   ⚠️  pip install timeout")
        error_logger.warning("pip install timeout during huawei-solar update")
        return True
    except Exception as e:
        print(f"   ❌ Fehler beim huawei-solar Update: {e}")
        error_logger.error(f"huawei-solar update failed: {e}")
        error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
        return True  # Continue anyway


class NiceHashAPI:
    """NiceHash API für Earnings/Stats."""
    
    def __init__(self, wallet_address):
        self.wallet_address = wallet_address.split('.')[0]  # Nur Wallet ohne Worker-Name
        self.api_url = NICEHASH_API_URL
        
    def get_mining_address_stats(self):
        """Holt Statistiken für Mining-Adresse."""
        try:
            url = f"{self.api_url}/{self.wallet_address}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception as e:
            return None
    
    def get_earnings_info(self):
        """Extrahiert wichtige Earnings-Informationen."""
        stats = self.get_mining_address_stats()
        
        if not stats or 'unpaidAmount' not in stats:
            return None
        
        return {
            'unpaid_btc': float(stats.get('unpaidAmount', 0)),
            'total_balance_btc': float(stats.get('totalBalance', 0)),
            'total_paid_btc': float(stats.get('totalPaidAmount', 0)),
        }
    
    def format_btc(self, btc_amount):
        """Formatiert BTC Betrag schön."""
        if btc_amount >= 0.01:
            return f"{btc_amount:.8f} BTC"
        else:
            # Zeige in Satoshis wenn sehr klein
            sats = btc_amount * 100_000_000
            return f"{sats:.0f} sats"


class GPUMonitor:
    """Überwacht GPU-Nutzung durch andere Prozesse."""
    
    def __init__(self, gpu_id=0, threshold=10):
        self.gpu_id = gpu_id
        self.threshold = threshold
        self.excavator_pid = None
        self.current_script_pid = os.getpid()  # PID vom Controller-Script selbst
        self.mining_active = False  # Flag ob Mining gerade läuft
        
    def set_excavator_pid(self, pid):
        """Speichert PID von Excavator um ihn zu ignorieren."""
        self.excavator_pid = pid
    
    def set_mining_active(self, active):
        """Setzt Flag ob Mining gerade läuft."""
        self.mining_active = active
        
    def get_gpu_usage_by_others(self):
        """
        Prüft ob andere Prozesse (außer Excavator und Mining-Script) die GPU nutzen.
        Returns: (is_gpu_busy, usage_percent, process_name)
        """
        try:
            gpus = GPUtil.getGPUs()
            if not gpus or len(gpus) <= self.gpu_id:
                return False, 0, None
            
            gpu = gpus[self.gpu_id]
            total_gpu_load = gpu.load * 100  # In Prozent
            
            # Wenn GPU Last sehr niedrig ist, nichts anderes läuft
            if total_gpu_load < self.threshold:
                return False, total_gpu_load, None
            
            # Bekannte Gaming/GPU-intensive Prozesse (OHNE python.exe - zu generisch)
            gpu_intensive_processes = [
                'RocketLeague.exe',
                'ComfyUI',
                'stable-diffusion-webui',
                'AUTOMATIC1111',
                'InvokeAI',
                'blender.exe',
                'Unity.exe',
                'UnrealEditor.exe',
                'UE4Editor.exe',
                'UE5Editor.exe',
                '3dsmax.exe',
                'maya.exe',
                'AfterFX.exe',
                'Premiere.exe',
                'DaVinciResolve.exe',
                'obs64.exe',
                'obs32.exe',
                'StreamlabsOBS.exe',
                # Gaming
                'RainbowSix.exe',
                'FortniteClient-Win64-Shipping.exe',
                'cs2.exe',
                'csgo.exe',
                'valorant.exe',
                'Overwatch.exe',
                'apex_legends.exe',
                'destiny2.exe',
                'GTA5.exe',
                'Cyberpunk2077.exe',
                'witcher3.exe',
            ]
            
            # PIDs die wir ignorieren müssen
            ignored_pids = {self.current_script_pid}
            if self.excavator_pid:
                ignored_pids.add(self.excavator_pid)
            
            # Suche nach bekannten GPU-Prozessen
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_pid = proc.info['pid']
                    proc_name = proc.info['name']
                    
                    # Ignoriere Mining-relevante Prozesse
                    if proc_pid in ignored_pids:
                        continue
                    
                    # Ignoriere excavator.exe auch ohne PID (falls mehrfach gestartet)
                    if 'excavator' in proc_name.lower():
                        continue
                    
                    # Prüfe ob bekannter GPU-Prozess läuft
                    if any(known.lower() in proc_name.lower() for known in gpu_intensive_processes):
                        # Wenn GPU-Last hoch ist UND ein bekannter Prozess läuft
                        if total_gpu_load > self.threshold:
                            return True, total_gpu_load, proc_name
                    
                    # Special case: python.exe - check if it's NOT our script
                    if 'python' in proc_name.lower() and total_gpu_load > 30:
                        # Check command line for Stable Diffusion indicators
                        try:
                            cmdline = ' '.join(proc.cmdline())
                            sd_keywords = ['stable-diffusion', 'comfy', 'automatic1111', 'invoke', 'diffusers', 'torch']
                            if any(kw in cmdline.lower() for kw in sd_keywords):
                                return True, total_gpu_load, f"Python (Stable Diffusion)"
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # IMPORTANT: When mining is active, high GPU load is NORMAL
            # Only pause at >80% AND mining is NOT active
            # This avoids false positives from the miner itself
            if not self.mining_active and total_gpu_load > 80:
                return True, total_gpu_load, "Unknown GPU-intensive Process"
            
            return False, total_gpu_load, None
            
        except Exception as e:
            error_logger.error(f"GPU monitoring error: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"GPU ID: {self.gpu_id}, Threshold: {self.threshold}, Mining Active: {self.mining_active}")
            print(f"⚠️ {t('gpu_monitoring_error')}: {e}")
            return False, 0, None


class QuickMinerAPI:
    """API Wrapper für NiceHash QuickMiner (REST API auf Port 18000)."""
    
    def __init__(self, host="localhost", port=18000):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.consecutive_errors = 0
        self.last_successful_command = None
        self.miner_type = "QuickMiner"
        # Get API auth token from config
        self.auth_token = self._get_auth_token()
    
    def _get_auth_token(self):
        """Read API auth token from QuickMiner config."""
        try:
            config_path = os.path.join(os.path.dirname(QUICKMINER_PATH), "nhqm.conf")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get("watchDogAPIAuth", "")
        except:
            pass
        return ""
        
    def send_command(self, method, params=None, retries=3):
        """
        Emuliert Excavator API für Kompatibilität.
        Mappt Excavator-Befehle zu QuickMiner REST API.
        """
        # QuickMiner nutzt Auto-Profit-Switching, daher sind
        # algorithm.add/worker.add nicht nötig
        if method in ["algorithm.add", "algorithm.remove", "algorithm.clear"]:
            # QuickMiner managed algorithms automatically
            return {"id": 1, "error": None}
        
        if method == "subscribe":
            # QuickMiner manages connection automatically
            return {"id": 1, "error": None}
        
        if method == "worker.add":
            # QuickMiner: Enable specific device via /enable endpoint
            # params = [algorithm_name, device_id]
            if params and len(params) >= 2:
                device_id = params[1]
                success = self.enable_device(device_id)
                return {"id": 1, "error": None, "worker_id": device_id} if success else {"id": 1, "error": "Failed to enable device"}
            return {"id": 1, "error": None, "worker_id": 0}
        
        if method == "worker.list":
            return self._get_workers()
        
        if method == "worker.clear":
            # Stop all GPUs via /quickstop
            success = self.stop_mining()
            return {"id": 1, "error": None} if success else {"id": 1, "error": "Failed to stop mining"}
        
        if method == "worker.free":
            # QuickMiner: Disable specific device via /disable endpoint
            # params = [worker_id] where worker_id == device_id
            if params and len(params) >= 1:
                device_id = params[0]
                success = self.disable_device(device_id)
                return {"id": 1, "error": None} if success else {"id": 1, "error": "Failed to disable device"}
            return {"id": 1, "error": None}
        
        if method == "info":
            return self._get_info()
        
        # Fallback für unbekannte Commands
        return {"id": 1, "error": f"Command {method} not supported by QuickMiner"}
    
    def _get_workers(self):
        """Holt Worker-Info von QuickMiner via /workers endpoint."""
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/workers", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.consecutive_errors = 0
                self.last_successful_command = datetime.now()
                return data  # Already in correct format
        except Exception as e:
            self.consecutive_errors += 1
            error_logger.warning(f"QuickMiner API error: {e}")
        
        return {"workers": [], "id": 1, "error": "Failed to get workers"}
    
    def _get_info(self):
        """Holt Miner-Info via /info endpoint."""
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/info", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data  # Already in correct format
        except Exception as e:
            error_logger.warning(f"QuickMiner info error: {e}")
        
        # Return None on error so caller can detect failure
        return None
    
    def is_mining(self):
        """Prüft ob QuickMiner aktiv mined via /workers endpoint."""
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/workers", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Check if there are any active workers
                workers = data.get("workers", [])
                return len(workers) > 0
        except:
            pass
        return False
    
    def get_info(self):
        """Public method to get miner info (calls _get_info)."""
        return self._get_info()
    
    def get_workers(self):
        """Public method to get workers list (extracts from _get_workers response)."""
        result = self._get_workers()
        return result.get("workers", [])
    
    def get_hashrate(self):
        """Returns total hashrate and per-GPU breakdown."""
        workers = self.get_workers()
        total_hashrate = 0
        gpu_hashrates = {}
        
        if workers:
            for worker in workers:
                device_id = worker.get("device_id", "?")
                if "algorithms" in worker and worker["algorithms"]:
                    speed = worker["algorithms"][0].get("speed", 0)
                    gpu_hashrates[device_id] = speed
                    total_hashrate += speed
        
        return total_hashrate, gpu_hashrates
    
    def start_mining(self, device_ids=None, algorithm=None, pool=None, wallet=None):
        """
        Startet Mining via /quickstart endpoint.
        
        Parameters are ignored - QuickMiner manages devices, algorithms, and pools automatically.
        They're accepted for API compatibility with ExcavatorAPI.
        """
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            
            # Get wallet and worker from config
            config_path = os.path.join(os.path.dirname(QUICKMINER_PATH), "nhqm.conf")
            wallet_id = NICEHASH_WALLET  # From .env
            
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    btc = config.get("authorization", {}).get("BTC")
                    worker = config.get("authorization", {}).get("workerName", "worker1")
                    if btc:
                        wallet_id = f"{btc}.{worker}"
            
            # The /quickstart endpoint requires: id (wallet.worker), loc (pool), ip (pool IP)
            # QuickMiner auto-resolves pool location and IP, we use auto.nicehash.com
            params = {
                "id": wallet_id,
                "loc": "nhmp.auto.nicehash.com",
                "ip": "34.111.64.157"  # NiceHash pool IP (resolved by QuickMiner)
            }
            
            url = f"{self.base_url}/quickstart"
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("error") is None:
                    print("✓ Mining started successfully")
                    return True
                else:
                    print(f"⚠ Mining start error: {data.get('error')}")
                    return False
            else:
                print(f"⚠ HTTP error {response.status_code}")
                return False
                
        except Exception as e:
            error_logger.warning(f"QuickMiner start error: {e}")
            return False
    
    def stop_mining(self):
        """Stoppt Mining via /quickstop endpoint."""
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/quickstop", headers=headers, timeout=5)
            return response.status_code == 200 and response.json().get("error") is None
        except Exception as e:
            error_logger.warning(f"QuickMiner stop error: {e}")
            return False
    
    def enable_device(self, device_id, algo=None, retries=3):
        """
        Enables a specific GPU via /enable endpoint.
        
        QuickMiner requires GPU UUID (not numeric ID) and algorithm name.
        Example: /enable?id=GPU-xxx&algo=kawpow
        """
        try:
            # Get GPU UUID for this device ID
            uuid = self._get_device_uuid(device_id)
            if not uuid:
                error_logger.warning(f"Could not find UUID for device {device_id}")
                return False
            
            # Use provided algo or detect from current workers
            if algo is None:
                algo = self._get_current_algorithm() or ""

            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            params = {"id": uuid, "algo": algo}

            last_err = None
            for attempt in range(retries):
                try:
                    response = requests.get(f"{self.base_url}/enable", params=params, headers=headers, timeout=5)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("error") is None:
                            return True
                        else:
                            last_err = result.get("error")
                            error_logger.warning(f"Enable device attempt {attempt+1} error: {last_err}")
                    else:
                        last_err = f"HTTP {response.status_code}"
                except Exception as e:
                    last_err = str(e)

                # small backoff between attempts
                time.sleep(1 + attempt)

            error_logger.warning(f"Enable device failed after {retries} retries: {last_err}")
            return False
        except Exception as e:
            error_logger.warning(f"QuickMiner enable device error: {e}")
            return False
    
    def disable_device(self, device_id):
        """
        Disables a specific GPU via /disable endpoint.
        
        QuickMiner requires GPU UUID (not numeric ID).
        Example: /disable?id=GPU-xxx
        """
        try:
            # Get GPU UUID for this device ID
            uuid = self._get_device_uuid(device_id)
            if not uuid:
                error_logger.warning(f"Could not find UUID for device {device_id}")
                return False
            
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/disable", params={"id": uuid}, headers=headers, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("error") is None
            return False
        except Exception as e:
            error_logger.warning(f"QuickMiner disable device error: {e}")
            return False
    
    def _get_device_uuid(self, device_id):
        """Get GPU UUID from numeric device ID."""
        try:
            headers = {"Authorization": self.auth_token} if self.auth_token else {}
            response = requests.get(f"{self.base_url}/devices_cuda", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                devices = data.get("devices", [])
                # Device ID might be string or int
                device_id_str = str(device_id)
                for device in devices:
                    if str(device.get("id", "")) == device_id_str:
                        return device.get("uuid")
            return None
        except Exception as e:
            error_logger.warning(f"Failed to get device UUID: {e}")
            return None
    
    def _get_current_algorithm(self):
        """Get currently active algorithm from workers."""
        try:
            workers = self.get_workers()
            if workers and len(workers) > 0:
                # Get algorithm from first active worker
                if "algorithms" in workers[0] and workers[0]["algorithms"]:
                    return workers[0]["algorithms"][0].get("name", "")
            return ""
        except:
            return ""


class ExcavatorAPI:
    """API Wrapper für Excavator Miner."""
    
    def __init__(self, host="127.0.0.1", port=3456):
        self.host = host
        self.port = port
        self.cmd_id = 1
        self.consecutive_errors = 0
        self.last_successful_command = None
        self.miner_type = "Excavator"
        
    def send_command(self, method, params=None, retries=3):
        """Sendet Kommando an Excavator API mit Retry-Logik."""
        if params is None:
            params = []
            
        cmd = {
            "id": self.cmd_id,
            "method": method,
            "params": params
        }
        self.cmd_id += 1
        
        last_error = None
        for attempt in range(retries):
            try:
                # Verbinde via TCP
                import socket
                
                # Try to determine if we need IPv6 (for QuickMiner on [::1]:18000)
                # or IPv4 (for standalone Excavator on 127.0.0.1:3456)
                family = socket.AF_INET  # Default: IPv4
                if self.host == "localhost" or self.host == "::1":
                    # QuickMiner uses IPv6
                    family = socket.AF_INET6
                    connect_host = "::1" if self.host == "localhost" else self.host
                else:
                    connect_host = self.host
                
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(10)  # Erhöht von 5 auf 10 Sekunden
                sock.connect((connect_host, self.port))
                
                # Sende Kommando
                message = json.dumps(cmd) + "\n"
                sock.sendall(message.encode())
                
                # Empfange Antwort
                response = b""
                while True:
                    chunk = sock.recv(1024)
                    if not chunk or b"\n" in chunk:
                        response += chunk
                        break
                    response += chunk
                
                sock.close()
                
                # Parse JSON
                response_str = response.decode().strip()
                if response_str:
                    self.consecutive_errors = 0
                    self.last_successful_command = datetime.now()
                    return json.loads(response_str)
                return None
                
            except ConnectionRefusedError as e:
                last_error = f"Verbindung verweigert (Port {self.port})"
                if attempt < retries - 1:
                    time.sleep(1)  # Warte 1s vor Retry
                    continue
            except socket.timeout:
                last_error = f"Timeout nach 10s"
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
        
        # All retries failed
        self.consecutive_errors += 1
        
        # Detailed error logging
        error_logger.error(f"Excavator API error ({self.consecutive_errors}x): {last_error}")
        error_logger.debug(f"Method: {method}, Params: {params}, Retries: {retries}")
        error_logger.debug(f"Host: {self.host}, Port: {self.port}, Command ID: {self.cmd_id-1}")
        error_logger.debug(f"Last successful command: {self.last_successful_command}")

        # If Excavator process is available, log PID/ memory/CPU for diagnostics
        try:
            if hasattr(self, 'controller') and self.controller and self.controller.excavator_process:
                pid = self.controller.excavator_process.pid
                error_logger.debug(f"Excavator PID: {pid}")
                try:
                    p = psutil.Process(pid)
                    mem = p.memory_info().rss / (1024*1024)
                    cpu = p.cpu_percent(interval=0.1)
                    error_logger.debug(f"Excavator Memory: {mem:.1f} MB, CPU%: {cpu}")
                except Exception as pe:
                    error_logger.debug(f"Could not read excavator process stats: {pe}")
        except Exception:
            pass
        
        # Only print every 10th error to avoid spam
        if self.consecutive_errors == 1 or self.consecutive_errors % 10 == 0:
            print(f"⚠️  {t('api_error', count=self.consecutive_errors)}: {last_error}")
            if self.consecutive_errors >= 30:
                print(f"⚠️  {t('excavator_not_responding')}")
                error_logger.warning(f"Excavator not responding for {self.consecutive_errors} attempts!")
        
        return None
    
    def is_mining(self):
        """Prüft ob aktiv gemined wird."""
        result = self.send_command("worker.list")
        if result and "workers" in result:
            return len(result["workers"]) > 0
        return False
    
    def get_workers(self):
        """Gibt Liste aller Worker zurück."""
        result = self.send_command("worker.list")
        if result and "workers" in result:
            return result["workers"]
        return []
    
    def start_mining(self, device_ids, algorithm, stratum_url, wallet):
        """Start mining on multiple GPUs (if not already active)."""
        try:
            # Check if already mining
            if self.is_mining():
                print(f"ℹ️  {t('mining_already_running')}")
                return True
                
            print(f"🔧 {t('configuring_mining')}")
            
            # 1. Subscribe to stratum
            result = self.send_command("subscribe", [stratum_url, wallet])
            if result is None:
                print(f"❌ {t('subscribe_no_response')}")
                return False
            if result.get("error"):
                print(f"❌ {t('subscribe_error')}: {result['error']}")
                return False
            print(f"   ✓ {t('subscribe_success')}")
            
            # 2. Add algorithm with fallback support
            result = self.send_command("algorithm.add", [algorithm])
            if result is None:
                print(f"❌ {t('algorithm_no_response')}")
                return False
            if result.get("error"):
                error_msg = result.get("error", "")
                print(f"❌ {t('algorithm_error')}: {error_msg}")
                
                return False
            print(f"   ✓ {t('algorithm_added', algo=algorithm)}")
            
            # 3. Add worker for each GPU
            workers_started = 0
            for device_id in device_ids:
                result = self.send_command("worker.add", [algorithm, device_id])
                if result is None:
                    print(f"❌ {t('worker_no_response')} (GPU {device_id})")
                    continue
                if result.get("error"):
                    print(f"❌ {t('worker_error')} (GPU {device_id}): {result['error']}")
                    continue
                
                worker_id = result.get("worker_id", 0)
                print(f"   ✓ {t('worker_started', id=worker_id)} (GPU {device_id})")
                workers_started += 1
            
            # Return success if at least one worker started
            if workers_started > 0:
                print(f"   ✅ {workers_started}/{len(device_ids)} GPUs gestartet")
                return True
            else:
                print(f"   ❌ Keine GPUs gestartet")
                return False
            
        except Exception as e:
            print(f"❌ {t('start_error')}: {e}")
            return False
    
    def stop_mining(self):
        """Stop mining completely (all workers and algorithms)."""
        try:
            # Check if mining at all
            if not self.is_mining():
                return True
                
            print(f"🔧 {t('stopping_mining')}")
            
            # 1. Clear all workers
            result = self.send_command("worker.clear")
            if result and result.get("error"):
                print(f"⚠️  {t('worker_error')}: {result['error']}")
            else:
                print(f"   ✓ {t('workers_cleared')}")
            
            # 2. Clear all algorithms
            result = self.send_command("algorithm.clear")
            if result and result.get("error"):
                print(f"⚠️  {t('algorithm_error')}: {result['error']}")
            else:
                print(f"   ✓ {t('algorithms_cleared')}")
            
            # 3. Disconnect from stratum
            result = self.send_command("unsubscribe")
            if result and result.get("error"):
                print(f"⚠️  {t('unsubscribe_error')}: {result['error']}")
            else:
                print(f"   ✓ {t('disconnected_from_stratum')}")
            
            return True
            
        except Exception as e:
            print(f"❌ {t('stop_error')}: {e}")
            return False
    
    def pause_worker(self, worker_id="0"):
        """Pausiert einen Worker (sanfter als stop_mining)."""
        try:
            result = self.send_command("worker.reset", {"worker_id": worker_id})
            if result and not result.get("error"):
                return True
            return False
        except:
            return False
    
    def resume_worker(self, worker_id="0"):
        """Setzt Worker fort (falls bereits konfiguriert)."""
        try:
            # Worker ist bereits konfiguriert, nur neu starten
            result = self.send_command("worker.reset", {"worker_id": worker_id})
            if result and not result.get("error"):
                return True
            return False
        except:
            return False
    
    def get_info(self):
        """Holt Excavator Info."""
        return self.send_command("info")
    
    def get_hashrate(self):
        """Returns total hashrate and per-GPU breakdown."""
        workers = self.get_workers()
        total_hashrate = 0
        gpu_hashrates = {}
        
        if workers:
            for worker in workers:
                device_id = worker.get("device_id", "?")
                if "algorithms" in worker and worker["algorithms"]:
                    speed = worker["algorithms"][0].get("speed", 0)
                    gpu_hashrates[device_id] = speed
                    total_hashrate += speed
        
        return total_hashrate, gpu_hashrates


def get_available_miner():
    """
    Automatische Miner-Erkennung.
    
    Priorität: QuickMiner > Excavator
    
    WICHTIG: QuickMiner managed alles selbst (Algorithmen, Workers, etc.)!
    QuickMiner startet excavator.exe mit JSON-RPC API auf Port 18000.
    Wir können QuickMiner's excavator DIREKT über die API steuern!
    """
    import psutil
    
    # 1. Prüfe ob QuickMiner-Prozess läuft (und damit excavator auf Port 18000)
    quickminer_running = False
    excavator_running = False
    
    for proc in psutil.process_iter(['name']):
        try:
            if 'NiceHashQuickMiner' in proc.info['name']:
                quickminer_running = True
            if 'excavator' in proc.info['name'].lower():
                excavator_running = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # 2. Wenn QuickMiner läuft, verwende dessen HTTP REST API auf Port 18000
    if quickminer_running and excavator_running:
        print(f"✅ QuickMiner erkannt!")
        print(f"   → Verwende QuickMiner's HTTP REST API (Port {QUICKMINER_API_PORT})")
        print(f"   → Unterstützt RTX 5000 Serie + moderne Algorithmen")
        print(f"   → Solar-basierte Start/Stop Steuerung aktiv")
        print(f"")
        # QuickMiner uses HTTP REST API, not JSON-RPC TCP sockets
        return QuickMinerAPI(QUICKMINER_API_HOST, QUICKMINER_API_PORT)
    
    # 3. Fallback: Standalone Excavator auf Port 3456
    if excavator_running and not quickminer_running:
        print(f"ℹ️  Standalone Excavator erkannt (Port {EXCAVATOR_API_PORT})")
        print(f"   ⚠️  HINWEIS: Standalone Excavator unterstützt KEINE RTX 5000 Serie!")
        print(f"   💡 Empfehlung: Verwende QuickMiner für bessere Kompatibilität")
        print(f"")
        return ExcavatorAPI(EXCAVATOR_API_HOST, EXCAVATOR_API_PORT)
    
    # 4. Kein Miner läuft - informiere User
    print(f"⚠️  Kein Miner gefunden!")
    print(f"")
    print(f"   Bitte starte einen Miner:")
    print(f"   • QuickMiner (empfohlen): {QUICKMINER_PATH}")
    print(f"   • Standalone Excavator: {EXCAVATOR_PATH}")
    print(f"")
    print(f"   Verwende QuickMiner für:")
    print(f"   ✓ RTX 5000 Serie Support")
    print(f"   ✓ Moderne Algorithmen (Autolykos2, KawPow, ETCHash, XelisHashV2)")
    print(f"   ✓ Automatisches Profit-Switching zwischen Algorithmen")
    print(f"")
    
    # Return QuickMiner API as default (user needs to start it)
    return ExcavatorAPI(QUICKMINER_API_HOST, QUICKMINER_API_PORT)


def log_gpu_health_event(event_type, gpu_id, gpu_name, stuck_algorithm, target_algorithm="", 
                         stuck_duration=0, hashrate_before=0, hashrate_after=0, 
                         miner_type="QuickMiner", notes=""):
    """
    Log GPU health events to CSV for later analysis.
    
    Event types:
    - 'stuck_detected': GPU detected with 0 hashrate
    - 'fix_attempted': Attempting to fix stuck GPU
    - 'fix_success': GPU successfully re-enabled
    - 'fix_failed': Failed to fix GPU
    - 'recovered': GPU recovered and producing hashrate
    """
    try:
        now = datetime.now()
        with open(GPU_HEALTH_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                now.strftime('%Y-%m-%d %H:%M:%S'),
                int(now.timestamp()),
                event_type,
                gpu_id,
                gpu_name,
                stuck_algorithm,
                target_algorithm,
                stuck_duration,
                hashrate_before,
                hashrate_after,
                miner_type,
                notes
            ])
    except Exception as e:
        error_logger.error(f"Failed to log GPU health event: {e}")


class SolarMiningController:
    def __init__(self):
        self.bridge = None
        self.excavator = get_available_miner()
        self.nicehash = NiceHashAPI(NICEHASH_WALLET)
        self.weather = WeatherAPI(WEATHER_LATITUDE, WEATHER_LONGITUDE) if WEATHER_ENABLED else None
        # Monitor first GPU for pause detection, but mine on all GPUs
        self.gpu_monitor = GPUMonitor(gpu_id=int(DEVICE_IDS[0]), threshold=GPU_USAGE_THRESHOLD)
        self.excavator_process = None
        self.is_mining = False
        self.start_confirmations = 0
        self.stop_confirmations = 0
        self.total_mining_time = 0
        self.mining_start_time = None
        self.gpu_paused = False  # Flag für GPU-Pause
        self.last_weather_data = {}  # Cache für Wetterdaten (immer verfügbar)
        
        # New: Mining failure tracking for immediate retry
        self.mining_start_failures = 0
        self.last_mining_attempt = None
        self.mining_retry_delay = 30  # seconds between immediate retries
        
        # Dynamic GPU scaling
        self.active_gpu_ids = []  # List of currently mining GPU IDs
        self.target_gpu_count = 0  # Target number of GPUs based on available power
        
        # GPU health monitoring (detect stuck GPUs with 0 hashrate)
        self.gpu_health_check_time = {}  # {device_id: last_check_time}
        self.gpu_zero_hashrate_start = {}  # {device_id: time_when_zero_started}
        self.gpu_health_check_interval = 120  # Check every 2 minutes
        self.gpu_zero_hashrate_threshold = 300  # 5 minutes of 0 hashrate = stuck
        # Auto-fix retry settings
        self.gpu_fix_retries = 3
        self.gpu_fix_retry_delay = 20  # seconds between retries
    
    def start_excavator(self):
        """Start miner if not already running (handles both QuickMiner and Excavator)."""
        # QuickMiner startet seinen eigenen Excavator - nur prüfen ob er läuft
        if self.excavator.port == QUICKMINER_API_PORT:
            info = self.excavator.get_info()
            # Check if API is actually responding (returns data, not None)
            if info:
                print(f"✓ QuickMiner's Excavator läuft bereits (Version: {info.get('version', 'unknown')})")
                print(f"  Port: {QUICKMINER_API_PORT}")
                return True
            else:
                print(f"⚠️  QuickMiner läuft, aber Excavator API nicht erreichbar!")
                print(f"  Starte QuickMiner neu oder warte kurz...")
                return False
        
        # Standalone Excavator-Logik (Port 3456)
        # Check if Excavator is already running
        info = self.excavator.get_info()
        if info:
            print(f"ℹ️  {t('excavator_already_running', version=info.get('version', 'unknown'))}")
            return True
        
        # Check if excavator.exe exists
        if not os.path.exists(EXCAVATOR_PATH):
            print(f"❌ {t('excavator_not_found')}: {EXCAVATOR_PATH}")
            print(f"   {t('please_adjust_path')}")
            return False
        
        try:
            print(f"🚀 {t('starting_excavator')}: {EXCAVATOR_PATH}")
            print(f"   {t('api_port')}: {EXCAVATOR_API_PORT}")
            
            # Rotate excavator logs if they are too big
            try:
                MAX_EXCAVATOR_LOG = 5 * 1024 * 1024
                for p in (EXCAVATOR_STDOUT, EXCAVATOR_STDERR):
                    if p.exists() and p.stat().st_size > MAX_EXCAVATOR_LOG:
                        # rotate: rename with timestamp
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        p.rename(p.with_name(p.stem + f"_{ts}" + p.suffix))
            except Exception as e:
                error_logger.debug(f"Could not rotate excavator logs: {e}")

            # Start Excavator in background and capture stdout/stderr to files
            try:
                stdout_f = open(EXCAVATOR_STDOUT, 'a', encoding='utf-8')
                stderr_f = open(EXCAVATOR_STDERR, 'a', encoding='utf-8')
            except Exception:
                stdout_f = subprocess.PIPE
                stderr_f = subprocess.PIPE

            self.excavator_process = subprocess.Popen(
                [EXCAVATOR_PATH, "-p", str(EXCAVATOR_API_PORT)],
                stdout=stdout_f,
                stderr=stderr_f,
                creationflags=subprocess.CREATE_NEW_CONSOLE  # Own window
            )
            
            # Set low process priority (gaming has priority!)
            try:
                import psutil
                p = psutil.Process(self.excavator_process.pid)
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows: Lower priority
                print(f"   ✓ {t('priority_set')}")
            except:
                pass
            
            # Wait until API is available
            print(f"   {t('waiting_for_api')}")
            for i in range(30):  # Max 30 seconds wait
                time.sleep(1)
                info = self.excavator.get_info()
                if info:
                    print(f"✅ {t('excavator_started', version=info.get('version', 'unknown'))}")
                    # Save PID for GPU monitoring
                    self.gpu_monitor.set_excavator_pid(self.excavator_process.pid)
                    print(f"   {t('pid')}: {self.excavator_process.pid}")
                    return True
                if i % 5 == 0 and i > 0:
                    print(f"   {t('remaining_seconds', seconds=30-i)}")
            
            print(f"❌ {t('excavator_start_timeout')}")
            error_logger.error("Excavator API not reachable after 30s")
            error_logger.debug(f"Excavator Path: {EXCAVATOR_PATH}")
            error_logger.debug(f"API Host: {self.excavator.host}, Port: {self.excavator.port}")
            error_logger.debug(f"Process PID: {self.excavator_process.pid if self.excavator_process else 'None'}")
            return False
            
        except Exception as e:
            print(f"❌ {t('excavator_start_error')}: {e}")
            error_logger.error(f"Excavator start error: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Excavator Path exists: {os.path.exists(EXCAVATOR_PATH)}")
            return False
    
    def check_excavator_health(self):
        """Check if Excavator is still responding and restart if necessary."""
        # Check if API responds
        info = self.excavator.get_info()
        
        if info:
            # All OK
            if self.excavator.consecutive_errors > 0:
                print(f"   ✅ Excavator API wieder erreichbar")
                error_logger.info("Excavator API recovered")
            return True
        
        # API not responding - check if process still running
        if self.excavator_process and self.excavator_process.poll() is None:
            # Process still running but API not responding
            if self.excavator.consecutive_errors >= 10:  # Reduced from 30 to 10
                print(f"\n⚠️  {t('excavator_process_not_responding')}")
                print(f"   API Timeouts: {self.excavator.consecutive_errors}x")
                print(f"   {t('terminating_old_process')}")
                error_logger.warning(f"Excavator frozen - API not responding after {self.excavator.consecutive_errors} attempts")
                error_logger.debug(f"PID: {self.excavator_process.pid}, Consecutive Errors: {self.excavator.consecutive_errors}")
                try:
                    print(f"   Beende Excavator (PID {self.excavator_process.pid})...")
                    self.excavator_process.terminate()
                    self.excavator_process.wait(timeout=5)
                except Exception as e:
                    error_logger.error(f"Error terminating Excavator: {e}")
                    print(f"   Force-Kill...")
                    self.excavator_process.kill()
                
                print(f"   Starte Excavator neu...")
                self.excavator_process = None
                self.excavator.consecutive_errors = 0
                return self.start_excavator()
        else:
            # Process crashed
            if self.excavator.consecutive_errors >= 5:  # Reduced from 10 to 5
                print(f"\n⚠️  {t('excavator_crashed')}")
                print(f"   {t('restarting_excavator')}")
                error_logger.error("Excavator process crashed - restarting")
                error_logger.debug(f"Consecutive Errors: {self.excavator.consecutive_errors}")
                self.excavator_process = None
                self.excavator.consecutive_errors = 0
                return self.start_excavator()
        
        return False
        
    async def connect(self):
        """Connect to inverter with unlimited retry logic."""
        RETRY_DELAY = 30  # seconds between retries
        CONNECTION_TIMEOUT = 60  # seconds for each connection attempt
        
        attempt = 0
        
        # Initial hint
        print()
        print("⚠️  HINWEIS: Falls die Verbindung fehlschlägt:")
        print("   → Schließe FusionSolar App und andere Monitoring-Software")
        print("   → Nur EIN Programm sollte gleichzeitig auf den Inverter zugreifen")
        print()
        
        while True:  # Infinite retry loop
            attempt += 1
            try:
                print(f"🔌 {t('connecting_to_inverter')} {INVERTER_HOST}:{INVERTER_PORT}... (Versuch {attempt})")
                
                # Wrap connection with timeout to prevent infinite hangs
                # Note: huawei-solar API changed - now uses create_tcp_bridge()
                self.bridge = await asyncio.wait_for(
                    create_tcp_bridge(host=INVERTER_HOST, port=INVERTER_PORT),
                    timeout=CONNECTION_TIMEOUT
                )
                
                print(f"✅ {t('inverter_connection_success')}")
                
                # Test connection with a simple read
                try:
                    test_read = await asyncio.wait_for(
                        self.bridge.client.get("input_power"),
                        timeout=10
                    )
                    print(f"✅ Verbindungstest erfolgreich (Solar: {test_read.value:.0f}W)")
                    
                    # If we had retries, warn about Modbus conflicts
                    if attempt > 1:
                        print()
                        print(f"⚠️  WARNUNG: Verbindung erst nach {attempt} Versuchen erfolgreich!")
                        print("   → Ein anderes Programm greift wahrscheinlich auf den Inverter zu")
                        print("   → Dies kann zu Instabilität und Datenverlusten führen")
                        print("   → Empfehlung: Schließe andere Modbus-Clients (FusionSolar App, etc.)")
                        print()
                        error_logger.warning(f"Connection successful only after {attempt} attempts - possible Modbus conflict")
                    
                except Exception as e:
                    error_logger.warning(f"Connection test read failed: {e}")
                    print(f"⚠️  Verbindung hergestellt, aber Test-Read fehlgeschlagen")
                
                break  # Successfully connected, exit loop
                
            except asyncio.TimeoutError:
                error_logger.error(f"Connection attempt {attempt} timed out after {CONNECTION_TIMEOUT}s")
                print(f"⏱️  Timeout nach {CONNECTION_TIMEOUT}s - Inverter antwortet nicht")
                print(f"⏳ Warte {RETRY_DELAY}s vor erneutem Verbindungsversuch...")
                if attempt == 1:
                    print(f"   💡 TIPP: Schließe jetzt FusionSolar App oder andere Monitoring-Software!")
                await asyncio.sleep(RETRY_DELAY)
                # Continue loop - no else needed anymore
                    
            except Exception as e:
                error_logger.error(f"Connection attempt {attempt} failed: {e}")
                error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
                
                # Check for specific Modbus conflict errors
                error_msg = str(e).lower()
                is_modbus_conflict = (
                    "interrupted" in error_msg or 
                    "another device" in error_msg or
                    "not connected" in error_msg or
                    "connection" in error_msg
                )
                
                print(f"⏳ Warte {RETRY_DELAY}s vor erneutem Verbindungsversuch...")
                if is_modbus_conflict:
                    print(f"   🔴 MODBUS-KONFLIKT ERKANNT!")
                    print(f"   → Ein anderes Programm greift auf den Inverter zu")
                    print(f"   → Schließe JETZT: FusionSolar App, Home Assistant, etc.")
                else:
                    print(f"   Fehler: {type(e).__name__}")
                await asyncio.sleep(RETRY_DELAY)
                # Continue loop
        
        # Start Excavator if needed
        print(f"\n🔌 {t('checking_excavator_api')} {self.excavator.host}:{self.excavator.port}...")
        if not self.start_excavator():
            raise Exception(t('excavator_could_not_start'))
    
    async def get_available_solar_power(self):
        """Read available solar power with timeout protection."""
        try:
            # Wrap Modbus reads with timeout to prevent hangs
            solar_power = await asyncio.wait_for(
                self.bridge.client.get("input_power"),
                timeout=MODBUS_CRITICAL_TIMEOUT
            )
            house_power = await asyncio.wait_for(
                self.bridge.client.get("power_meter_active_power"),
                timeout=MODBUS_CRITICAL_TIMEOUT
            )
            
            # Available power = feed-in (only what's left!)
            # house_power > 0: Feed-in to grid (available for mining)
            # house_power < 0: Grid import (nothing available, already drawing from grid)
            available = max(0, house_power.value)  # Only positive feed-in counts
            
            return solar_power.value, house_power.value, available
        except asyncio.TimeoutError:
            error_logger.warning(f"Timeout reading solar data after {MODBUS_CRITICAL_TIMEOUT}s (Modbus slow/busy)")
            print(f"Timeout while waiting for connection (>{MODBUS_CRITICAL_TIMEOUT}s). Reconnecting...")
            raise  # Re-raise to trigger reconnection logic
        except Exception as e:
            error_logger.error(f"Error reading solar data: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Bridge connected: {self.bridge is not None}")
            print(f"❌ {t('reading_error')}: {e}")
            raise  # Re-raise to trigger reconnection logic
    
    async def get_all_inverter_data(self):
        """Read ALL available inverter data with timeout protection."""
        data = {}
        
        try:
            # Basis Solar-Daten (critical - use longer timeout)
            data['input_power'] = (await asyncio.wait_for(
                self.bridge.client.get("input_power"), timeout=MODBUS_CRITICAL_TIMEOUT
            )).value
            data['power_meter_active_power'] = (await asyncio.wait_for(
                self.bridge.client.get("power_meter_active_power"), timeout=MODBUS_CRITICAL_TIMEOUT
            )).value
            
            # String-Daten (PV1 & PV2) - non-critical, fail silently
            try:
                data['pv_01_voltage'] = (await asyncio.wait_for(
                    self.bridge.client.get("pv_01_voltage"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['pv_01_current'] = (await asyncio.wait_for(
                    self.bridge.client.get("pv_01_current"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['pv_02_voltage'] = (await asyncio.wait_for(
                    self.bridge.client.get("pv_02_voltage"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['pv_02_current'] = (await asyncio.wait_for(
                    self.bridge.client.get("pv_02_current"), timeout=MODBUS_READ_TIMEOUT
                )).value
            except (asyncio.TimeoutError, Exception):
                pass
            
            # Grid-Daten (Phase 1, 2, 3) - non-critical, fail silently
            try:
                data['grid_A_voltage'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_A_voltage"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['grid_B_voltage'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_B_voltage"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['grid_C_voltage'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_C_voltage"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['grid_A_current'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_A_current"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['grid_B_current'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_B_current"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['grid_C_current'] = (await asyncio.wait_for(
                    self.bridge.client.get("grid_C_current"), timeout=MODBUS_READ_TIMEOUT
                )).value
            except (asyncio.TimeoutError, Exception):
                pass
            
            # Temperatur & Effizienz - non-critical, fail silently
            try:
                data['internal_temperature'] = (await asyncio.wait_for(
                    self.bridge.client.get("internal_temperature"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['efficiency'] = (await asyncio.wait_for(
                    self.bridge.client.get("efficiency"), timeout=MODBUS_READ_TIMEOUT
                )).value
            except (asyncio.TimeoutError, Exception):
                pass
            
            # Tages-Statistiken - non-critical, fail silently
            try:
                data['daily_yield_energy'] = (await asyncio.wait_for(
                    self.bridge.client.get("daily_yield_energy"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['accumulated_yield_energy'] = (await asyncio.wait_for(
                    self.bridge.client.get("accumulated_yield_energy"), timeout=MODBUS_READ_TIMEOUT
                )).value
            except (asyncio.TimeoutError, Exception):
                pass
            
            # Batterie (falls vorhanden) - non-critical, fail silently
            try:
                data['battery_charge_discharge_power'] = (await asyncio.wait_for(
                    self.bridge.client.get("storage_charge_discharge_power"), timeout=MODBUS_READ_TIMEOUT
                )).value
                data['battery_state_of_capacity'] = (await asyncio.wait_for(
                    self.bridge.client.get("storage_state_of_capacity"), timeout=MODBUS_READ_TIMEOUT
                )).value
            except (asyncio.TimeoutError, Exception):
                pass
            
            # Alarms & Status - important but non-critical
            try:
                alarm_1_raw = (await asyncio.wait_for(
                    self.bridge.client.get("alarm_1"), timeout=MODBUS_READ_TIMEOUT
                )).value
                alarm_2_raw = (await asyncio.wait_for(
                    self.bridge.client.get("alarm_2"), timeout=MODBUS_READ_TIMEOUT
                )).value
                alarm_3_raw = (await asyncio.wait_for(
                    self.bridge.client.get("alarm_3"), timeout=MODBUS_READ_TIMEOUT
                )).value
                
                # Verwende AlarmParser aus solar_core
                data['alarm_1'] = AlarmParser.extract_alarm_value(alarm_1_raw)
                data['alarm_2'] = AlarmParser.extract_alarm_value(alarm_2_raw)
                data['alarm_3'] = AlarmParser.extract_alarm_value(alarm_3_raw)
                data['device_status'] = (await self.bridge.client.get("device_status")).value
            except:
                pass
                
        except Exception as e:
            error_logger.error(f"Fehler beim Lesen von erweiterten Inverter-Daten: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
        
        return data
    
    async def check_inverter_alarms(self):
        """Prüft Inverter auf aktive Alarme und loggt sie mit vollständigem Kontext."""
        try:
            # Add timeout protection to alarm reads
            alarm_1 = await asyncio.wait_for(
                self.bridge.client.get("alarm_1"), 
                timeout=MODBUS_READ_TIMEOUT
            )
            alarm_2 = await asyncio.wait_for(
                self.bridge.client.get("alarm_2"), 
                timeout=MODBUS_READ_TIMEOUT
            )
            alarm_3 = await asyncio.wait_for(
                self.bridge.client.get("alarm_3"), 
                timeout=MODBUS_READ_TIMEOUT
            )
            device_status = await asyncio.wait_for(
                self.bridge.client.get("device_status"), 
                timeout=MODBUS_READ_TIMEOUT
            )
            
            # Verwende AlarmParser aus solar_core
            alarm_1_val, alarm_1_obj = AlarmParser.get_alarm_details(alarm_1)
            alarm_2_val, alarm_2_obj = AlarmParser.get_alarm_details(alarm_2)
            alarm_3_val, alarm_3_obj = AlarmParser.get_alarm_details(alarm_3)
            
            # Check if alarms are active (ID != 0 or alarm object present)
            has_alarms = (alarm_1_val != 0 or alarm_2_val != 0 or alarm_3_val != 0 or 
                         alarm_1_obj is not None or alarm_2_obj is not None or alarm_3_obj is not None)
            
            if has_alarms:
                print(f"\n⚠️  {t('alarm_warning')}")
                
                # === COMPLETE ALARM CONTEXT SNAPSHOT ===
                error_logger.error("=" * 80)
                error_logger.error("🚨 ALARM SNAPSHOT - Complete Inverter Diagnostics")
                error_logger.error("=" * 80)
                
                # Alarm-Details
                if alarm_1_obj:
                    error_logger.error(f"Alarm 1: {alarm_1_obj.name} (ID={alarm_1_obj.id}, Level={alarm_1_obj.level})")
                    print(f"   ⚠️  Alarm 1: {alarm_1_obj.name} (Level: {alarm_1_obj.level})")
                elif alarm_1_val != 0:
                    error_logger.warning(f"Alarm 1: Bitfeld = {alarm_1_val:016b} (0x{alarm_1_val:04X})")
                    print(f"   Alarm 1: {alarm_1_val:016b} (0x{alarm_1_val:04X})")
                
                if alarm_2_obj:
                    error_logger.error(f"Alarm 2: {alarm_2_obj.name} (ID={alarm_2_obj.id}, Level={alarm_2_obj.level})")
                    print(f"   ⚠️  Alarm 2: {alarm_2_obj.name} (Level: {alarm_2_obj.level})")
                elif alarm_2_val != 0:
                    error_logger.warning(f"Alarm 2: Bitfeld = {alarm_2_val:016b} (0x{alarm_2_val:04X})")
                    print(f"   Alarm 2: {alarm_2_val:016b} (0x{alarm_2_val:04X})")
                
                if alarm_3_obj:
                    error_logger.error(f"Alarm 3: {alarm_3_obj.name} (ID={alarm_3_obj.id}, Level={alarm_3_obj.level})")
                    print(f"   ⚠️  Alarm 3: {alarm_3_obj.name} (Level: {alarm_3_obj.level})")
                elif alarm_3_val != 0:
                    error_logger.warning(f"Alarm 3: Bitfeld = {alarm_3_val:016b} (0x{alarm_3_val:04X})")
                    print(f"   Alarm 3: {alarm_3_val:016b} (0x{alarm_3_val:04X})")
                
                error_logger.error(f"Device Status: {device_status.value}")
                print(f"   Status: {device_status.value}")
                
                # === GRID-STATUS (kritisch bei Grid Overvoltage!) ===
                try:
                    error_logger.error("\n📊 GRID-STATUS:")
                    grid_a_v = await self.bridge.client.get("grid_A_voltage")
                    grid_b_v = await self.bridge.client.get("grid_B_voltage")
                    grid_c_v = await self.bridge.client.get("grid_C_voltage")
                    grid_freq = await self.bridge.client.get("grid_frequency")
                    line_ab = await self.bridge.client.get("line_voltage_A_B")
                    line_bc = await self.bridge.client.get("line_voltage_B_C")
                    line_ca = await self.bridge.client.get("line_voltage_C_A")
                    
                    error_logger.error(f"  Phase A: {grid_a_v.value:.1f}V")
                    error_logger.error(f"  Phase B: {grid_b_v.value:.1f}V")
                    error_logger.error(f"  Phase C: {grid_c_v.value:.1f}V")
                    error_logger.error(f"  Frequency: {grid_freq.value:.2f}Hz")
                    error_logger.error(f"  Line A-B: {line_ab.value:.1f}V")
                    error_logger.error(f"  Line B-C: {line_bc.value:.1f}V")
                    error_logger.error(f"  Line C-A: {line_ca.value:.1f}V")
                except Exception as e:
                    error_logger.warning(f"  Grid-Daten nicht lesbar: {e}")
                
                # === PV-STRING-STATUS ===
                try:
                    error_logger.error("\n☀️ PV-STRINGS:")
                    pv1_v = await self.bridge.client.get("pv_01_voltage")
                    pv1_a = await self.bridge.client.get("pv_01_current")
                    pv2_v = await self.bridge.client.get("pv_02_voltage")
                    pv2_a = await self.bridge.client.get("pv_02_current")
                    input_power = await self.bridge.client.get("input_power")
                    
                    error_logger.error(f"  String 1: {pv1_v.value:.1f}V @ {pv1_a.value:.2f}A = {pv1_v.value * pv1_a.value:.0f}W")
                    error_logger.error(f"  String 2: {pv2_v.value:.1f}V @ {pv2_a.value:.2f}A = {pv2_v.value * pv2_a.value:.0f}W")
                    error_logger.error(f"  Total DC Input: {input_power.value:.0f}W")
                except Exception as e:
                    error_logger.warning(f"  PV-Daten nicht lesbar: {e}")
                
                # === INVERTER-TEMPERATUR ===
                try:
                    error_logger.error("\n🌡️ TEMPERATUREN:")
                    internal_temp = await self.bridge.client.get("internal_temperature")
                    error_logger.error(f"  Intern: {internal_temp.value:.1f}°C")
                    
                    # Falls Multi-Modul Temperaturen verfügbar
                    try:
                        inv_a = await self.bridge.client.get("inv_module_A_temp")
                        inv_b = await self.bridge.client.get("inv_module_B_temp")
                        inv_c = await self.bridge.client.get("inv_module_C_temp")
                        error_logger.error(f"  Modul A: {inv_a.value:.1f}°C")
                        error_logger.error(f"  Modul B: {inv_b.value:.1f}°C")
                        error_logger.error(f"  Modul C: {inv_c.value:.1f}°C")
                    except:
                        pass  # Nicht alle Modelle haben diese
                except Exception as e:
                    error_logger.warning(f"  Temperatur-Daten nicht lesbar: {e}")
                
                # === ZUSÄTZLICHE FEHLER-CODES ===
                try:
                    error_logger.error("\n🔍 FEHLER-DETAILS:")
                    fault_code = await self.bridge.client.get("fault_code")
                    error_logger.error(f"  Fault Code: {fault_code.value}")
                except Exception as e:
                    error_logger.warning(f"  Fault-Code nicht lesbar: {e}")
                
                # === ISOLATIONSWIDERSTAND (kritisch bei Shutdown) ===
                try:
                    insulation = await self.bridge.client.get("insulation_resistance")
                    error_logger.error(f"  Insulation Resistance: {insulation.value:.2f} MΩ")
                except Exception as e:
                    error_logger.warning(f"  Isolationswiderstand nicht lesbar: {e}")
                
                # === LECKSTROM ===
                try:
                    leakage = await self.bridge.client.get("leakage_current_RCD")
                    error_logger.error(f"  Leakage Current: {leakage.value:.2f} mA")
                except Exception as e:
                    error_logger.warning(f"  Leckstrom nicht lesbar: {e}")
                
                # === EFFIZIENZ & LEISTUNG ===
                try:
                    error_logger.error("\n⚡ LEISTUNG:")
                    efficiency = await self.bridge.client.get("efficiency")
                    active_power = await self.bridge.client.get("active_power")
                    error_logger.error(f"  Efficiency: {efficiency.value:.2f}%")
                    error_logger.error(f"  Active Power: {active_power.value:.0f}W")
                except Exception as e:
                    error_logger.warning(f"  Leistungs-Daten nicht lesbar: {e}")
                
                error_logger.error("=" * 80)
                error_logger.error("")  # Leerzeile für bessere Lesbarkeit
                print()
                
                return True
            
            return False
            
        except asyncio.TimeoutError:
            # Timeout during alarm check - not critical, just log and continue
            error_logger.warning(f"Timeout beim Prüfen von Inverter-Alarmen (Modbus busy)")
            return False
        except Exception as e:
            error_logger.error(f"Fehler beim Prüfen von Inverter-Alarmen: {e}")
            return False
    
    def calculate_target_gpu_count(self, available_power):
        """
        Berechnet die optimale Anzahl an GPUs basierend auf verfügbarer Leistung.
        
        Logik:
        - 1 GPU: MIN_POWER_TO_START (z.B. 400W)
        - 2 GPUs: 2 * MIN_POWER_TO_START (z.B. 800W)
        - etc.
        
        Returns: Anzahl GPUs die gestartet werden sollten (0 bis len(DEVICE_IDS))
        """
        if available_power < MIN_POWER_TO_START:
            return 0
        
        # Berechne wie viele GPUs wir mit der verfügbaren Power betreiben können
        max_gpus = min(
            int(available_power / MIN_POWER_TO_START),
            len(DEVICE_IDS)
        )
        
        return max_gpus
    
    def get_active_workers_device_ids(self):
        """
        Gibt Liste der Device IDs zurück, die aktuell als Worker laufen.
        """
        workers = self.excavator.get_workers()
        active_ids = []
        for worker in workers:
            device_id = worker.get("device_id")
            if device_id is not None:
                active_ids.append(str(device_id))
        return active_ids
    
    def _get_gpu_name(self, device_id):
        """Get GPU model name from device ID for logging."""
        try:
            if self.excavator.miner_type == "QuickMiner":
                # Try to get GPU name from QuickMiner API
                response = requests.get(
                    f"{self.excavator.base_url}/devices_cuda",
                    headers={"Authorization": self.excavator.auth_token} if self.excavator.auth_token else {},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("devices", [])
                    for device in devices:
                        if str(device.get("id", "")) == str(device_id):
                            return device.get("name", f"GPU {device_id}")
        except Exception as e:
            error_logger.debug(f"Could not get GPU name: {e}")
        
        return f"GPU {device_id}"
    
    async def check_and_fix_stuck_gpus(self):
        """
        Prüft ob GPUs mit 0 Hashrate feststecken und behebt dies automatisch.
        
        QuickMiner Issue: Manchmal bleibt eine GPU auf einem inkompatiblen Algorithmus
        stecken (z.B. ZelHash auf RTX 5060 Ti) und zeigt 0 MH/s.
        
        Diese Funktion erkennt solche Fälle und:
        1. Disabled die betroffene GPU
        2. Re-enabled sie mit einem kompatiblen Algorithmus
        """
        if not self.is_mining:
            return
        
        try:
            workers = self.excavator.get_workers()
            current_time = datetime.now()
            
            for worker in workers:
                device_id = str(worker.get("device_id", ""))
                
                # Get hashrate for this worker
                hashrate = 0
                if "algorithms" in worker and worker["algorithms"]:
                    hashrate = worker["algorithms"][0].get("speed", 0)
                
                # Initialize tracking for this GPU if first time
                if device_id not in self.gpu_zero_hashrate_start:
                    self.gpu_zero_hashrate_start[device_id] = None
                
                # Check if GPU has zero hashrate
                if hashrate == 0:
                    # Start tracking when zero hashrate began
                    if self.gpu_zero_hashrate_start[device_id] is None:
                        self.gpu_zero_hashrate_start[device_id] = current_time
                        algorithm = worker["algorithms"][0].get("name", "unknown")
                        print(f"   ⚠️  GPU {device_id} hashrate = 0 (starting monitoring)")
                        
                        # Log stuck detection
                        gpu_name = self._get_gpu_name(device_id)
                        log_gpu_health_event(
                            event_type='stuck_detected',
                            gpu_id=device_id,
                            gpu_name=gpu_name,
                            stuck_algorithm=algorithm,
                            hashrate_before=0,
                            miner_type=self.excavator.miner_type,
                            notes="GPU hashrate dropped to 0, started monitoring"
                        )
                    else:
                        # Calculate how long it's been stuck at 0
                        zero_duration = (current_time - self.gpu_zero_hashrate_start[device_id]).total_seconds()
                        
                        # If stuck for too long, fix it
                        if zero_duration > self.gpu_zero_hashrate_threshold:
                            algorithm = worker["algorithms"][0].get("name", "unknown")
                            gpu_name = self._get_gpu_name(device_id)
                            
                            print(f"\n   🔧 GPU {device_id} stuck at 0 MH/s for {int(zero_duration/60)} minutes!")
                            print(f"   Algorithm: {algorithm}")
                            print(f"   🔄 Automatically fixing GPU {device_id}...")
                            error_logger.warning(f"GPU {device_id} stuck at 0 MH/s on {algorithm} for {int(zero_duration/60)} min - auto-fixing")
                            
                            # Only attempt fix for QuickMiner (has enable/disable)
                            if self.excavator.miner_type == "QuickMiner":
                                # Get currently working algorithm from other GPUs
                                working_algo = None
                                for w in workers:
                                    if str(w.get("device_id", "")) != device_id:
                                        if "algorithms" in w and w["algorithms"]:
                                            speed = w["algorithms"][0].get("speed", 0)
                                            if speed > 0:
                                                working_algo = w["algorithms"][0].get("name")
                                                break
                                
                                # Default to kawpow if no other GPU is working
                                if not working_algo:
                                    working_algo = "kawpow"
                                
                                # Log fix attempt
                                log_gpu_health_event(
                                    event_type='fix_attempted',
                                    gpu_id=device_id,
                                    gpu_name=gpu_name,
                                    stuck_algorithm=algorithm,
                                    target_algorithm=working_algo,
                                    stuck_duration=int(zero_duration),
                                    hashrate_before=0,
                                    miner_type=self.excavator.miner_type,
                                    notes=f"Attempting to switch from {algorithm} to {working_algo}"
                                )
                                
                                # Try multiple disable/enable attempts
                                fixed = False
                                for attempt in range(1, self.gpu_fix_retries + 1):
                                    print(f"   → Fix attempt {attempt}/{self.gpu_fix_retries} for GPU {device_id}")
                                    # Try to disable
                                    success_disable = self.excavator.disable_device(device_id)
                                    if not success_disable:
                                        print(f"   ❌ Failed to disable GPU {device_id} on attempt {attempt}")
                                        error_logger.error(f"Failed to disable GPU {device_id} (attempt {attempt})")
                                        log_gpu_health_event(
                                            event_type='fix_attempted',
                                            gpu_id=device_id,
                                            gpu_name=gpu_name,
                                            stuck_algorithm=algorithm,
                                            target_algorithm=working_algo,
                                            stuck_duration=int(zero_duration),
                                            hashrate_before=0,
                                            miner_type=self.excavator.miner_type,
                                            notes=f"disable_failed_attempt_{attempt}"
                                        )
                                        # wait before next attempt
                                        await asyncio.sleep(self.gpu_fix_retry_delay)
                                        continue

                                    # Give miner a moment
                                    await asyncio.sleep(2)

                                    print(f"   ✓ Disabled GPU {device_id}, enabling with {working_algo} (attempt {attempt})")
                                    # Try to enable with chosen algorithm and allow QuickMinerAPI retries
                                    success_enable = self.excavator.enable_device(device_id, algo=working_algo, retries=max(1, self.gpu_fix_retries))
                                    if success_enable:
                                        print(f"   ✅ GPU {device_id} re-enabled on attempt {attempt}! Waiting for DAG build...")
                                        error_logger.info(f"GPU {device_id} successfully re-enabled with {working_algo} (attempt {attempt})")
                                        log_gpu_health_event(
                                            event_type='fix_success',
                                            gpu_id=device_id,
                                            gpu_name=gpu_name,
                                            stuck_algorithm=algorithm,
                                            target_algorithm=working_algo,
                                            stuck_duration=int(zero_duration),
                                            hashrate_before=0,
                                            miner_type=self.excavator.miner_type,
                                            notes=f"reenabled_attempt_{attempt}"
                                        )
                                        fixed = True
                                        # Reset tracking
                                        self.gpu_zero_hashrate_start[device_id] = None
                                        break
                                    else:
                                        print(f"   ❌ Enable failed on attempt {attempt} for GPU {device_id}")
                                        error_logger.error(f"Failed to enable GPU {device_id} (attempt {attempt})")
                                        log_gpu_health_event(
                                            event_type='fix_failed',
                                            gpu_id=device_id,
                                            gpu_name=gpu_name,
                                            stuck_algorithm=algorithm,
                                            target_algorithm=working_algo,
                                            stuck_duration=int(zero_duration),
                                            miner_type=self.excavator.miner_type,
                                            notes=f"enable_failed_attempt_{attempt}"
                                        )
                                        # wait before next attempt
                                        await asyncio.sleep(self.gpu_fix_retry_delay)

                                if not fixed:
                                    print(f"   ❌ All fix attempts failed for GPU {device_id}")
                                    error_logger.error(f"All fix attempts failed for GPU {device_id}")
                                    log_gpu_health_event(
                                        event_type='fix_failed',
                                        gpu_id=device_id,
                                        gpu_name=gpu_name,
                                        stuck_algorithm=algorithm,
                                        target_algorithm=working_algo,
                                        stuck_duration=int(zero_duration),
                                        miner_type=self.excavator.miner_type,
                                        notes="all_attempts_failed"
                                    )
                            else:
                                print(f"   ⚠️  Auto-fix only supported for QuickMiner")
                                # For standalone Excavator, just log the issue
                                error_logger.warning(f"GPU {device_id} stuck but auto-fix not available for standalone Excavator")
                                
                                log_gpu_health_event(
                                    event_type='fix_failed',
                                    gpu_id=device_id,
                                    gpu_name=gpu_name,
                                    stuck_algorithm=algorithm,
                                    stuck_duration=int(zero_duration),
                                    miner_type=self.excavator.miner_type,
                                    notes="Auto-fix not available for standalone Excavator"
                                )
                else:
                    # GPU has valid hashrate - reset tracking
                    if self.gpu_zero_hashrate_start[device_id] is not None:
                        algorithm = worker["algorithms"][0].get("name", "unknown")
                        gpu_name = self._get_gpu_name(device_id)
                        
                        print(f"   ✅ GPU {device_id} recovered! Hashrate: {hashrate/1000000:.2f} MH/s")
                        
                        # Log recovery
                        log_gpu_health_event(
                            event_type='recovered',
                            gpu_id=device_id,
                            gpu_name=gpu_name,
                            stuck_algorithm=algorithm,
                            hashrate_after=hashrate,
                            miner_type=self.excavator.miner_type,
                            notes=f"GPU producing hashrate: {hashrate/1000000:.2f} MH/s"
                        )
                    
                    self.gpu_zero_hashrate_start[device_id] = None
        
        except Exception as e:
            error_logger.error(f"Error in GPU health check: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
    
    async def scale_gpus(self, available_power):
        """
        Skaliert die Anzahl der mining GPUs basierend auf verfügbarer Power.
        
        Returns: (changed, active_count) - ob Änderungen gemacht wurden und aktuelle Anzahl
        """
        target_count = self.calculate_target_gpu_count(available_power)
        current_active = self.get_active_workers_device_ids()
        current_count = len(current_active)
        
        if target_count == current_count:
            return False, current_count
        
        changed = False
        
        # Mehr GPUs starten
        if target_count > current_count:
            gpus_to_add = target_count - current_count
            print(f"\n      📈 Mehr Power verfügbar - starte {gpus_to_add} weitere GPU(s)")
            
            # Finde GPUs die noch nicht laufen
            for device_id in DEVICE_IDS:
                if device_id not in current_active and gpus_to_add > 0:
                    # Worker für diese GPU hinzufügen
                    result = self.excavator.send_command("worker.add", [ALGORITHM, device_id])
                    if result and not result.get("error"):
                        worker_id = result.get("worker_id", "?")
                        print(f"      ✅ GPU {device_id} gestartet (Worker {worker_id})")
                        changed = True
                        gpus_to_add -= 1
                    else:
                        error = result.get("error") if result else "No response"
                        print(f"      ❌ GPU {device_id} Start fehlgeschlagen: {error}")
        
        # Weniger GPUs - einige stoppen
        elif target_count < current_count:
            gpus_to_remove = current_count - target_count
            print(f"\n      📉 Weniger Power - stoppe {gpus_to_remove} GPU(s)")
            
            # Stoppe die letzten GPUs (LIFO - Last In First Out)
            workers = self.excavator.get_workers()
            workers_to_stop = workers[-gpus_to_remove:] if gpus_to_remove < len(workers) else workers
            
            for worker in workers_to_stop:
                worker_id = worker.get("worker_id")
                device_id = worker.get("device_id", "?")
                result = self.excavator.send_command("worker.free", [worker_id])
                if result and not result.get("error"):
                    print(f"      ⏸️  GPU {device_id} gestoppt (Worker {worker_id})")
                    changed = True
                else:
                    error = result.get("error") if result else "No response"
                    print(f"      ⚠️  GPU {device_id} Stopp fehlgeschlagen: {error}")
        
        # Update active GPU list
        self.active_gpu_ids = self.get_active_workers_device_ids()
        return changed, len(self.active_gpu_ids)
    
    async def run(self):
        """Main loop."""
        print("=" * 80)
        print(f"⚡ {t('system_title').upper()}")
        print("=" * 80)
        print(f"GPU Devices: {', '.join(DEVICE_IDS)}")
        print(f"Algorithm: {ALGORITHM}")
        print(f"Wallet: {NICEHASH_WALLET.split('.')[0][:20]}...")
        print(f"Worker: {NICEHASH_WALLET.split('.')[1]}")
        print(f"Miner: {self.excavator.miner_type}")
        print(f"Dynamisches GPU-Scaling:")
        print(f"  • 1 GPU  = {MIN_POWER_TO_START}W")
        print(f"  • 2 GPUs = {2*MIN_POWER_TO_START}W")
        for i in range(3, len(DEVICE_IDS)+1):
            print(f"  • {i} GPUs = {i*MIN_POWER_TO_START}W")
        print(f"Stop bei: < {MIN_POWER_TO_KEEP}W (alle GPUs)")
        print(f"Check-Intervall: {CHECK_INTERVAL}s")
        print(f"Alarm-Check: {ALARM_CHECK_INTERVAL}s")
        print("=" * 80)
        print()
        
        # Initial Status
        self.is_mining = self.excavator.is_mining()
        if self.is_mining:
            print("ℹ️  Mining läuft bereits\n")
            self.mining_start_time = datetime.now()
            self.active_gpu_ids = self.get_active_workers_device_ids()
        else:
            print("ℹ️  Mining läuft nicht\n")
            
            # Check if we have enough power to start mining immediately
            try:
                print("🔍 Prüfe verfügbare Solar-Power für Auto-Start...")
                initial_solar, initial_house, initial_available = await self.get_available_solar_power()
                print(f"   Solar: {initial_solar:.0f}W | Verfügbar: {initial_available:.0f}W")
                
                target_gpu_count = self.calculate_target_gpu_count(initial_available)
                if target_gpu_count > 0:
                    print(f"   ✅ Genug Power für {target_gpu_count} GPU(s)!")
                    print(f"\n   🚀 STARTE MINING SOFORT MIT {target_gpu_count} GPU(s)!\n")
                    
                    gpus_to_start = DEVICE_IDS[:target_gpu_count]
                    success = self.excavator.start_mining(
                        gpus_to_start, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                    )
                    
                    if success:
                        self.is_mining = True
                        self.gpu_monitor.set_mining_active(True)
                        self.mining_start_time = datetime.now()
                        self.active_gpu_ids = self.get_active_workers_device_ids()
                        print(f"   ✅ Mining gestartet! GPUs: {', '.join(self.active_gpu_ids)}")
                    else:
                        print(f"   ⚠️  Mining-Start fehlgeschlagen - wird im Loop erneut versucht")
                else:
                    print(f"   ⏸️  Nicht genug Power ({initial_available:.0f}W < {MIN_POWER_TO_START}W)")
                    print(f"   → Mining startet automatisch wenn genug Solar-Power verfügbar ist")
                print()
            except Exception as e:
                error_logger.warning(f"Auto-start check failed: {e}")
                print(f"   ⚠️  Konnte Solar-Power nicht prüfen - normale Überwachung startet...\n")
        
        # Hole initiale Earnings
        print("💰 Hole NiceHash Earnings...")
        earnings = self.nicehash.get_earnings_info()
        if earnings:
            print(f"   Unbezahlt: {self.nicehash.format_btc(earnings['unpaid_btc'])}")
            print(f"   Gesamt bezahlt: {self.nicehash.format_btc(earnings['total_paid_btc'])}")
        else:
            print("   ⚠️  Earnings noch nicht verfügbar (Mining gerade gestartet?)")
        print()
        
        # Hole initiale Wetterdaten (Cache füllen für CSV!)
        if self.weather:
            print("🌤️  Hole initiale Wetterdaten...")
            initial_weather = self.weather.get_current_weather()
            if initial_weather:
                self.last_weather_data = initial_weather
                print(f"   ✓ Temperatur: {initial_weather.get('temperature_c', 0):.1f}°C")
                print(f"   ✓ Wolken: {initial_weather.get('cloud_cover_percent', 0):.0f}%")
                print(f"   ✓ Wind: {initial_weather.get('wind_speed_kmh', 0):.1f} km/h")
            else:
                print("   ⚠️  Wetterdaten nicht verfügbar")
            print()
        
        print("�🔄 Starte Monitoring...\n")
        
        iteration = 0
        last_earnings_check = 0
        last_alarm_check = 0  # Separater Timer für Alarm-Checks
        
        try:
            while True:
                iteration += 1
                now = datetime.now().strftime("%H:%M:%S")
                current_time = time.time()
                
                # Prüfe Excavator Health bei JEDER Iteration (alle 2 Minuten)
                # Dies ermöglicht schnelleres Erkennen von Problemen
                self.check_excavator_health()
                
                # Prüfe Inverter Alarme (häufiger als normale Checks!)
                if current_time - last_alarm_check >= ALARM_CHECK_INTERVAL:
                    try:
                        await self.check_inverter_alarms()
                        last_alarm_check = current_time
                    except asyncio.TimeoutError:
                        # Timeout during alarm check - not critical, just skip this check
                        last_alarm_check = current_time  # Update timer to prevent spam
                    except Exception as e:
                        error_logger.warning(f"Alarm check failed: {e}")
                        last_alarm_check = current_time  # Update timer to prevent spam
                
                # Lese Solar-Daten (mit Error Handling für Connection Loss)
                try:
                    solar, house, available = await self.get_available_solar_power()
                except asyncio.TimeoutError:
                    error_logger.error(f"Modbus timeout in main loop - reconnecting")
                    print(f"\n⏱️  Modbus Timeout!")
                    print(f"   💡 HÄUFIGE URSACHEN:")
                    print(f"   → FusionSolar App oder anderes Monitoring-Programm läuft gleichzeitig")
                    print(f"   → Netzwerk-Latenz zum Inverter zu hoch")
                    print(f"   → Inverter ist überlastet (zu viele gleichzeitige Verbindungen)")
                    print(f"   → WLAN-Signal zu schwach (LAN-Kabel empfohlen!)")
                    print(f"   📖 Siehe TROUBLESHOOTING_TIMEOUTS.md für Lösungen")
                    
                    # Bei Connection-Loss: Mining sicherheitshalber stoppen
                    if self.is_mining:
                        print(f"⚠️  Stoppe Mining zur Sicherheit...")
                        self.excavator.stop_mining()
                    
                    # Versuche Reconnect
                    print(f"🔄 Versuche Wiederverbindung zum Inverter...")
                    try:
                        if self.bridge:
                            await self.bridge.stop()
                            self.bridge = None
                    except:
                        pass
                    
                    # Reconnect mit retry logic (ruft connect() auf, die unbegrenzt versucht)
                    await self.connect()
                    print(f"✅ Wiederverbindung erfolgreich! Setze Monitoring fort...\n")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue
                    
                except Exception as e:
                    tb = traceback.format_exc()
                    error_logger.error(f"Error reading solar data in main loop: {e}")
                    error_logger.debug(f"Traceback:\n{tb}")
                    print(f"\n⚠️  Verbindung zum Inverter verloren!")
                    # Print a concise but informative error to console and point to logs for details
                    try:
                        err_repr = repr(e)
                    except Exception:
                        err_repr = str(type(e).__name__)
                    print(f"   Fehler: {type(e).__name__}: {err_repr}")
                    if isinstance(e, TypeError):
                        print("   ℹ️  TypeError erkannt — vollständiger Trace ist im Log.")
                    print(f"   📖 Details im Log: {ERROR_LOG_FILE}")
                    
                    # Bei Connection-Loss: Mining sicherheitshalber stoppen
                    if self.is_mining:
                        print(f"⚠️  Stoppe Mining zur Sicherheit...")
                        self.excavator.stop_mining()
                    
                    # Versuche Reconnect
                    print(f"🔄 Versuche Wiederverbindung zum Inverter...")
                    try:
                        if self.bridge:
                            await self.bridge.stop()
                            self.bridge = None
                    except:
                        pass
                    
                    # Reconnect mit retry logic (ruft connect() auf, die unbegrenzt versucht)
                    await self.connect()
                    print(f"✅ Wiederverbindung erfolgreich! Setze Monitoring fort...\n")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue
                
                # Status Update
                was_mining = self.is_mining
                self.is_mining = self.excavator.is_mining()
                total_hashrate, gpu_hashrates = self.excavator.get_hashrate() if self.is_mining else (0, {})
                
                # Track Mining-Zeit
                if self.is_mining and not was_mining:
                    self.mining_start_time = datetime.now()
                elif not self.is_mining and was_mining and self.mining_start_time:
                    session_time = (datetime.now() - self.mining_start_time).total_seconds()
                    self.total_mining_time += session_time
                    self.mining_start_time = None
                
                # Berechne aktuelle Mining-Session Zeit
                session_time = 0
                if self.is_mining and self.mining_start_time:
                    session_time = (datetime.now() - self.mining_start_time).total_seconds()
                
                # Berechne tatsächlichen Haus-Verbrauch
                actual_house_consumption = solar - house if house > 0 else solar + abs(house)
                
                # GPU Info sammeln - check all configured GPUs
                gpu_usage = 0
                gpu_temp = 0
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        # Collect data from all configured GPUs
                        total_usage = 0
                        total_temp = 0
                        active_gpus = 0
                        for device_id in DEVICE_IDS:
                            gpu_index = int(device_id)
                            if gpu_index < len(gpus):
                                gpu = gpus[gpu_index]
                                total_usage += gpu.load * 100
                                total_temp += gpu.temperature
                                active_gpus += 1
                        # Average across all GPUs
                        if active_gpus > 0:
                            gpu_usage = total_usage / active_gpus
                            gpu_temp = total_temp / active_gpus
                except:
                    pass
                
                # Hole ALLE Inverter-Daten
                inverter_data = await self.get_all_inverter_data()
                
                # Berechne String-Powers (sichere None-Handling)
                pv1_voltage = inverter_data.get('pv_01_voltage') or 0
                pv1_current = inverter_data.get('pv_01_current') or 0
                pv2_voltage = inverter_data.get('pv_02_voltage') or 0
                pv2_current = inverter_data.get('pv_02_current') or 0
                pv1_power = pv1_voltage * pv1_current
                pv2_power = pv2_voltage * pv2_current
                
                # Berechne Grid Phase Powers (sichere None-Handling)
                grid_a_voltage = inverter_data.get('grid_A_voltage') or 0
                grid_a_current = inverter_data.get('grid_A_current') or 0
                grid_b_voltage = inverter_data.get('grid_B_voltage') or 0
                grid_b_current = inverter_data.get('grid_B_current') or 0
                grid_c_voltage = inverter_data.get('grid_C_voltage') or 0
                grid_c_current = inverter_data.get('grid_C_current') or 0
                grid_a_power = grid_a_voltage * grid_a_current
                grid_b_power = grid_b_voltage * grid_b_current
                grid_c_power = grid_c_voltage * grid_c_current
                
                # Hole Wetter-Daten (API-Call nur alle 10 Minuten, aber Cache immer verwenden!)
                if self.weather and iteration % 20 == 0:  # Alle 10 Minuten API-Call
                    new_weather = self.weather.get_current_weather()
                    if new_weather:
                        self.last_weather_data = new_weather  # Update Cache
                
                # Verwende immer die gecachten Wetterdaten (auch zwischen API-Calls!)
                weather_data = self.last_weather_data
                
                # DATA LOGGING - CSV für Auswertungen/ML
                try:
                    with open(DATA_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            # Basis
                            datetime.now().isoformat(),
                            int(datetime.now().timestamp()),
                            # Solar/Grid
                            solar,
                            house,
                            actual_house_consumption,
                            max(0, house),  # Einspeisung (nur positiv)
                            max(0, -house),  # Netzbezug (nur negativ -> positiv)
                            available,
                            # Mining
                            1 if self.is_mining else 0,
                            1 if self.gpu_paused else 0,
                            total_hashrate / 1e6 if total_hashrate > 0 else 0,
                            self.excavator.consecutive_errors,
                            self.start_confirmations,
                            self.stop_confirmations,
                            # GPU
                            gpu_usage,
                            gpu_temp,
                            # String-Daten (PV)
                            pv1_voltage,
                            pv1_current,
                            pv1_power,
                            pv2_voltage,
                            pv2_current,
                            pv2_power,
                            # Grid Details (3 Phasen)
                            grid_a_voltage,
                            grid_b_voltage,
                            grid_c_voltage,
                            grid_a_current,
                            grid_b_current,
                            grid_c_current,
                            grid_a_power,
                            grid_b_power,
                            grid_c_power,
                            # Inverter Status
                            inverter_data.get('internal_temperature') or 0,
                            inverter_data.get('efficiency') or 0,
                            inverter_data.get('daily_yield_energy') or 0,
                            inverter_data.get('accumulated_yield_energy') or 0,
                            # Batterie (optional)
                            inverter_data.get('battery_charge_discharge_power') or 0,
                            inverter_data.get('battery_state_of_capacity') or 0,
                            # Wetter
                            weather_data.get('temperature_c', 0) if weather_data else 0,
                            weather_data.get('cloud_cover_percent', 0) if weather_data else 0,
                            weather_data.get('wind_speed_kmh', 0) if weather_data else 0,
                            weather_data.get('precipitation_mm', 0) if weather_data else 0,
                            weather_data.get('global_radiation_wm2', 0) if weather_data else 0,
                            weather_data.get('direct_radiation_wm2', 0) if weather_data else 0,
                            weather_data.get('diffuse_radiation_wm2', 0) if weather_data else 0,
                            # Inverter Alarms (safe conversion: Liste → int, leere Liste → 0)
                            (inverter_data.get('alarm_1')[0] if (isinstance(inverter_data.get('alarm_1'), list) and len(inverter_data.get('alarm_1', [])) > 0) else (inverter_data.get('alarm_1') if not isinstance(inverter_data.get('alarm_1'), list) else 0)) or 0,
                            (inverter_data.get('alarm_2')[0] if (isinstance(inverter_data.get('alarm_2'), list) and len(inverter_data.get('alarm_2', [])) > 0) else (inverter_data.get('alarm_2') if not isinstance(inverter_data.get('alarm_2'), list) else 0)) or 0,
                            (inverter_data.get('alarm_3')[0] if (isinstance(inverter_data.get('alarm_3'), list) and len(inverter_data.get('alarm_3', [])) > 0) else (inverter_data.get('alarm_3') if not isinstance(inverter_data.get('alarm_3'), list) else 0)) or 0,
                            inverter_data.get('device_status') or 0
                        ])
                except Exception as e:
                    error_logger.error(f"Data logging Fehler: {e}")
                    error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
                
                print(f"[{iteration:3d}] {now}")
                print(f"      ☀️  {t('solar_production')}:       {solar:>6.0f} W")
                if house > 0:
                    print(f"      🏠 {t('consumption')}:   {actual_house_consumption:>6.0f} W {t('house_consumption')}")
                    print(f"      📤 {t('grid_export')}: {house:>6.0f} W {t('to_grid')}")
                else:
                    print(f"      🏠 {t('consumption')}:   {actual_house_consumption:>6.0f} W {t('house_consumption')}")
                    print(f"      📥 {t('grid_import')}:   {abs(house):>6.0f} W {t('from_grid')}")
                print(f"      ✨ {t('available_power')}:   {available:>6.0f} W {t('for_mining')}")
                
                # Mining Status mit GPU-Anzahl und Hashrate-Validierung
                if self.is_mining:
                    active_count = len(self.active_gpu_ids)
                    target_count = self.calculate_target_gpu_count(available)
                    status_icon = "🟢"
                    
                    # Hashrate-Validierung: Mining sollte aktiv sein, aber prüfe ob Hashrate > 0
                    if total_hashrate == 0 and session_time > 120:  # Nach 2 Minuten sollte Hashrate da sein
                        status_icon = "🔴"
                        print(f"      ⛏️  {t('mining_status')}:      {status_icon} Mining FEHLER ({active_count}/{len(DEVICE_IDS)} GPUs)")
                        print(f"      ⚠️  WARNUNG: Kein Hashrate trotz aktivem Mining!")
                        print(f"      ℹ️  Mögliche Ursachen:")
                        print(f"         • DAG-Generierung läuft noch (warte 5-10 Min)")
                        print(f"         • Algorithmus nicht unterstützt")
                        print(f"         • GPU-Fehler oder Treiberproblem")
                        error_logger.warning(f"Mining active but no hashrate after {session_time:.0f}s - possible issue!")
                    elif active_count < target_count:
                        status_icon = "🟡"  # Könnte mehr GPUs nutzen
                        print(f"      ⛏️  {t('mining_status')}:      {status_icon} Mining ({active_count}/{len(DEVICE_IDS)} GPUs)")
                    else:
                        print(f"      ⛏️  {t('mining_status')}:      {status_icon} Mining ({active_count}/{len(DEVICE_IDS)} GPUs)")
                else:
                    print(f"      ⛏️  {t('mining_status')}:      🔴 {t('mining_stopped')}")
                
                if total_hashrate > 0:
                    print(f"      📈 Total:       {total_hashrate/1e6:.2f} MH/s ✅")
                    # Show per-GPU hashrates if multiple GPUs
                    if len(gpu_hashrates) > 1:
                        gpu_details = ", ".join([f"GPU{gpu_id}: {speed/1e6:.1f}" for gpu_id, speed in sorted(gpu_hashrates.items())])
                        print(f"         └─ {gpu_details} MH/s")
                    elif len(gpu_hashrates) == 1:
                        gpu_id = list(gpu_hashrates.keys())[0]
                        print(f"         └─ GPU{gpu_id}")
                elif self.is_mining:
                    # Mining läuft aber kein Hashrate - zeige Warnung
                    if session_time < 120:
                        print(f"      📈 Total:       0.00 MH/s ⏳ (Initialisierung...)")
                    else:
                        print(f"      📈 Total:       0.00 MH/s ❌ (FEHLER!)")
                
                if session_time > 0:
                    mins = int(session_time / 60)
                    secs = int(session_time % 60)
                    print(f"      ⏱️  Session:     {mins}m {secs}s")
                
                # Earnings alle 10 Minuten updaten
                if iteration % 20 == 0 or (iteration == 1 and earnings is None):
                    earnings = self.nicehash.get_earnings_info()
                    if earnings:
                        print(f"      💰 Unbezahlt:   {self.nicehash.format_btc(earnings['unpaid_btc'])}")
                
                # Wetter-Daten anzeigen (alle 10 Minuten)
                if weather_data:
                    print(f"      🌡️  Wetter:      {weather_data.get('temperature_c', 0):.1f}°C, " +
                          f"☁️ {weather_data.get('cloud_cover_percent', 0):.0f}%, " +
                          f"☀️ {weather_data.get('global_radiation_wm2', 0):.0f} W/m²")
                
                # GPU MONITORING - Prüfe ob andere Software die GPU braucht
                gpu_busy = False
                gpu_usage = 0
                gpu_process = None
                
                if GPU_CHECK_ENABLED and self.is_mining:
                    gpu_busy, gpu_usage, gpu_process = self.gpu_monitor.get_gpu_usage_by_others()
                    
                    if gpu_busy and not self.gpu_paused:
                        # GPU wird von anderem Prozess genutzt - STOPPE Mining für maximale Performance
                        print(f"      🎮 GPU von '{gpu_process}' genutzt ({gpu_usage:.0f}%)")
                        print(f"      ⏸️  STOPPE Mining (Gaming hat Priorität!)...")
                        self.excavator.stop_mining()
                        self.gpu_paused = True
                        self.gpu_monitor.set_mining_active(False)  # GPU Monitor informieren
                        
                    elif not gpu_busy and self.gpu_paused:
                        # GPU wieder frei - Mining fortsetzen wenn genug Power
                        print(f"      ✅ GPU wieder frei ({gpu_usage:.0f}%)")
                        if available >= MIN_POWER_TO_KEEP:
                            print(f"      ▶️  STARTE Mining neu...")
                            success = self.excavator.start_mining(
                                DEVICE_IDS, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                            )
                            if success:
                                self.gpu_paused = False
                                self.gpu_monitor.set_mining_active(True)
                        else:
                            print(f"      ⏸️  Warte auf genug Solar-Power...")
                    
                    elif gpu_busy and self.gpu_paused:
                        # Noch immer gepaused
                        print(f"      🎮 GPU-Pause: {gpu_process} ({gpu_usage:.0f}%)")
                
                # ==============================================================
                # DYNAMISCHE GPU-SKALIERUNGS-LOGIK (nur wenn nicht GPU-gepaused)
                # ==============================================================
                if not self.gpu_paused:
                    target_gpu_count = self.calculate_target_gpu_count(available)
                    current_workers = self.get_active_workers_device_ids()
                    current_count = len(current_workers)
                    
                    # Fall 1: Kein Mining aktiv
                    if not self.is_mining:
                        if target_gpu_count > 0:
                            # Genug Power für mindestens 1 GPU
                            if self.start_confirmations < START_CONFIRMATIONS_NEEDED:
                                self.start_confirmations += 1
                            self.stop_confirmations = 0
                            print(f"      ➕ Power für {target_gpu_count} GPU(s)! {self.start_confirmations}/{START_CONFIRMATIONS_NEEDED}")
                            
                            if self.start_confirmations >= START_CONFIRMATIONS_NEEDED:
                                # Starte nur die Anzahl GPUs die wir mit Power versorgen können
                                gpus_to_start = DEVICE_IDS[:target_gpu_count]
                                print(f"\n      🚀 STARTE MINING MIT {target_gpu_count} GPU(s)!\n")
                                success = self.excavator.start_mining(
                                    gpus_to_start, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                                )
                                if success:
                                    self.is_mining = True
                                    self.gpu_monitor.set_mining_active(True)
                                    self.start_confirmations = 0
                                    self.mining_start_time = datetime.now()
                                    self.mining_start_failures = 0
                                    self.last_mining_attempt = time.time()
                                    self.active_gpu_ids = self.get_active_workers_device_ids()
                                    print(f"      ✅ Mining gestartet mit GPUs: {', '.join(self.active_gpu_ids)}")
                                else:
                                    print("      ⚠️  Start fehlgeschlagen!")
                                    self.mining_start_failures += 1
                                    error_logger.warning(f"Mining start failed - attempt {self.mining_start_failures}")
                        else:
                            # Nicht genug Power für auch nur 1 GPU
                            self.start_confirmations = 0
                            self.mining_start_failures = 0
                            print(f"      ⏸️  Zu wenig Power (brauche {MIN_POWER_TO_START}W für 1 GPU)")
                    
                    # Fall 2: Mining läuft bereits
                    else:
                        # Prüfe ob wir GPUs hinzufügen oder entfernen müssen
                        if target_gpu_count != current_count:
                            changed, new_count = await self.scale_gpus(available)
                            if changed:
                                self.active_gpu_ids = self.get_active_workers_device_ids()
                                print(f"      ℹ️  Aktive GPUs: {', '.join(self.active_gpu_ids)}")
                                # Reset confirmations nach Änderung
                                self.start_confirmations = 0
                                self.stop_confirmations = 0
                        
                        # Prüfe ob wir komplett stoppen müssen (weniger als MIN_POWER_TO_KEEP)
                        if available < MIN_POWER_TO_KEEP:
                            if self.stop_confirmations < STOP_CONFIRMATIONS_NEEDED:
                                self.stop_confirmations += 1
                            self.start_confirmations = 0
                            print(f"      ⚠️  Zu wenig Power! {self.stop_confirmations}/{STOP_CONFIRMATIONS_NEEDED}")
                            
                            if self.stop_confirmations >= STOP_CONFIRMATIONS_NEEDED:
                                print(f"\n      🛑 STOPPE ALLE GPUs!\n")
                                success = self.excavator.stop_mining()
                                if success:
                                    self.is_mining = False
                                    self.gpu_monitor.set_mining_active(False)
                                    self.stop_confirmations = 0
                                    self.active_gpu_ids = []
                                    # Speichere Mining-Zeit
                                    if self.mining_start_time:
                                        session_time = (datetime.now() - self.mining_start_time).total_seconds()
                                        self.total_mining_time += session_time
                                        self.mining_start_time = None
                        else:
                            # Genug Power vorhanden
                            self.stop_confirmations = 0
                
                # ==============================================================
                # ENDE DYNAMISCHE GPU-SKALIERUNG
                # ==============================================================
                
                # GPU Health Check - detect and fix stuck GPUs with 0 hashrate
                if self.is_mining and iteration % 4 == 0:  # Check every 2 minutes (4 * 30s)
                    await self.check_and_fix_stuck_gpus()
                
                print("-" * 80)
                await asyncio.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Beende Controller...")
            
            # Finale Statistik
            if self.mining_start_time:
                session_time = (datetime.now() - self.mining_start_time).total_seconds()
                self.total_mining_time += session_time
            
            if self.total_mining_time > 0:
                hours = int(self.total_mining_time / 3600)
                mins = int((self.total_mining_time % 3600) / 60)
                print(f"\n📊 Gesamt gemined: {hours}h {mins}m")
                
                # Finale Earnings
                earnings = self.nicehash.get_earnings_info()
                if earnings:
                    print(f"💰 Unbezahlt: {self.nicehash.format_btc(earnings['unpaid_btc'])}")
            
            if self.is_mining:
                choice = input("\nMining stoppen? (j/n): ").strip().lower()
                if choice == 'j':
                    self.excavator.stop_mining()
            
            # Excavator beenden?
            if self.excavator_process:
                choice = input("Excavator beenden? (j/n): ").strip().lower()
                if choice == 'j':
                    print("🛑 Beende Excavator...")
                    try:
                        self.excavator.send_command("quit")
                        self.excavator_process.wait(timeout=5)
                    except:
                        self.excavator_process.terminate()
                    print("✅ Excavator beendet")
            
            if self.bridge:
                await self.bridge.stop()
            
            print("✅ Controller beendet")


async def main():
    # ============================================================================
    # AUTO-UPDATE CHECKS
    # ============================================================================
    print("=" * 80)
    print("🔄 AUTO-UPDATE CHECK")
    print("=" * 80)
    
    # Check for huawei-solar package updates
    check_and_update_huawei_solar()
    
    # Check for Excavator updates
    check_and_update_excavator(EXCAVATOR_PATH)
    
    print("=" * 80)
    print()
    
    # Prüfe Konfiguration
    if "YOUR_WALLET_ADDRESS" in NICEHASH_WALLET:
        print("=" * 80)
        print("⚠️  KONFIGURATION ERFORDERLICH!")
        print("=" * 80)
        print()
        print("Bitte bearbeite die Datei und setze:")
        print(f"  NICEHASH_WALLET = 'deine_wallet_adresse.worker_name'")
        print()
        print("Beispiel:")
        print("  NICEHASH_WALLET = '34HKWdzLxWBduUfJE9JxaFhoXnfC6gmePG.solar_rig'")
        print()
        print("=" * 80)
        return
    
    controller = SolarMiningController()
    
    try:
        await controller.connect()
        print()
        await controller.run()
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if controller.bridge:
            await controller.bridge.stop()


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "🌞 SOLAR MINING AUTOMATION v2.0 🌞" + " " * 23 + "║")
    print("║" + " " * 25 + "(Excavator API)" + " " * 39 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    asyncio.run(main())
