"""
Solar Mining Controller mit GPU-Monitoring
===========================================
Automatisches Crypto-Mining basierend auf verfügbarer Solar-Energie.

Features:
- Startet/stoppt Mining basierend auf Solar-Überschuss
- Pausiert automatisch wenn andere Software die GPU braucht (Gaming, Stable Diffusion, etc.)
- Excavator API Control (schnelle Start/Stop-Zeiten)
- NiceHash Earnings Tracking
- Auto-Start von Excavator

GPU Monitoring:
- Erkennt wenn andere Prozesse die GPU nutzen (>10% Last)
- Pausiert Mining automatisch für Rocket League, Stable Diffusion, etc.
- Setzt Mining fort wenn GPU wieder frei ist
- GPU_CHECK_ENABLED = True/False um Feature ein/auszuschalten
"""

import asyncio
import json
import subprocess
import os
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

# Lade .env Datei
load_dotenv()

# KONFIGURATION (aus .env)
EXCAVATOR_PATH = os.getenv("EXCAVATOR_PATH", r"H:\miner\excavator.exe")
EXCAVATOR_API_HOST = os.getenv("EXCAVATOR_API_HOST", "127.0.0.1")
EXCAVATOR_API_PORT = int(os.getenv("EXCAVATOR_API_PORT", "3456"))
INVERTER_HOST = os.getenv("INVERTER_HOST", "192.168.18.206")
INVERTER_PORT = int(os.getenv("INVERTER_PORT", "6607"))

# GPU Einstellungen
DEVICE_ID = os.getenv("DEVICE_ID", "0")
ALGORITHM = os.getenv("ALGORITHM", "daggerhashimoto")
STRATUM_URL = os.getenv("STRATUM_URL", "nhmp-ssl.eu.nicehash.com:443")
NICEHASH_WALLET = os.getenv("NICEHASH_WALLET", "YOUR_WALLET_ADDRESS.worker_name")

# NiceHash API (für Earnings)
NICEHASH_API_URL = "https://api2.nicehash.com/main/api/v2/mining/external"

# Wetter API (Open-Meteo - kostenlos, kein API-Key nötig)
WEATHER_ENABLED = os.getenv("WEATHER_ENABLED", "True").lower() == "true"
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "37.6931"))  # Los Nietos, Spanien
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "-0.8481"))
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Power Schwellwerte
MIN_POWER_TO_START = int(os.getenv("MIN_POWER_TO_START", "200"))
MIN_POWER_TO_KEEP = int(os.getenv("MIN_POWER_TO_KEEP", "150"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
ALARM_CHECK_INTERVAL = int(os.getenv("ALARM_CHECK_INTERVAL", "5"))

# Hysterese
START_CONFIRMATIONS_NEEDED = int(os.getenv("START_CONFIRMATIONS_NEEDED", "3"))
STOP_CONFIRMATIONS_NEEDED = int(os.getenv("STOP_CONFIRMATIONS_NEEDED", "5"))

# GPU Nutzungs-Monitoring
GPU_USAGE_THRESHOLD = int(os.getenv("GPU_USAGE_THRESHOLD", "10"))
GPU_CHECK_ENABLED = os.getenv("GPU_CHECK_ENABLED", "True").lower() == "true"

# LOGGING KONFIGURATION
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG_FILE = LOG_DIR / "errors.log"
DATA_LOG_FILE = LOG_DIR / "solar_data.csv"

# Setup Error Logger
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.DEBUG)
error_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
error_handler.setLevel(logging.DEBUG)
error_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
error_handler.setFormatter(error_formatter)
error_logger.addHandler(error_handler)

# Data Logger Setup
def init_data_log():
    """Initialisiert CSV-Datei für Datenlogging falls nicht existiert."""
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


class WeatherAPI:
    """Open-Meteo Weather API - kostenlos, kein API-Key."""
    
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude
        self.api_url = WEATHER_API_URL
        self.last_data = None
        self.last_fetch = None
        
    def get_current_weather(self):
        """
        Holt aktuelles Wetter inkl. Solar-Radiation.
        Cache: 10 Minuten (API ist nur alle 15min aktuell).
        """
        # Cache prüfen (10 Minuten)
        if self.last_data and self.last_fetch:
            age = (datetime.now() - self.last_fetch).total_seconds()
            if age < 600:  # 10 Minuten
                return self.last_data
        
        try:
            params = {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'current': [
                    'temperature_2m',
                    'cloud_cover',
                    'wind_speed_10m',
                    'precipitation',
                ],
                'hourly': [
                    'global_tilted_irradiance',
                    'direct_radiation',
                    'diffuse_radiation'
                ],
                'timezone': 'auto',
                'forecast_days': 1
            }
            
            response = requests.get(self.api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Aktuelle Wetterdaten
                current = data.get('current', {})
                
                # Solar Radiation (aktuellste Stunde)
                hourly = data.get('hourly', {})
                current_hour_index = 0  # Erste Stunde ist aktuelle
                
                result = {
                    'temperature_c': current.get('temperature_2m', 0),
                    'cloud_cover_percent': current.get('cloud_cover', 0),
                    'wind_speed_kmh': current.get('wind_speed_10m', 0),
                    'precipitation_mm': current.get('precipitation', 0),
                    'global_radiation_wm2': hourly.get('global_tilted_irradiance', [0])[current_hour_index],
                    'direct_radiation_wm2': hourly.get('direct_radiation', [0])[current_hour_index],
                    'diffuse_radiation_wm2': hourly.get('diffuse_radiation', [0])[current_hour_index],
                }
                
                self.last_data = result
                self.last_fetch = datetime.now()
                return result
            else:
                error_logger.warning(f"Weather API HTTP {response.status_code}")
                return None
                
        except Exception as e:
            error_logger.error(f"Weather API Fehler: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return None


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
                    
                    # Spezialfall: python.exe - prüfe ob es NICHT unser Script ist
                    if 'python' in proc_name.lower() and total_gpu_load > 30:
                        # Prüfe Kommandozeile für Stable Diffusion Hinweise
                        try:
                            cmdline = ' '.join(proc.cmdline())
                            sd_keywords = ['stable-diffusion', 'comfy', 'automatic1111', 'invoke', 'diffusers', 'torch']
                            if any(kw in cmdline.lower() for kw in sd_keywords):
                                return True, total_gpu_load, f"Python (Stable Diffusion)"
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # WICHTIG: Wenn Mining aktiv ist, ist hohe GPU-Last NORMAL
            # Pausiere nur bei >80% UND Mining ist NICHT aktiv
            # Das vermeidet false positives vom Miner selbst
            if not self.mining_active and total_gpu_load > 80:
                return True, total_gpu_load, "Unknown GPU-intensive Process"
            
            return False, total_gpu_load, None
            
        except Exception as e:
            error_logger.error(f"GPU Monitoring Fehler: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"GPU ID: {self.gpu_id}, Threshold: {self.threshold}, Mining Active: {self.mining_active}")
            print(f"⚠️ GPU Monitoring Fehler: {e}")
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
        
        # Alle Retries fehlgeschlagen
        self.consecutive_errors += 1
        
        # Detailliertes Error-Logging
        error_logger.error(f"Excavator API Fehler ({self.consecutive_errors}x): {last_error}")
        error_logger.debug(f"Method: {method}, Params: {params}, Retries: {retries}")
        error_logger.debug(f"Host: {self.host}, Port: {self.port}, Command ID: {self.cmd_id-1}")
        error_logger.debug(f"Last successful command: {self.last_successful_command}")
        
        # Nur jeden 10. Fehler ausgeben um Spam zu vermeiden
        if self.consecutive_errors == 1 or self.consecutive_errors % 10 == 0:
            print(f"⚠️  API Fehler ({self.consecutive_errors}x): {last_error}")
            if self.consecutive_errors >= 30:
                print(f"⚠️  Excavator antwortet nicht! Prozess neu starten?")
                error_logger.warning(f"Excavator antwortet seit {self.consecutive_errors} Versuchen nicht mehr!")
        
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
        """Startet Mining."""
        try:
            print(f"🔧 Konfiguriere Mining...")
            
            # 1. Subscribe zum Stratum
            result = self.send_command("subscribe", [stratum_url, wallet])
            if result and result.get("error"):
                print(f"❌ Subscribe Fehler: {result['error']}")
                return False
            print(f"   ✓ Subscribe erfolgreich")
            
            # 2. Algorithm hinzufügen
            result = self.send_command("algorithm.add", [algorithm])
            if result and result.get("error"):
                print(f"❌ Algorithm Fehler: {result['error']}")
                return False
            print(f"   ✓ Algorithm '{algorithm}' hinzugefügt")
            
            # 3. Worker hinzufügen (GPU mining starten)
            result = self.send_command("worker.add", [algorithm, device_id])
            if result and result.get("error"):
                print(f"❌ Worker Fehler: {result['error']}")
                return False
            
            worker_id = result.get("worker_id", 0)
            print(f"   ✓ Worker {worker_id} gestartet")
            
            return True
            
        except Exception as e:
            print(f"❌ Start-Fehler: {e}")
            return False
    
    def stop_mining(self):
        """Stoppt Mining."""
        try:
            print(f"🔧 Stoppe Mining...")
            
            # 1. Alle Worker entfernen
            result = self.send_command("worker.clear")
            if result and result.get("error"):
                print(f"⚠️  Worker clear Fehler: {result['error']}")
            else:
                print(f"   ✓ Alle Worker gestoppt")
            
            # 2. Alle Algorithmen entfernen
            result = self.send_command("algorithm.clear")
            if result and result.get("error"):
                print(f"⚠️  Algorithm clear Fehler: {result['error']}")
            else:
                print(f"   ✓ Algorithms entfernt")
            
            # 3. Von Stratum trennen
            result = self.send_command("unsubscribe")
            if result and result.get("error"):
                print(f"⚠️  Unsubscribe Fehler: {result['error']}")
            else:
                print(f"   ✓ Von Stratum getrennt")
            
            return True
            
        except Exception as e:
            print(f"❌ Stop-Fehler: {e}")
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
    
    def start_excavator(self):
        """Startet Excavator falls nicht bereits laufend."""
        # Prüfe ob Excavator schon läuft
        info = self.excavator.get_info()
        if info:
            print(f"ℹ️  Excavator läuft bereits (Version {info.get('version', 'unknown')})")
            return True
        
        # Prüfe ob excavator.exe existiert
        if not os.path.exists(EXCAVATOR_PATH):
            print(f"❌ Excavator nicht gefunden: {EXCAVATOR_PATH}")
            print(f"   Bitte EXCAVATOR_PATH in der Konfiguration anpassen!")
            return False
        
        try:
            print(f"🚀 Starte Excavator: {EXCAVATOR_PATH}")
            print(f"   API Port: {EXCAVATOR_API_PORT}")
            
            # Starte Excavator im Hintergrund
            self.excavator_process = subprocess.Popen(
                [EXCAVATOR_PATH, "-p", str(EXCAVATOR_API_PORT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE  # Eigenes Fenster
            )
            
            # Warte bis API verfügbar ist
            print("   Warte auf API...")
            for i in range(30):  # Max 30 Sekunden warten
                time.sleep(1)
                info = self.excavator.get_info()
                if info:
                    print(f"✅ Excavator gestartet! Version: {info.get('version', 'unknown')}")
                    # Speichere PID für GPU Monitoring
                    self.gpu_monitor.set_excavator_pid(self.excavator_process.pid)
                    print(f"   PID: {self.excavator_process.pid}")
                    return True
                if i % 5 == 0 and i > 0:
                    print(f"   Noch {30-i}s...")
            
            print("❌ Excavator API nicht erreichbar nach 30s")
            error_logger.error("Excavator API nicht erreichbar nach 30s")
            error_logger.debug(f"Excavator Path: {EXCAVATOR_PATH}")
            error_logger.debug(f"API Host: {self.excavator.host}, Port: {self.excavator.port}")
            error_logger.debug(f"Process PID: {self.excavator_process.pid if self.excavator_process else 'None'}")
            return False
            
        except Exception as e:
            print(f"❌ Fehler beim Starten von Excavator: {e}")
            error_logger.error(f"Fehler beim Starten von Excavator: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Excavator Path exists: {os.path.exists(EXCAVATOR_PATH)}")
            return False
    
    def check_excavator_health(self):
        """Prüft ob Excavator noch antwortet und startet neu falls nötig."""
        # Prüfe ob API antwortet
        info = self.excavator.get_info()
        
        if info:
            # Alles OK
            return True
        
        # API antwortet nicht - prüfe ob Prozess noch läuft
        if self.excavator_process and self.excavator_process.poll() is None:
            # Prozess läuft noch, aber API antwortet nicht
            if self.excavator.consecutive_errors >= 30:
                print("\n⚠️  Excavator Prozess läuft, aber API antwortet nicht!")
                print("   Beende alten Prozess und starte neu...")
                error_logger.warning("Excavator Prozess läuft, aber API antwortet nicht - Neustart")
                error_logger.debug(f"PID: {self.excavator_process.pid}, Consecutive Errors: {self.excavator.consecutive_errors}")
                try:
                    self.excavator_process.terminate()
                    self.excavator_process.wait(timeout=5)
                except Exception as e:
                    error_logger.error(f"Fehler beim Beenden von Excavator: {e}")
                    self.excavator_process.kill()
                
                self.excavator_process = None
                self.excavator.consecutive_errors = 0
                return self.start_excavator()
        else:
            # Prozess ist abgestürzt
            if self.excavator.consecutive_errors >= 10:
                print("\n⚠️  Excavator Prozess ist abgestürzt!")
                print("   Starte Excavator neu...")
                error_logger.error("Excavator Prozess ist abgestürzt - Neustart")
                error_logger.debug(f"Consecutive Errors: {self.excavator.consecutive_errors}")
                self.excavator_process = None
                self.excavator.consecutive_errors = 0
                return self.start_excavator()
        
        return False
        
    async def connect(self):
        """Verbinde mit Inverter."""
        try:
            print(f"🔌 Verbinde mit Inverter {INVERTER_HOST}:{INVERTER_PORT}...")
            self.bridge = await HuaweiSolarBridge.create(INVERTER_HOST, port=INVERTER_PORT)
            print("✅ Inverter verbunden!")
        except Exception as e:
            error_logger.error(f"Fehler beim Verbinden mit Inverter: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Host: {INVERTER_HOST}, Port: {INVERTER_PORT}")
            raise
        
        # Starte Excavator falls nötig
        print(f"\n🔌 Prüfe Excavator API auf {EXCAVATOR_API_HOST}:{EXCAVATOR_API_PORT}...")
        if not self.start_excavator():
            raise Exception("Excavator konnte nicht gestartet werden!")
    
    async def get_available_solar_power(self):
        """Lese verfügbare Solarleistung."""
        try:
            solar_power = await self.bridge.client.get("input_power")
            house_power = await self.bridge.client.get("power_meter_active_power")
            
            # Verfügbare Power = Einspeisung (nur das was übrig ist!)
            # house_power > 0: Einspeisung ins Netz (verfügbar für Mining)
            # house_power < 0: Netzbezug (nichts verfügbar, ziehen schon aus Netz)
            available = max(0, house_power.value)  # Nur positive Einspeisung zählt
            
            return solar_power.value, house_power.value, available
        except Exception as e:
            error_logger.error(f"Fehler beim Lesen von Solar-Daten: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            error_logger.debug(f"Bridge connected: {self.bridge is not None}")
            print(f"❌ Fehler beim Lesen: {e}")
            return 0, 0, 0
    
    async def get_all_inverter_data(self):
        """Liest ALLE verfügbaren Inverter-Daten aus."""
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
                
                # Konvertiere Listen zu int (erstes Element; bei leerer Liste = 0)
                data['alarm_1'] = alarm_1_raw[0] if (isinstance(alarm_1_raw, list) and len(alarm_1_raw) > 0) else (alarm_1_raw if not isinstance(alarm_1_raw, list) else 0)
                data['alarm_2'] = alarm_2_raw[0] if (isinstance(alarm_2_raw, list) and len(alarm_2_raw) > 0) else (alarm_2_raw if not isinstance(alarm_2_raw, list) else 0)
                data['alarm_3'] = alarm_3_raw[0] if (isinstance(alarm_3_raw, list) and len(alarm_3_raw) > 0) else (alarm_3_raw if not isinstance(alarm_3_raw, list) else 0)
                data['device_status'] = (await self.bridge.client.get("device_status")).value
            except:
                pass
                
        except Exception as e:
            error_logger.error(f"Fehler beim Lesen von erweiterten Inverter-Daten: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
        
        return data
    
    async def check_inverter_alarms(self):
        """Prüft Inverter auf aktive Alarme und loggt sie."""
        try:
            alarm_1 = await self.bridge.client.get("alarm_1")
            alarm_2 = await self.bridge.client.get("alarm_2")
            alarm_3 = await self.bridge.client.get("alarm_3")
            device_status = await self.bridge.client.get("device_status")
            
            # Konvertiere zu int (falls Liste, nehme erstes Element; bei leerer Liste = 0)
            alarm_1_val = alarm_1.value[0] if (isinstance(alarm_1.value, list) and len(alarm_1.value) > 0) else (alarm_1.value if not isinstance(alarm_1.value, list) else 0)
            alarm_2_val = alarm_2.value[0] if (isinstance(alarm_2.value, list) and len(alarm_2.value) > 0) else (alarm_2.value if not isinstance(alarm_2.value, list) else 0)
            alarm_3_val = alarm_3.value[0] if (isinstance(alarm_3.value, list) and len(alarm_3.value) > 0) else (alarm_3.value if not isinstance(alarm_3.value, list) else 0)
            
            # Prüfe ob Alarme aktiv sind (Bitfeld)
            has_alarms = (alarm_1_val != 0 or alarm_2_val != 0 or alarm_3_val != 0)
            
            if has_alarms:
                print(f"\n⚠️  INVERTER ALARM ERKANNT!")
                error_logger.warning(f"Inverter Alarm: Alarm1={alarm_1_val}, Alarm2={alarm_2_val}, Alarm3={alarm_3_val}")
                error_logger.warning(f"Device Status: {device_status.value}")
                print(f"   Alarm 1: {alarm_1_val:016b} (0x{alarm_1_val:04X})")
                print(f"   Alarm 2: {alarm_2_val:016b} (0x{alarm_2_val:04X})")
                print(f"   Alarm 3: {alarm_3_val:016b} (0x{alarm_3_val:04X})")
                print(f"   Status: {device_status.value}\n")
                
                # Bekannte Alarm-Bits (Beispiele - Huawei Dokumentation prüfen)
                alarm_bits = {
                    0: "Grid Overvoltage",
                    1: "Grid Undervoltage", 
                    2: "Grid Overfrequency",
                    3: "Grid Underfrequency",
                    4: "PV Overvoltage",
                    5: "PV Undervoltage",
                    8: "Isolation Fault",
                    9: "Temperature Too High",
                    10: "Fan Fault",
                    # Weitere Bits je nach Modell
                }
                
                # Parse Alarm 1 Bits
                for bit, description in alarm_bits.items():
                    if alarm_1_val & (1 << bit):
                        print(f"   ⚠️  {description}")
                        error_logger.error(f"Inverter Alarm: {description}")
                
                return True
            
            return False
            
        except Exception as e:
            error_logger.error(f"Fehler beim Prüfen von Inverter-Alarmen: {e}")
            error_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return False
    
    async def run(self):
        """Hauptschleife."""
        print("=" * 80)
        print("⚡ SOLAR MINING CONTROLLER (Excavator API)")
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
        print("� Hole NiceHash Earnings...")
        earnings = self.nicehash.get_earnings_info()
        if earnings:
            print(f"   Unbezahlt: {self.nicehash.format_btc(earnings['unpaid_btc'])}")
            print(f"   Gesamt bezahlt: {self.nicehash.format_btc(earnings['total_paid_btc'])}")
        else:
            print("   ⚠️  Earnings noch nicht verfügbar (Mining gerade gestartet?)")
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
                
                # Prüfe Excavator Health (alle 10 Iterationen)
                if iteration % 10 == 0:
                    self.check_excavator_health()
                
                # Prüfe Inverter Alarme (häufiger als normale Checks!)
                if current_time - last_alarm_check >= ALARM_CHECK_INTERVAL:
                    await self.check_inverter_alarms()
                    last_alarm_check = current_time
                
                # Lese Solar-Daten
                solar, house, available = await self.get_available_solar_power()
                
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
                
                # Hole Wetter-Daten (nur alle 10 Minuten)
                weather_data = {}
                if self.weather and iteration % 20 == 0:  # Alle 10 Minuten
                    weather_data = self.weather.get_current_weather() or {}
                
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
                print(f"      ☀️  Solar:       {solar:>6.0f} W")
                if house > 0:
                    print(f"      🏠 Verbrauch:   {actual_house_consumption:>6.0f} W (Haus)")
                    print(f"      📤 Einspeisung: {house:>6.0f} W (ins Netz)")
                else:
                    print(f"      🏠 Verbrauch:   {actual_house_consumption:>6.0f} W (Haus)")
                    print(f"      📥 Netzbezug:   {abs(house):>6.0f} W (aus Netz)")
                print(f"      ✨ Verfügbar:   {available:>6.0f} W (für Mining)")
                print(f"      ⛏️  Mining:      {'🟢 AKTIV' if self.is_mining else '🔴 GESTOPPT'}")
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
                        # GPU wird von anderem Prozess genutzt - Mining pausieren
                        print(f"      🎮 GPU von '{gpu_process}' genutzt ({gpu_usage:.0f}%)")
                        print(f"      ⏸️  PAUSIERE Mining für andere Software...")
                        self.excavator.stop_mining()
                        self.gpu_paused = True
                        self.gpu_monitor.set_mining_active(False)  # GPU Monitor informieren
                        # is_mining bleibt True, nur gepaused
                        
                    elif not gpu_busy and self.gpu_paused:
                        # GPU wieder frei - Mining fortsetzen wenn genug Power
                        print(f"      ✅ GPU wieder frei ({gpu_usage:.0f}%)")
                        if available >= MIN_POWER_TO_KEEP:
                            print(f"      ▶️  SETZE Mining fort...")
                            success = self.excavator.start_mining(
                                DEVICE_ID, ALGORITHM, STRATUM_URL, NICEHASH_WALLET
                            )
                            if success:
                                self.gpu_paused = False
                                self.gpu_monitor.set_mining_active(True)  # GPU Monitor informieren
                        else:
                            print(f"      ⏸️  Warte auf genug Solar-Power...")
                    
                    elif gpu_busy and self.gpu_paused:
                        # Noch immer gepaused
                        print(f"      🎮 GPU-Pause: {gpu_process} ({gpu_usage:.0f}%)")
                
                # ENTSCHEIDUNGSLOGIK (nur wenn nicht GPU-gepaused)
                if not self.is_mining:
                    if available >= MIN_POWER_TO_START:
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
                            else:
                                print("      ⚠️  Start fehlgeschlagen, versuche später erneut")
                    else:
                        self.start_confirmations = 0
                        print(f"      ⏸️  Zu wenig Power (brauche {MIN_POWER_TO_START}W)")
                
                else:
                    # Mining läuft - prüfe ob genug Power (aber nur wenn nicht GPU-gepaused)
                    if not self.gpu_paused:
                        if available < MIN_POWER_TO_KEEP:
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
