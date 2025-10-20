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
from huawei_solar import HuaweiSolarBridge
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
EXCAVATOR_PATH = os.getenv("EXCAVATOR_PATH", r"H:\miner\excavator.exe")
EXCAVATOR_API_HOST = os.getenv("EXCAVATOR_API_HOST", "127.0.0.1")
EXCAVATOR_API_PORT = int(os.getenv("EXCAVATOR_API_PORT", "3456"))
INVERTER_HOST = os.getenv("INVERTER_HOST", "192.168.18.206")
INVERTER_PORT = int(os.getenv("INVERTER_PORT", "6607"))

# GPU settings
DEVICE_ID = os.getenv("DEVICE_ID", "0")
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

# LOGGING CONFIGURATION
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG_FILE = LOG_DIR / "errors.log"
DATA_LOG_FILE = LOG_DIR / "solar_data.csv"

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
        
        # Compare versions
        try:
            if version.parse(current_version) >= version.parse(latest_version):
                print(f"   ✅ Excavator ist aktuell")
                return True
        except Exception as e:
            error_logger.debug(f"Version comparison failed: {e}, will update")
        
        # Check if Excavator is running before attempting update
        excavator_running = False
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info['name'] and 'excavator' in proc.info['name'].lower():
                    excavator_running = True
                    break
        except:
            pass
        
        if excavator_running:
            print(f"   ⚠️  Excavator läuft bereits - Update wird übersprungen")
            print(f"   💡 TIPP: Beende Excavator und starte Script neu für Update")
            error_logger.warning(f"Excavator update skipped - process is running (version {current_version} -> {latest_version} available)")
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
        
        # Check latest version on PyPI
        try:
            response = requests.get('https://pypi.org/pypi/huawei-solar/json', timeout=10)
            if response.status_code == 200:
                pypi_data = response.json()
                latest_version = pypi_data['info']['version']
                print(f"   Verfügbar:   {latest_version}")
            else:
                print(f"   ⚠️  PyPI nicht erreichbar (Status {response.status_code})")
                return True
        except Exception as e:
            print(f"   ⚠️  Konnte PyPI nicht abfragen: {e}")
            error_logger.warning(f"PyPI query failed: {e}")
            return True
        
        # Compare versions
        try:
            if version.parse(current_version) >= version.parse(latest_version):
                print(f"   ✅ huawei-solar ist aktuell")
                return True
        except Exception as e:
            error_logger.debug(f"Version comparison failed: {e}, will update")
        
        # Update needed
        print(f"\n📥 Aktualisiere huawei-solar auf {latest_version}...")
        
        # Run pip upgrade using sys.executable (correct Python interpreter)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'huawei-solar'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print(f"   ✅ huawei-solar erfolgreich aktualisiert!")
            error_logger.info(f"huawei-solar updated to version {latest_version}")
            
            # Verify new version (need to reload pkg_resources cache)
            try:
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


class ExcavatorAPI:
    """API Wrapper für Excavator Miner."""
    
    def __init__(self, host="127.0.0.1", port=3456):
        self.host = host
        self.port = port
        self.cmd_id = 1
        self.consecutive_errors = 0
        self.last_successful_command = None
        
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
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)  # Erhöht von 5 auf 10 Sekunden
                sock.connect((self.host, self.port))
                
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
    
    def start_mining(self, device_id, algorithm, stratum_url, wallet):
        """Start mining (only if not already active)."""
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
            
            # 2. Add algorithm
            result = self.send_command("algorithm.add", [algorithm])
            if result is None:
                print(f"❌ {t('algorithm_no_response')}")
                return False
            if result.get("error"):
                print(f"❌ {t('algorithm_error')}: {result['error']}")
                return False
            print(f"   ✓ {t('algorithm_added', algo=algorithm)}")
            
            # 3. Add worker (start GPU mining)
            result = self.send_command("worker.add", [algorithm, device_id])
            if result is None:
                print(f"❌ {t('worker_no_response')}")
                return False
            if result.get("error"):
                print(f"❌ {t('worker_error')}: {result['error']}")
                return False
            
            worker_id = result.get("worker_id", 0)
            print(f"   ✓ {t('worker_started', id=worker_id)}")
            
            return True
            
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
        """Gibt aktuelle Hashrate zurück."""
        workers = self.get_workers()
        if workers:
            for worker in workers:
                if "algorithms" in worker and worker["algorithms"]:
                    return worker["algorithms"][0].get("speed", 0)
        return 0


class SolarMiningController:
    def __init__(self):
        self.bridge = None
        self.excavator = ExcavatorAPI(EXCAVATOR_API_HOST, EXCAVATOR_API_PORT)
        self.nicehash = NiceHashAPI(NICEHASH_WALLET)
        self.weather = WeatherAPI(WEATHER_LATITUDE, WEATHER_LONGITUDE) if WEATHER_ENABLED else None
        self.gpu_monitor = GPUMonitor(gpu_id=int(DEVICE_ID), threshold=GPU_USAGE_THRESHOLD)
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
    
    def start_excavator(self):
        """Start Excavator if not already running."""
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
                self.bridge = await asyncio.wait_for(
                    HuaweiSolarBridge.create(INVERTER_HOST, port=INVERTER_PORT),
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
        print(f"\n🔌 {t('checking_excavator_api')} {EXCAVATOR_API_HOST}:{EXCAVATOR_API_PORT}...")
        if not self.start_excavator():
            raise Exception(t('excavator_could_not_start'))
    
    async def get_available_solar_power(self):
        """Read available solar power."""
        try:
            solar_power = await self.bridge.client.get("input_power")
            house_power = await self.bridge.client.get("power_meter_active_power")
            
            # Available power = feed-in (only what's left!)
            # house_power > 0: Feed-in to grid (available for mining)
            # house_power < 0: Grid import (nothing available, already drawing from grid)
            available = max(0, house_power.value)  # Only positive feed-in counts
            
            return solar_power.value, house_power.value, available
        except Exception as e:
            error_logger.error(f"Error reading solar data: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Bridge connected: {self.bridge is not None}")
            print(f"❌ {t('reading_error')}: {e}")
            return 0, 0, 0
    
    async def get_all_inverter_data(self):
        """Read ALL available inverter data."""
        data = {}
        try:
            # Basis Solar-Daten
            data['input_power'] = (await self.bridge.client.get("input_power")).value
            data['power_meter_active_power'] = (await self.bridge.client.get("power_meter_active_power")).value
            
            # String-Daten (PV1 & PV2)
            try:
                data['pv_01_voltage'] = (await self.bridge.client.get("pv_01_voltage")).value
                data['pv_01_current'] = (await self.bridge.client.get("pv_01_current")).value
                data['pv_02_voltage'] = (await self.bridge.client.get("pv_02_voltage")).value
                data['pv_02_current'] = (await self.bridge.client.get("pv_02_current")).value
            except:
                pass
            
            # Grid-Daten (Phase 1, 2, 3)
            try:
                data['grid_A_voltage'] = (await self.bridge.client.get("grid_A_voltage")).value
                data['grid_B_voltage'] = (await self.bridge.client.get("grid_B_voltage")).value
                data['grid_C_voltage'] = (await self.bridge.client.get("grid_C_voltage")).value
                data['grid_A_current'] = (await self.bridge.client.get("grid_A_current")).value
                data['grid_B_current'] = (await self.bridge.client.get("grid_B_current")).value
                data['grid_C_current'] = (await self.bridge.client.get("grid_C_current")).value
            except:
                pass
            
            # Temperatur & Effizienz
            try:
                data['internal_temperature'] = (await self.bridge.client.get("internal_temperature")).value
                data['efficiency'] = (await self.bridge.client.get("efficiency")).value
            except:
                pass
            
            # Tages-Statistiken
            try:
                data['daily_yield_energy'] = (await self.bridge.client.get("daily_yield_energy")).value
                data['accumulated_yield_energy'] = (await self.bridge.client.get("accumulated_yield_energy")).value
            except:
                pass
            
            # Batterie (falls vorhanden)
            try:
                data['battery_charge_discharge_power'] = (await self.bridge.client.get("storage_charge_discharge_power")).value
                data['battery_state_of_capacity'] = (await self.bridge.client.get("storage_state_of_capacity")).value
            except:
                pass
            
            # Alarms & Status
            try:
                alarm_1_raw = (await self.bridge.client.get("alarm_1")).value
                alarm_2_raw = (await self.bridge.client.get("alarm_2")).value
                alarm_3_raw = (await self.bridge.client.get("alarm_3")).value
                
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
            alarm_1 = await self.bridge.client.get("alarm_1")
            alarm_2 = await self.bridge.client.get("alarm_2")
            alarm_3 = await self.bridge.client.get("alarm_3")
            device_status = await self.bridge.client.get("device_status")
            
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
            
        except Exception as e:
            error_logger.error(f"Fehler beim Prüfen von Inverter-Alarmen: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return False
    
    async def run(self):
        """Main loop."""
        print("=" * 80)
        print(f"⚡ {t('system_title').upper()}")
        print("=" * 80)
        print(f"GPU Device: {DEVICE_ID}")
        print(f"Algorithm: {ALGORITHM}")
        print(f"Wallet: {NICEHASH_WALLET.split('.')[0][:20]}...")
        print(f"Worker: {NICEHASH_WALLET.split('.')[1]}")
        print(f"Start bei: {MIN_POWER_TO_START}W")
        print(f"Stop bei: < {MIN_POWER_TO_KEEP}W")
        print(f"Check-Intervall: {CHECK_INTERVAL}s")
        print(f"Alarm-Check: {ALARM_CHECK_INTERVAL}s")
        print("=" * 80)
        print()
        
        # Initial Status
        self.is_mining = self.excavator.is_mining()
        if self.is_mining:
            print("ℹ️  Mining läuft bereits\n")
            self.mining_start_time = datetime.now()
        else:
            print("ℹ️  Mining läuft nicht\n")
        
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
                    except Exception as e:
                        error_logger.error(f"Error checking inverter alarms: {e}")
                        print(f"⚠️  Alarm-Check fehlgeschlagen (Inverter evtl. offline)")
                
                # Lese Solar-Daten (mit Error Handling für Connection Loss)
                try:
                    solar, house, available = await self.get_available_solar_power()
                except Exception as e:
                    error_logger.error(f"Error reading solar data in main loop: {e}")
                    print(f"\n⚠️  Verbindung zum Inverter verloren!")
                    print(f"   Fehler: {type(e).__name__}")
                    
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
                hashrate = self.excavator.get_hashrate() if self.is_mining else 0
                
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
                
                # GPU Info sammeln
                gpu_usage = 0
                gpu_temp = 0
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus and len(gpus) > int(DEVICE_ID):
                        gpu = gpus[int(DEVICE_ID)]
                        gpu_usage = gpu.load * 100
                        gpu_temp = gpu.temperature
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
                            hashrate / 1e6 if hashrate > 0 else 0,
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
                print(f"      ⛏️  {t('mining_status')}:      {'🟢 ' + t('mining_running') if self.is_mining else '🔴 ' + t('mining_stopped')}")
                if hashrate > 0:
                    print(f"      📈 Hashrate:    {hashrate/1e6:.2f} MH/s")
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
                                DEVICE_ID, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                            )
                            if success:
                                self.gpu_paused = False
                                self.gpu_monitor.set_mining_active(True)
                        else:
                            print(f"      ⏸️  Warte auf genug Solar-Power...")
                    
                    elif gpu_busy and self.gpu_paused:
                        # Noch immer gepaused
                        print(f"      🎮 GPU-Pause: {gpu_process} ({gpu_usage:.0f}%)")
                
                # ENTSCHEIDUNGSLOGIK (nur wenn nicht GPU-gepaused)
                if not self.is_mining:
                    if available >= MIN_POWER_TO_START:
                        # Only increment if we haven't reached the threshold yet
                        if self.start_confirmations < START_CONFIRMATIONS_NEEDED:
                            self.start_confirmations += 1
                        self.stop_confirmations = 0
                        print(f"      ➕ Genug Power! {self.start_confirmations}/{START_CONFIRMATIONS_NEEDED}")
                        
                        if self.start_confirmations >= START_CONFIRMATIONS_NEEDED:
                            print(f"\n      🚀 STARTE MINING!\n")
                            success = self.excavator.start_mining(
                                DEVICE_ID, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                            )
                            if success:
                                self.is_mining = True
                                self.gpu_monitor.set_mining_active(True)  # GPU Monitor informieren
                                self.start_confirmations = 0
                                self.mining_start_time = datetime.now()
                                self.mining_start_failures = 0  # Reset failure counter on success
                                self.last_mining_attempt = time.time()
                            else:
                                # Mining start failed - implement immediate retry logic
                                print("      ⚠️  Start fehlgeschlagen!")
                                self.mining_start_failures += 1
                                error_logger.warning(f"Mining start failed - attempt {self.mining_start_failures}")
                                
                                # Immediate retry if we still have power and haven't exceeded retry limit
                                if self.mining_start_failures <= 3 and available >= MIN_POWER_TO_START:
                                    # Calculate time since last attempt
                                    time_since_last = time.time() - (self.last_mining_attempt or 0)
                                    
                                    # Wait a bit if last attempt was very recent
                                    if time_since_last < self.mining_retry_delay:
                                        wait_time = self.mining_retry_delay - time_since_last
                                        print(f"      ⏳ Warte {wait_time:.0f}s vor erneutem Versuch...")
                                        await asyncio.sleep(wait_time)
                                    
                                    # Verify power still available after wait
                                    solar_retry, house_retry, available_retry = await self.get_available_solar_power()
                                    
                                    if available_retry >= MIN_POWER_TO_START:
                                        print(f"      🔄 Sofortiger Retry {self.mining_start_failures}/3...")
                                        self.last_mining_attempt = time.time()
                                        success_retry = self.excavator.start_mining(
                                            DEVICE_ID, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                                        )
                                        if success_retry:
                                            print(f"      ✅ Retry erfolgreich!")
                                            self.is_mining = True
                                            self.gpu_monitor.set_mining_active(True)
                                            self.start_confirmations = 0
                                            self.mining_start_time = datetime.now()
                                            self.mining_start_failures = 0
                                            self.last_mining_attempt = time.time()
                                        else:
                                            print(f"      ❌ Retry {self.mining_start_failures}/3 fehlgeschlagen")
                                            error_logger.error(f"Mining retry {self.mining_start_failures} failed")
                                            if self.mining_start_failures >= 3:
                                                print(f"      ⚠️  3 Versuche fehlgeschlagen - warte auf nächsten Zyklus")
                                                error_logger.error("Mining retries exhausted - falling back to normal cycle")
                                    else:
                                        print(f"      ⚠️  Nicht genug Power mehr ({available_retry}W) - Retry abgebrochen")
                                else:
                                    if self.mining_start_failures > 3:
                                        print(f"      ⚠️  3 Retries fehlgeschlagen - warte {CHECK_INTERVAL}s")
                                    else:
                                        print(f"      ⚠️  Nicht genug Power für Retry")
                    else:
                        self.start_confirmations = 0
                        self.mining_start_failures = 0  # Reset failures when power insufficient
                        print(f"      ⏸️  Zu wenig Power (brauche {MIN_POWER_TO_START}W)")
                
                else:
                    # Mining läuft - prüfe ob genug Power (aber nur wenn nicht GPU-gepaused)
                    if not self.gpu_paused:
                        if available < MIN_POWER_TO_KEEP:
                            # Only increment if we haven't reached the threshold yet
                            if self.stop_confirmations < STOP_CONFIRMATIONS_NEEDED:
                                self.stop_confirmations += 1
                            self.start_confirmations = 0
                            print(f"      ⚠️  Zu wenig Power! {self.stop_confirmations}/{STOP_CONFIRMATIONS_NEEDED}")
                            
                            if self.stop_confirmations >= STOP_CONFIRMATIONS_NEEDED:
                                print(f"\n      🛑 STOPPE MINING!\n")
                                self.excavator.stop_mining()
                                self.is_mining = False
                                self.gpu_monitor.set_mining_active(False)  # GPU Monitor informieren
                                self.stop_confirmations = 0
                                if self.mining_start_time:
                                    session_time = (datetime.now() - self.mining_start_time).total_seconds()
                                    self.total_mining_time += session_time
                                    self.mining_start_time = None
                        else:
                            self.stop_confirmations = 0
                            print(f"      ✅ Genug Power ({available}W)")
                
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
