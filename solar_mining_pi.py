"""
Solar Monitoring System - Raspberry Pi Edition
==============================================
Monitoring of Huawei Solar Inverter with email notifications.

Features:
- Monitors solar production, grid status, alarms
- Email notifications for alarms and critical errors
- Optional: Daily summary via email
- Weather data integration (Open-Meteo)
- CSV logging for data analysis
- No mining (monitoring only)
"""

import asyncio
import os
import logging
import traceback
import csv
from datetime import datetime, time as dt_time
from pathlib import Path
from dotenv import load_dotenv

# Import shared components
from solar_core import (
    WeatherAPI,
    InverterConnection,
    AlarmParser,
    CSVLogger,
    AlarmDiagnostics,
    EmailNotifier,
    setup_logging as core_setup_logging,
    CSV_COLUMNS_MINIMAL
)

# Import translation system
from translations import t

try:
    from huawei_solar import HuaweiSolarBridge
    HUAWEI_AVAILABLE = True
except ImportError:
    HUAWEI_AVAILABLE = False
    print("⚠️  huawei-solar not installed. Install with: pip install huawei-solar")

# Load .env file
load_dotenv()

# CONFIGURATION
INVERTER_HOST = os.getenv("INVERTER_HOST", "192.168.18.206")
INVERTER_PORT = int(os.getenv("INVERTER_PORT", "6607"))
INVERTER_SLAVE_ID = int(os.getenv("INVERTER_SLAVE_ID", "1"))

# Weather API
WEATHER_ENABLED = os.getenv("WEATHER_ENABLED", "true").lower() == "true"
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "37.6931"))
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "-0.8481"))
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_UPDATE_INTERVAL = int(os.getenv("WEATHER_UPDATE_INTERVAL_SEC", "600"))

# Check intervals
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SEC", "30"))
ALARM_CHECK_INTERVAL = int(os.getenv("ALARM_CHECK_INTERVAL_SEC", "5"))

# Email configuration
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SMTP_USE_TLS = os.getenv("EMAIL_SMTP_USE_TLS", "true").lower() == "true"
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", EMAIL_FROM)
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_SEND_ON_ALARM = os.getenv("EMAIL_SEND_ON_ALARM", "true").lower() == "true"
EMAIL_SEND_ON_CRITICAL_ERROR = os.getenv("EMAIL_SEND_ON_CRITICAL_ERROR", "true").lower() == "true"
EMAIL_SEND_DAILY_SUMMARY = os.getenv("EMAIL_SEND_DAILY_SUMMARY", "false").lower() == "true"
EMAIL_DAILY_SUMMARY_TIME = os.getenv("EMAIL_DAILY_SUMMARY_TIME", "18:00")

# LOGGING
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG_FILE = LOG_DIR / os.getenv("ERROR_LOG_FILENAME", "errors.log")
DATA_LOG_FILE = LOG_DIR / os.getenv("CSV_FILENAME", "solar_data.csv")

# Setup Error Logger
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.DEBUG)
error_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
error_handler.setLevel(logging.DEBUG)
error_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
error_handler.setFormatter(error_formatter)
error_logger.addHandler(error_handler)


# EmailNotifier imported from solar_core, wrapper for Pi-specific logic
class PiEmailNotifier(EmailNotifier):
    """Pi-specific email extension."""
    
    def __init__(self):
        # Create config from .env for solar_core EmailNotifier
        config = {
            'enabled': EMAIL_ENABLED,
            'smtp_server': EMAIL_SMTP_SERVER,
            'smtp_port': EMAIL_SMTP_PORT,
            'use_tls': EMAIL_SMTP_USE_TLS,
            'from': EMAIL_FROM,
            'to': EMAIL_TO,
            'username': EMAIL_USERNAME,
            'password': EMAIL_PASSWORD,
            'send_on_alarm': EMAIL_SEND_ON_ALARM,
            'send_on_error': EMAIL_SEND_ON_CRITICAL_ERROR,
            'send_daily': EMAIL_SEND_DAILY_SUMMARY,
            'daily_time': EMAIL_DAILY_SUMMARY_TIME
        }
        super().__init__(config)
        self.last_daily_summary = None
        
        if self.enabled and not EMAIL_FROM:
            print(f"⚠️  Email enabled but EMAIL_FROM not set!")
            self.enabled = False
    
    # send_email comes from EmailNotifier (solar_core)
    
    def send_alarm_notification(self, alarm_details):
        """Send alarm notification via email."""
        if not EMAIL_SEND_ON_ALARM:
            return
        
        subject = f"⚠️ Inverter Alarm: {alarm_details.get('name', 'Unbekannt')}"
        
        body = f"""
Solar Monitoring - Alarm erkannt!

Alarm: {alarm_details.get('name', 'Unbekannt')}
ID: {alarm_details.get('id', 'N/A')}
Level: {alarm_details.get('level', 'N/A')}
Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Device Status: {alarm_details.get('device_status', 'Unbekannt')}

Grid Status:
{alarm_details.get('grid_details', 'Keine Daten')}

PV Strings:
{alarm_details.get('pv_details', 'Keine Daten')}

Temperaturen:
{alarm_details.get('temp_details', 'Keine Daten')}

Details siehe errors.log
"""
        
        self.send_email(subject, body)
    
    def send_critical_error(self, error_message):
        """Sendet kritische Fehler-Benachrichtigung."""
        if not EMAIL_SEND_ON_CRITICAL_ERROR:
            return
        
        subject = "🚨 Kritischer Fehler"
        body = f"""
Solar Monitoring - Kritischer Fehler aufgetreten!

Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Fehler:
{error_message}

Das System läuft möglicherweise nicht korrekt.
Bitte prüfen!
"""
        
        self.send_email(subject, body)
    
    def send_daily_summary(self, summary_data):
        """Sendet tägliche Zusammenfassung."""
        if not EMAIL_SEND_DAILY_SUMMARY:
            return
        
        subject = f"📊 Tägliche Zusammenfassung - {datetime.now().strftime('%d.%m.%Y')}"
        
        body = f"""
Solar Monitoring - Tägliche Zusammenfassung

Datum: {datetime.now().strftime('%d.%m.%Y')}

Produktion:
  Heute: {summary_data.get('daily_yield', 0):.2f} kWh
  Gesamt: {summary_data.get('total_yield', 0):.2f} kWh

Durchschnitt:
  Solar: {summary_data.get('avg_solar', 0):.0f} W
  Grid: {summary_data.get('avg_grid', 0):.0f} W
  Verbrauch: {summary_data.get('avg_consumption', 0):.0f} W

Wetter:
  Temperatur: {summary_data.get('avg_temp', 0):.1f}°C
  Wolken: {summary_data.get('avg_clouds', 0):.0f}%

Alarme heute: {summary_data.get('alarm_count', 0)}
"""
        
        self.send_email(subject, body)
    
    def check_daily_summary_time(self):
        """Prüft ob Zeit für tägliche Zusammenfassung."""
        if not EMAIL_SEND_DAILY_SUMMARY:
            return False
        
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        
        # Parse Summary Time
        try:
            hour, minute = map(int, EMAIL_DAILY_SUMMARY_TIME.split(':'))
            target_time = dt_time(hour, minute)
        except:
            target_time = dt_time(18, 0)  # Default: 18:00
        
        # Prüfe ob Zeit erreicht und noch nicht heute gesendet
        if now.time() >= target_time and self.last_daily_summary != today_str:
            self.last_daily_summary = today_str
            return True
        
        return False

# WeatherAPI wird aus solar_core importiert (siehe oben)

def init_data_log():
    """Initialisiert CSV-Datei."""
    if not DATA_LOG_FILE.exists():
        with open(DATA_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'unix_timestamp',
                'solar_production_w', 'grid_power_w', 'house_consumption_w',
                'grid_feed_in_w', 'grid_import_w',
                'pv_01_voltage_v', 'pv_01_current_a', 'pv_01_power_w',
                'pv_02_voltage_v', 'pv_02_current_a', 'pv_02_power_w',
                'grid_A_voltage_v', 'grid_B_voltage_v', 'grid_C_voltage_v',
                'internal_temp_c', 'efficiency_percent',
                'daily_yield_kwh', 'total_yield_kwh',
                'battery_power_w', 'battery_soc_percent',
                'weather_temp_c', 'weather_cloud_cover_percent', 'weather_wind_speed_kmh',
                'weather_precipitation_mm', 'weather_global_radiation_wm2',
                'weather_direct_radiation_wm2', 'weather_diffuse_radiation_wm2',
                'inverter_alarm_1', 'inverter_alarm_2', 'inverter_alarm_3',
                'inverter_device_status'
            ])


class SolarMonitor:
    """Raspberry Pi Solar Monitoring System."""
    
    def __init__(self):
        self.bridge = None
        # WeatherAPI aus solar_core verwenden (Los Nietos GPS)
        self.weather = WeatherAPI(
            latitude=37.6931,
            longitude=-0.8481,
            update_interval=600
        ) if WEATHER_ENABLED else None
        # PiEmailNotifier ist die Pi-spezifische Wrapper-Klasse
        self.email = PiEmailNotifier()
        self.last_weather_data = {}
        self.running = True
        
        print("=" * 50)
        print(f"  {t('system_title_pi')}")
        print("=" * 50)
        print(f"Inverter: {INVERTER_HOST}:{INVERTER_PORT}")
        print(f"{t('email_enabled')}: {t('enabled') if EMAIL_ENABLED else t('disabled')}")
        print(f"{t('weather_enabled')}: {t('enabled') if WEATHER_ENABLED else t('disabled')}")
        print("=" * 50)
    
    async def connect_inverter(self):
        """Connect to Huawei inverter."""
        if not HUAWEI_AVAILABLE:
            raise Exception("huawei-solar library not installed!")
        
        try:
            self.bridge = await HuaweiSolarBridge.create(
                host=INVERTER_HOST,
                port=INVERTER_PORT,
                slave_id=INVERTER_SLAVE_ID
            )
            print(f"✓ {t('inverter_connected')}")
            return True
        except Exception as e:
            error_msg = f"{t('connection_error')}: {e}"
            error_logger.error(error_msg)
            print(f"✗ {error_msg}")
            self.email.send_critical_error(error_msg)
            return False
    
    async def check_inverter_alarms(self):
        """Prüft Inverter-Alarme mit vollständigem Kontext."""
        try:
            alarm_1 = await self.bridge.client.get("alarm_1")
            alarm_2 = await self.bridge.client.get("alarm_2")
            alarm_3 = await self.bridge.client.get("alarm_3")
            device_status = await self.bridge.client.get("device_status")
            
            # AlarmParser aus solar_core verwenden
            alarm_1_val, alarm_1_obj = AlarmParser.get_alarm_details(alarm_1)
            alarm_2_val, alarm_2_obj = AlarmParser.get_alarm_details(alarm_2)
            alarm_3_val, alarm_3_obj = AlarmParser.get_alarm_details(alarm_3)
            
            has_alarms = (alarm_1_val != 0 or alarm_2_val != 0 or alarm_3_val != 0 or 
                         alarm_1_obj is not None or alarm_2_obj is not None or alarm_3_obj is not None)
            
            if has_alarms:
                print(f"\n⚠️  {t('alarm_detected').upper()}!")
                
                error_logger.error("=" * 80)
                error_logger.error("🚨 ALARM SNAPSHOT - Complete Inverter Diagnostics")
                error_logger.error("=" * 80)
                
                alarm_details = {
                    'device_status': device_status.value,
                    'grid_details': '',
                    'pv_details': '',
                    'temp_details': ''
                }
                
                # Log alarms
                if alarm_1_obj:
                    error_logger.error(f"Alarm 1: {alarm_1_obj.name} (ID={alarm_1_obj.id}, Level={alarm_1_obj.level})")
                    print(f"   ⚠️  Alarm 1: {alarm_1_obj.name} (Level: {alarm_1_obj.level})")
                    alarm_details['name'] = alarm_1_obj.name
                    alarm_details['id'] = alarm_1_obj.id
                    alarm_details['level'] = alarm_1_obj.level
                
                if alarm_2_obj:
                    error_logger.error(f"Alarm 2: {alarm_2_obj.name} (ID={alarm_2_obj.id}, Level={alarm_2_obj.level})")
                    print(f"   ⚠️  Alarm 2: {alarm_2_obj.name} (Level: {alarm_2_obj.level})")
                
                if alarm_3_obj:
                    error_logger.error(f"Alarm 3: {alarm_3_obj.name} (ID={alarm_3_obj.id}, Level={alarm_3_obj.level})")
                    print(f"   ⚠️  Alarm 3: {alarm_3_obj.name} (Level: {alarm_3_obj.level})")
                
                error_logger.error(f"{t('device_status')}: {device_status.value}")
                
                # Grid-Status
                try:
                    error_logger.error("\n📊 GRID-STATUS:")
                    grid_a_v = await self.bridge.client.get("grid_A_voltage")
                    grid_b_v = await self.bridge.client.get("grid_B_voltage")
                    grid_c_v = await self.bridge.client.get("grid_C_voltage")
                    grid_freq = await self.bridge.client.get("grid_frequency")
                    
                    grid_info = f"Phase A: {grid_a_v.value:.1f}V, B: {grid_b_v.value:.1f}V, C: {grid_c_v.value:.1f}V, Freq: {grid_freq.value:.2f}Hz"
                    error_logger.error(f"  {grid_info}")
                    alarm_details['grid_details'] = grid_info
                except Exception as e:
                    error_logger.warning(f"  Grid-Daten nicht lesbar: {e}")
                
                # PV-Status
                try:
                    error_logger.error("\n☀️ PV-STRINGS:")
                    pv1_v = await self.bridge.client.get("pv_01_voltage")
                    pv1_a = await self.bridge.client.get("pv_01_current")
                    pv2_v = await self.bridge.client.get("pv_02_voltage")
                    pv2_a = await self.bridge.client.get("pv_02_current")
                    
                    pv_info = f"String 1: {pv1_v.value:.1f}V@{pv1_a.value:.2f}A, String 2: {pv2_v.value:.1f}V@{pv2_a.value:.2f}A"
                    error_logger.error(f"  {pv_info}")
                    alarm_details['pv_details'] = pv_info
                except Exception as e:
                    error_logger.warning(f"  PV-Daten nicht lesbar: {e}")
                
                # Temperatur
                try:
                    error_logger.error("\n🌡️ TEMPERATUREN:")
                    internal_temp = await self.bridge.client.get("internal_temperature")
                    temp_info = f"Intern: {internal_temp.value:.1f}°C"
                    error_logger.error(f"  {temp_info}")
                    alarm_details['temp_details'] = temp_info
                except Exception as e:
                    error_logger.warning(f"  Temp-Daten nicht lesbar: {e}")
                
                error_logger.error("=" * 80)
                error_logger.error("")
                
                # Sende E-Mail
                self.email.send_alarm_notification(alarm_details)
                
        except Exception as e:
            error_logger.error(f"Alarm-Check Fehler: {e}\n{traceback.format_exc()}")
    
    async def log_data(self):
        """Loggt Daten in CSV."""
        try:
            # Hole Inverter-Daten
            input_power = await self.bridge.client.get("input_power")
            grid_exported = await self.bridge.client.get("grid_exported_energy")
            meter_active_power = await self.bridge.client.get("power_meter_active_power")
            
            # PV Strings
            pv1_v = await self.bridge.client.get("pv_01_voltage")
            pv1_a = await self.bridge.client.get("pv_01_current")
            pv2_v = await self.bridge.client.get("pv_02_voltage")
            pv2_a = await self.bridge.client.get("pv_02_current")
            
            # Grid
            grid_a = await self.bridge.client.get("grid_A_voltage")
            grid_b = await self.bridge.client.get("grid_B_voltage")
            grid_c = await self.bridge.client.get("grid_C_voltage")
            
            # Inverter
            internal_temp = await self.bridge.client.get("internal_temperature")
            efficiency = await self.bridge.client.get("efficiency")
            daily_yield = await self.bridge.client.get("daily_yield_energy")
            total_yield = await self.bridge.client.get("accumulated_yield_energy")
            
            # Battery
            storage_charge = await self.bridge.client.get("storage_charge_discharge_power")
            storage_soc = await self.bridge.client.get("storage_state_of_capacity")
            
            # Alarme
            alarm_1 = await self.bridge.client.get("alarm_1")
            alarm_2 = await self.bridge.client.get("alarm_2")
            alarm_3 = await self.bridge.client.get("alarm_3")
            device_status = await self.bridge.client.get("device_status")
            
            # Berechne Werte
            solar_production = input_power.value if input_power.value else 0
            grid_power = meter_active_power.value if meter_active_power.value else 0
            grid_feed_in = max(0, grid_power)
            grid_import = max(0, -grid_power)
            house_consumption = solar_production - grid_power
            
            # Wetter (gecached)
            weather = self.last_weather_data
            
            # CSV schreiben - AlarmParser.extract_alarm_value() aus solar_core verwenden
            with open(DATA_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    int(time.time()),
                    solar_production,
                    grid_power,
                    house_consumption,
                    grid_feed_in,
                    grid_import,
                    pv1_v.value, pv1_a.value, pv1_v.value * pv1_a.value,
                    pv2_v.value, pv2_a.value, pv2_v.value * pv2_a.value,
                    grid_a.value, grid_b.value, grid_c.value,
                    internal_temp.value, efficiency.value,
                    daily_yield.value, total_yield.value,
                    storage_charge.value if storage_charge else 0,
                    storage_soc.value if storage_soc else 0,
                    weather.get('temperature_c', 0),
                    weather.get('cloud_cover_percent', 0),
                    weather.get('wind_speed_kmh', 0),
                    weather.get('precipitation_mm', 0),
                    weather.get('global_radiation_wm2', 0),
                    weather.get('direct_radiation_wm2', 0),
                    weather.get('diffuse_radiation_wm2', 0),
                    AlarmParser.extract_alarm_value(alarm_1),
                    AlarmParser.extract_alarm_value(alarm_2),
                    AlarmParser.extract_alarm_value(alarm_3),
                    device_status.value
                ])
            
            # Output status
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Solar: {solar_production:4.0f}W | "
                  f"Grid: {grid_power:5.0f}W | Consumption: {house_consumption:4.0f}W | "
                  f"Temp: {weather.get('temperature_c', 0):.1f}°C")
            
        except Exception as e:
            error_logger.error(f"Logging error: {e}\n{traceback.format_exc()}")
            print(f"✗ {t('logging_failed')}: {e}")
    
    async def run(self):
        """Main loop."""
        init_data_log()
        
        if not await self.connect_inverter():
            return
        
        # Fetch initial weather
        if self.weather:
            print(f"🌤️  {t('weather_cache_filled')}...")
            initial_weather = self.weather.get_current_weather()
            if initial_weather:
                self.last_weather_data = initial_weather
                print(f"   ✓ {t('temperature')}: {initial_weather.get('temperature_c', 0):.1f}°C")
        
        # Alarm check task
        async def alarm_checker():
            while self.running:
                await self.check_inverter_alarms()
                await asyncio.sleep(ALARM_CHECK_INTERVAL)
        
        asyncio.create_task(alarm_checker())
        
        iteration = 0
        
        try:
            while self.running:
                # Wetter-Update
                if self.weather and iteration % (WEATHER_UPDATE_INTERVAL // CHECK_INTERVAL) == 0:
                    new_weather = self.weather.get_current_weather()
                    if new_weather:
                        self.last_weather_data = new_weather
                
                # Daten loggen
                await self.log_data()
                
                # Daily Summary Check
                if self.email.check_daily_summary_time():
                    # Hole Summary-Daten aus CSV
                    daily_yield = await self.bridge.client.get("daily_yield_energy")
                    total_yield = await self.bridge.client.get("accumulated_yield_energy")
                    
                    summary_data = {
                        'daily_yield': daily_yield.value,
                        'total_yield': total_yield.value,
                        'avg_temp': self.last_weather_data.get('temperature_c', 0),
                        'avg_clouds': self.last_weather_data.get('cloud_cover_percent', 0),
                        'alarm_count': 0  # TODO: Count from logs
                    }
                    
                    self.email.send_daily_summary(summary_data)
                
                iteration += 1
                await asyncio.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 {t('shutdown_by_user')}...")
        except Exception as e:
            error_msg = f"{t('critical_error')}: {e}\n{traceback.format_exc()}"
            error_logger.error(error_msg)
            print(f"\n❌ {error_msg}")
            self.email.send_critical_error(error_msg)
        finally:
            self.running = False
            print(f"✓ {t('monitoring_stopped')}")


if __name__ == "__main__":
    import time
    monitor = SolarMonitor()
    asyncio.run(monitor.run())
