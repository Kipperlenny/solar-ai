"""
Solar Monitoring System - Shared Core Library
==============================================
Shared components for Windows and Raspberry Pi versions.

Follows DRY (Don't Repeat Yourself) and SOLID principles.
Provides reusable infrastructure for both deployment targets.
"""

import asyncio
import os
import logging
import csv
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from dotenv import load_dotenv
import requests

try:
    from huawei_solar import HuaweiSolarBridge
    HUAWEI_AVAILABLE = True
except ImportError:
    HUAWEI_AVAILABLE = False


class WeatherAPI:
    """Open-Meteo Weather API Client (shared)."""
    
    def __init__(self, latitude, longitude, update_interval=600):
        self.latitude = latitude
        self.longitude = longitude
        self.update_interval = update_interval
        self.last_update = 0
        self.api_url = "https://api.open-meteo.com/v1/forecast"
    
    def get_current_weather(self):
        """
        Fetch current weather data with rate limiting.
        
        Returns None if update interval hasn't elapsed yet.
        """
        now = time.time()
        if now - self.last_update < self.update_interval:
            return None  # Update not needed yet
        
        try:
            params = {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'current': 'temperature_2m,cloud_cover,wind_speed_10m,precipitation,global_tilted_irradiance,direct_radiation,diffuse_radiation',
                'timezone': 'auto'
            }
            
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            current = data.get('current', {})
            
            weather_data = {
                'temperature_c': current.get('temperature_2m', 0),
                'cloud_cover_percent': current.get('cloud_cover', 0),
                'wind_speed_kmh': current.get('wind_speed_10m', 0),
                'precipitation_mm': current.get('precipitation', 0),
                'global_radiation_wm2': current.get('global_tilted_irradiance', 0),
                'direct_radiation_wm2': current.get('direct_radiation', 0),
                'diffuse_radiation_wm2': current.get('diffuse_radiation', 0)
            }
            
            self.last_update = now
            return weather_data
            
        except Exception as e:
            logging.warning(f"Weather API error: {e}")
            return None


class InverterConnection:
    """Huawei Solar Inverter Connection (shared)."""
    
    def __init__(self, host, port, slave_id=1):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.bridge = None
    
    async def connect(self):
        """Verbinde zu Inverter."""
        if not HUAWEI_AVAILABLE:
            raise Exception("huawei-solar nicht installiert!")
        
        try:
            self.bridge = await HuaweiSolarBridge.create(
                host=self.host,
                port=self.port,
                slave_id=self.slave_id
            )
            return True
        except Exception as e:
            logging.error(f"Inverter-Verbindung fehlgeschlagen: {e}")
            return False
    
    async def get_register(self, register_name):
        """Lese Register vom Inverter."""
        if not self.bridge:
            raise Exception("Nicht verbunden!")
        return await self.bridge.client.get(register_name)


class AlarmParser:
    """
    Alarm parsing logic (shared).
    
    Handles various alarm formats from Huawei Solar API:
    - Direct Alarm objects with .id attribute
    - Lists of Alarm objects
    - Integer values
    - Empty/None values
    """
    
    @staticmethod
    def extract_alarm_value(alarm_raw):
        """
        Extract alarm ID from various formats.
        
        Returns alarm ID as integer, or 0 if no alarm.
        """
        if alarm_raw is None:
            return 0
        
        val = alarm_raw.value if hasattr(alarm_raw, 'value') else alarm_raw
        
        # Alarm object with .id attribute
        if hasattr(val, 'id'):
            return val.id
        
        # List of Alarm objects
        if isinstance(val, list) and len(val) > 0:
            if hasattr(val[0], 'id'):
                return val[0].id
            return int(val[0]) if val[0] else 0
        
        # Ignore strings
        if isinstance(val, str):
            return 0
        
        # Direct integer value
        return int(val) if val else 0
    
    @staticmethod
    def get_alarm_details(alarm_obj):
        """
        Get detailed alarm information (ID + Alarm object).
        
        Returns tuple: (alarm_id: int, alarm_object: Alarm|None)
        """
        val = alarm_obj.value
        
        # List of Alarm objects
        if isinstance(val, list) and len(val) > 0:
            if hasattr(val[0], 'id'):
                return val[0].id, val[0]
            return int(val[0]) if val[0] else 0, None
        
        # Direct Alarm object
        if hasattr(val, 'id'):
            return val.id, val
        
        # Empty/no alarm
        if not val or (isinstance(val, list) and len(val) == 0):
            return 0, None
        
        return int(val) if val else 0, None


class CSVLogger:
    """CSV Data Logger (shared)."""
    
    def __init__(self, log_file, columns):
        self.log_file = Path(log_file)
        self.columns = columns
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with header if it doesn't exist."""
        if not self.log_file.exists():
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.columns)
    
    def log_data(self, data_dict):
        """Write data row to CSV file."""
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                row = [data_dict.get(col, 0) for col in self.columns]
                writer.writerow(row)
        except Exception as e:
            logging.error(f"CSV logging error: {e}")


class AlarmDiagnostics:
    """
    Extended alarm diagnostics (shared).
    
    Provides comprehensive context information when alarms occur,
    including grid status, PV string data, and temperature readings.
    """
    
    def __init__(self, inverter_connection):
        self.inverter = inverter_connection
    
    async def get_full_alarm_context(self):
        """
        Fetch complete alarm context data.
        
        Returns dict with grid, PV, and temperature information.
        """
        context = {}
        
        # Grid status
        try:
            grid_a_v = await self.inverter.get_register("grid_A_voltage")
            grid_b_v = await self.inverter.get_register("grid_B_voltage")
            grid_c_v = await self.inverter.get_register("grid_C_voltage")
            grid_freq = await self.inverter.get_register("grid_frequency")
            
            context['grid'] = {
                'phase_a': grid_a_v.value,
                'phase_b': grid_b_v.value,
                'phase_c': grid_c_v.value,
                'frequency': grid_freq.value
            }
        except Exception as e:
            context['grid'] = {'error': str(e)}
        
        # PV strings
        try:
            pv1_v = await self.inverter.get_register("pv_01_voltage")
            pv1_a = await self.inverter.get_register("pv_01_current")
            pv2_v = await self.inverter.get_register("pv_02_voltage")
            pv2_a = await self.inverter.get_register("pv_02_current")
            
            context['pv'] = {
                'string_1_voltage': pv1_v.value,
                'string_1_current': pv1_a.value,
                'string_2_voltage': pv2_v.value,
                'string_2_current': pv2_a.value
            }
        except Exception as e:
            context['pv'] = {'error': str(e)}
        
        # Temperature
        try:
            internal_temp = await self.inverter.get_register("internal_temperature")
            context['temperature'] = {'internal': internal_temp.value}
        except Exception as e:
            context['temperature'] = {'error': str(e)}
        
        return context
    
    def format_alarm_report(self, alarm_obj, context):
        """
        Format alarm report as text.
        
        Creates a detailed text report with alarm info and context data.
        """
        lines = [
            "=" * 80,
            "🚨 ALARM SNAPSHOT",
            "=" * 80,
            f"Alarm: {alarm_obj.name}",
            f"ID: {alarm_obj.id}",
            f"Level: {alarm_obj.level}",
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Grid
        if 'grid' in context and 'error' not in context['grid']:
            grid = context['grid']
            lines.extend([
                "📊 GRID-STATUS:",
                f"  Phase A: {grid['phase_a']:.1f}V",
                f"  Phase B: {grid['phase_b']:.1f}V",
                f"  Phase C: {grid['phase_c']:.1f}V",
                f"  Frequency: {grid['frequency']:.2f}Hz",
                ""
            ])
        
        # PV
        if 'pv' in context and 'error' not in context['pv']:
            pv = context['pv']
            lines.extend([
                "☀️ PV-STRINGS:",
                f"  String 1: {pv['string_1_voltage']:.1f}V @ {pv['string_1_current']:.2f}A",
                f"  String 2: {pv['string_2_voltage']:.1f}V @ {pv['string_2_current']:.2f}A",
                ""
            ])
        
        # Temperatur
        if 'temperature' in context and 'error' not in context['temperature']:
            temp = context['temperature']
            lines.extend([
                "🌡️ TEMPERATUREN:",
                f"  Intern: {temp['internal']:.1f}°C",
                ""
            ])
        
        lines.append("=" * 80)
        return "\n".join(lines)


class EmailNotifier:
    """E-Mail Benachrichtigungssystem (shared, optional)."""
    
    def __init__(self, config):
        """
        config = {
            'enabled': bool,
            'smtp_server': str,
            'smtp_port': int,
            'use_tls': bool,
            'from': str,
            'to': str,
            'username': str,
            'password': str,
            'send_on_alarm': bool,
            'send_on_critical': bool,
            'send_daily_summary': bool,
            'daily_summary_time': str
        }
        """
        self.enabled = config.get('enabled', False)
        self.smtp_server = config.get('smtp_server')
        self.smtp_port = config.get('smtp_port', 587)
        self.use_tls = config.get('use_tls', True)
        self.from_addr = config.get('from')
        self.to_addr = config.get('to')
        self.username = config.get('username', self.from_addr)
        self.password = config.get('password')
        self.send_on_alarm = config.get('send_on_alarm', True)
        self.send_on_critical = config.get('send_on_critical', True)
        self.send_daily_summary = config.get('send_daily_summary', False)
        self.daily_summary_time = config.get('daily_summary_time', '18:00')
        self.last_daily_summary = None
        
        if self.enabled and not self.from_addr:
            logging.warning("Email enabled but FROM address not set!")
            self.enabled = False
    
    def send_email(self, subject, body, is_html=False):
        """Send email via SMTP."""
        if not self.enabled:
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[Solar Monitor] {subject}"
            msg['From'] = self.from_addr
            msg['To'] = self.to_addr
            
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # SMTP connection
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            
            # Login
            if self.password:
                server.login(self.username, self.password)
            
            server.send_message(msg)
            server.quit()
            
            logging.info(f"Email sent: {subject}")
            return True
            
        except Exception as e:
            logging.error(f"Email error: {e}")
            return False
    
    def send_alarm_notification(self, alarm_details):
        """Send alarm notification email."""
        if not self.send_on_alarm:
            return
        
        subject = f"⚠️ Inverter Alarm: {alarm_details.get('name', 'Unknown')}"
        
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
        """Send critical error notification email."""
        if not self.send_on_critical:
            return
        
        subject = "🚨 Critical Error"
        body = f"""
Solar Monitoring - Critical error occurred!

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Error:
{error_message}

The system may not be functioning correctly.
Please check immediately!
"""
        
        self.send_email(subject, body)
    
    def send_daily_summary(self, summary_data):
        """Send daily summary email."""
        if not self.send_daily_summary:
            return
        
        subject = f"📊 Daily Summary - {datetime.now().strftime('%Y-%m-%d')}"
        
        body = f"""
Solar Monitoring - Daily Summary

Date: {datetime.now().strftime('%Y-%m-%d')}

Production:
  Today: {summary_data.get('daily_yield', 0):.2f} kWh
  Total: {summary_data.get('total_yield', 0):.2f} kWh

Average:
  Solar: {summary_data.get('avg_solar', 0):.0f} W
  Grid: {summary_data.get('avg_grid', 0):.0f} W
  Consumption: {summary_data.get('avg_consumption', 0):.0f} W

Weather:
  Temperature: {summary_data.get('avg_temp', 0):.1f}°C
  Clouds: {summary_data.get('avg_clouds', 0):.0f}%

Alarme heute: {summary_data.get('alarm_count', 0)}
"""
        
        self.send_email(subject, body)
    
    def check_daily_summary_time(self):
        """Check if it's time to send daily summary."""
        if not self.send_daily_summary:
            return False
        
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        
        try:
            hour, minute = map(int, self.daily_summary_time.split(':'))
            target_time = dt_time(hour, minute)
        except:
            target_time = dt_time(18, 0)
        
        if now.time() >= target_time and self.last_daily_summary != today_str:
            self.last_daily_summary = today_str
            return True
        
        return False


class EmailNotifier:
    """
    Email notification system (shared).
    
    Supports SMTP/TLS for sending alarm notifications, error alerts,
    and optional daily summaries.
    """
    
    def __init__(self, config):
        """
        config = {
            'enabled': bool,
            'smtp_server': str,
            'smtp_port': int,
            'use_tls': bool,
            'from': str,
            'to': str,
            'username': str,
            'password': str,
            'send_on_alarm': bool,
            'send_on_error': bool,
            'send_daily': bool,
            'daily_time': str
        }
        """
        self.config = config
        self.enabled = config.get('enabled', False)
        self.last_daily_summary = None
        
        if self.enabled and not config.get('from'):
            logging.warning("E-Mail aktiviert aber EMAIL_FROM nicht gesetzt!")
            self.enabled = False
    
    def send_email(self, subject, body, is_html=False):
        """Sendet E-Mail via SMTP."""
        if not self.enabled:
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[Solar Monitor] {subject}"
            msg['From'] = self.config['from']
            msg['To'] = self.config['to']
            
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # SMTP-Verbindung
            if self.config.get('use_tls', True):
                server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.config['smtp_server'], self.config['smtp_port'])
            
            if self.config.get('password'):
                server.login(self.config.get('username', self.config['from']), self.config['password'])
            
            server.send_message(msg)
            server.quit()
            
            logging.info(f"E-Mail gesendet: {subject}")
            return True
            
        except Exception as e:
            logging.error(f"E-Mail-Fehler: {e}")
            return False
    
    def send_alarm_notification(self, alarm_details):
        """Sendet Alarm-Benachrichtigung."""
        if not self.config.get('send_on_alarm', True):
            return
        
        subject = f"⚠️ Inverter Alarm: {alarm_details.get('name', 'Unbekannt')}"
        
        body = f"""
Solar Monitoring - Alarm erkannt!

Alarm: {alarm_details.get('name', 'Unbekannt')}
ID: {alarm_details.get('id', 'N/A')}
Level: {alarm_details.get('level', 'N/A')}
Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Device Status: {alarm_details.get('device_status', 'Unbekannt')}

Details siehe errors.log
"""
        
        self.send_email(subject, body)
    
    def send_critical_error(self, error_message):
        """Sendet kritische Fehler-Benachrichtigung."""
        if not self.config.get('send_on_error', True):
            return
        
        subject = "🚨 Kritischer Fehler"
        body = f"""
Solar Monitoring - Kritischer Fehler!

Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Fehler:
{error_message}

Das System läuft möglicherweise nicht korrekt.
"""
        
        self.send_email(subject, body)


def setup_logging(log_dir, error_log_filename):
    """Setup Standard-Logging (shared)."""
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)
    
    error_logger = logging.getLogger('error_logger')
    error_logger.setLevel(logging.DEBUG)
    
    handler = logging.FileHandler(log_dir / error_log_filename, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    handler.setFormatter(formatter)
    
    error_logger.addHandler(handler)
    
    return error_logger


# CSV Column Definitions (shared)
CSV_COLUMNS_FULL = [
    'timestamp', 'unix_timestamp',
    'solar_production_w', 'grid_power_w', 'house_consumption_w',
    'grid_feed_in_w', 'grid_import_w', 'available_for_mining_w',
    'mining_active', 'mining_paused', 'hashrate_mhs', 'excavator_errors',
    'start_confirmations', 'stop_confirmations',
    'gpu_usage_percent', 'gpu_temp_c',
    'pv_01_voltage_v', 'pv_01_current_a', 'pv_01_power_w',
    'pv_02_voltage_v', 'pv_02_current_a', 'pv_02_power_w',
    'grid_A_voltage_v', 'grid_B_voltage_v', 'grid_C_voltage_v',
    'grid_A_current_a', 'grid_B_current_a', 'grid_C_current_a',
    'grid_A_power_w', 'grid_B_power_w', 'grid_C_power_w',
    'internal_temp_c', 'efficiency_percent',
    'daily_yield_kwh', 'total_yield_kwh',
    'battery_power_w', 'battery_soc_percent',
    'weather_temp_c', 'weather_cloud_cover_percent', 'weather_wind_speed_kmh',
    'weather_precipitation_mm', 'weather_global_radiation_wm2',
    'weather_direct_radiation_wm2', 'weather_diffuse_radiation_wm2',
    'inverter_alarm_1', 'inverter_alarm_2', 'inverter_alarm_3',
    'inverter_device_status'
]

CSV_COLUMNS_MINIMAL = [
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
]
