"""
Internationalization (i18n) support for Solar Mining/Monitoring System.

Supports English (en) and German (de) languages.
Language is selected via LANGUAGE environment variable (default: en).
"""

import os

# Supported languages
SUPPORTED_LANGUAGES = ['en', 'de']

# Get language from environment variable
LANGUAGE = os.getenv('LANGUAGE', 'en').lower()
if LANGUAGE not in SUPPORTED_LANGUAGES:
    LANGUAGE = 'en'

# Translation dictionaries
TRANSLATIONS = {
    'en': {
        # General
        'yes': 'Yes',
        'no': 'No',
        'enabled': 'Enabled',
        'disabled': 'Disabled',
        'error': 'Error',
        'warning': 'Warning',
        'success': 'Success',
        
        # System startup
        'system_title': 'Solar Mining System - Windows',
        'system_title_pi': 'Solar Monitoring System - Raspberry Pi',
        'configuration': 'Configuration',
        'inverter_ip': 'Inverter IP',
        'weather_enabled': 'Weather',
        'email_enabled': 'Email',
        'nicehash_enabled': 'NiceHash',
        'starting': 'Starting',
        'startup_complete': 'System startup complete',
        'startup_failed': 'System startup failed',
        
        # Weather
        'weather_cache_filled': 'Weather cache initialized',
        'weather_update': 'Weather updated',
        'weather_update_failed': 'Weather update failed',
        
        # Inverter connection
        'connecting_inverter': 'Connecting to inverter',
        'inverter_connected': 'Inverter connected',
        'connection_error': 'Connection error',
        'connection_retry': 'Retrying connection',
        'connection_timeout': 'Connection timeout. Reconnecting...',
        
        # Alarm messages
        'alarm_detected': 'Alarm detected',
        'alarm_details': 'Alarm details',
        'grid_status': 'GRID STATUS',
        'pv_strings': 'PV STRINGS',
        'temperatures': 'TEMPERATURES',
        'device_status': 'Device Status',
        'grid_details_phase': 'Phase A: {a}V, B: {b}V, C: {c}V, Freq: {freq}Hz',
        'pv_details_string': 'String 1: {v1}V@{a1}A, String 2: {v2}V@{a2}A',
        'temp_details_internal': 'Internal: {temp}°C',
        'grid_data_unavailable': 'Grid data not available',
        'pv_data_unavailable': 'PV data not available',
        'temp_data_unavailable': 'Temperature data not available',
        'alarm_check_failed': 'Alarm check failed',
        
        # Mining control
        'mining_status': 'Mining',
        'mining_running': 'RUNNING',
        'mining_stopped': 'STOPPED',
        'mining_starting': 'STARTING MINING!',
        'mining_stopping': 'STOPPING MINING!',
        'mining_already_running': 'Mining already running - skipping start',
        'mining_already_stopped': 'Mining already stopped',
        'configuring_mining': 'Configuring mining...',
        'subscribe_success': 'Subscribe successful',
        'subscribe_error': 'Subscribe error',
        'subscribe_no_response': 'Subscribe: No response from Excavator',
        'algorithm_added': 'Algorithm \'{algo}\' added',
        'algorithm_error': 'Algorithm error',
        'algorithm_no_response': 'Algorithm: No response from Excavator',
        'worker_started': 'Worker {id} started',
        'worker_error': 'Worker error',
        'worker_no_response': 'Worker Start: No response from Excavator',
        'start_error': 'Start error',
        'start_failed_retry': 'Start failed, will retry later',
        'stopping_mining': 'Stopping mining...',
        'workers_cleared': 'All workers cleared',
        'algorithms_cleared': 'All algorithms cleared',
        'stop_error': 'Stop error',
        
        # GPU monitoring
        'gpu_monitoring_error': 'GPU monitoring error',
        'gpu_usage_high': 'Other program using GPU (>{percent}%) - pausing mining',
        'gpu_usage_normal': 'GPU available again - resuming mining',
        'gpu_not_found': 'GPU not found',
        
        # Power/Energy display
        'solar_production': 'Solar',
        'consumption': 'Consumption',
        'house_consumption': '(House)',
        'grid_export': 'Export',
        'grid_import': 'Import',
        'to_grid': '(to grid)',
        'from_grid': '(from grid)',
        'available_power': 'Available',
        'for_mining': '(for Mining)',
        'temperature': 'Temp',
        'enough_power': 'Enough Power! {current}/{required}',
        'not_enough_power': 'Not enough power {current}/{required}',
        
        # Email notifications
        'email_sent': 'Email sent',
        'email_failed': 'Email send failed',
        'email_alarm_subject': '⚠️ Solar System Alarm',
        'email_error_subject': '🚨 Critical Error',
        'email_daily_subject': '☀️ Daily Solar Report',
        'email_alarm_body': 'Alarm detected in solar system:\n\nName: {name}\nID: {id}\nLevel: {level}\n\nGrid: {grid}\nPV: {pv}\nTemperature: {temp}',
        'email_error_body': 'Critical error in monitoring system:\n\n{error}',
        
        # CSV logging
        'csv_initialized': 'CSV log file initialized',
        'data_logged': 'Data logged',
        'logging_error': 'Logging error',
        
        # Excavator API
        'api_error': 'API Error ({count}x)',
        'excavator_not_responding': 'Excavator not responding! Restart process?',
        'excavator_already_running': 'Excavator already running (Version {version})',
        'excavator_not_found': 'Excavator not found',
        'please_adjust_path': 'Please adjust EXCAVATOR_PATH in configuration!',
        'starting_excavator': 'Starting Excavator',
        'api_port': 'API Port',
        'priority_set': 'Priority set to BELOW_NORMAL (gaming-friendly)',
        'waiting_for_api': 'Waiting for API...',
        'excavator_started': 'Excavator started! Version: {version}',
        'excavator_start_timeout': 'Timeout waiting for Excavator API',
        'excavator_start_error': 'Error starting Excavator',
        
        # Status output format
        'status_line': '[{index}] {time}',
        'status_solar': '☀️  Solar:         {power:4.0f} W',
        'status_consumption': '🏠 Consumption:    {power:4.0f} W (House)',
        'status_export': '📤 Export:        {power:4.0f} W (to grid)',
        'status_import': '📥 Import:        {power:4.0f} W (from grid)',
        'status_available': '✨ Available:     {power:4.0f} W (for Mining)',
        'status_mining': '⛏️  Mining:       {status}',
        'status_weather': '🌡️  Weather:       {temp}°C, ☁️ {clouds}%, ☀️ {radiation} W/m²',
        'status_power_check': '➕ {message}',
        
        # Additional Excavator messages
        'excavator_process_not_responding': 'Excavator process running but API not responding!',
        'terminating_old_process': 'Terminating old process and restarting...',
        'excavator_crashed': 'Excavator process crashed!',
        'restarting_excavator': 'Restarting Excavator...',
        'connecting_to_inverter': 'Connecting to inverter',
        'inverter_connection_success': 'Inverter connected!',
        'checking_excavator_api': 'Checking Excavator API on',
        'excavator_could_not_start': 'Excavator could not be started!',
        'reading_error': 'Read error',
        'alarm_warning': 'INVERTER ALARM DETECTED!',
        'unsubscribe_error': 'Unsubscribe error',
        'disconnected_from_stratum': 'Disconnected from stratum',
        'pid': 'PID',
        'remaining_seconds': '{seconds}s remaining...',
        
        # Status display
        'logging_failed': 'Logging error',
        'shutdown_by_user': 'Shutdown by user',
        'critical_error': 'Critical error',
        'monitoring_stopped': 'Monitoring stopped',
    },
    'de': {
        # General / Allgemein
        'yes': 'Ja',
        'no': 'Nein',
        'enabled': 'Aktiviert',
        'disabled': 'Deaktiviert',
        'error': 'Fehler',
        'warning': 'Warnung',
        'success': 'Erfolg',
        
        # System startup / Systemstart
        'system_title': 'Solar Mining System - Windows',
        'system_title_pi': 'Solar Monitoring System - Raspberry Pi',
        'configuration': 'Konfiguration',
        'inverter_ip': 'Inverter IP',
        'weather_enabled': 'Wetter',
        'email_enabled': 'E-Mail',
        'nicehash_enabled': 'NiceHash',
        'starting': 'Starte',
        'startup_complete': 'Systemstart abgeschlossen',
        'startup_failed': 'Systemstart fehlgeschlagen',
        
        # Weather / Wetter
        'weather_cache_filled': 'Wetter-Cache initialisiert',
        'weather_update': 'Wetter aktualisiert',
        'weather_update_failed': 'Wetter-Aktualisierung fehlgeschlagen',
        
        # Inverter connection / Wechselrichter-Verbindung
        'connecting_inverter': 'Verbinde mit Wechselrichter',
        'inverter_connected': 'Wechselrichter verbunden',
        'connection_error': 'Verbindungsfehler',
        'connection_retry': 'Verbindung wird wiederholt',
        'connection_timeout': 'Timeout beim Warten auf Verbindung. Reconnecting...',
        
        # Alarm messages / Alarmmeldungen
        'alarm_detected': 'Alarm erkannt',
        'alarm_details': 'Alarm-Details',
        'grid_status': 'NETZ-STATUS',
        'pv_strings': 'PV-STRINGS',
        'temperatures': 'TEMPERATUREN',
        'device_status': 'Gerätestatus',
        'grid_details_phase': 'Phase A: {a}V, B: {b}V, C: {c}V, Freq: {freq}Hz',
        'pv_details_string': 'String 1: {v1}V@{a1}A, String 2: {v2}V@{a2}A',
        'temp_details_internal': 'Intern: {temp}°C',
        'grid_data_unavailable': 'Netz-Daten nicht lesbar',
        'pv_data_unavailable': 'PV-Daten nicht lesbar',
        'temp_data_unavailable': 'Temp-Daten nicht lesbar',
        'alarm_check_failed': 'Alarm-Check Fehler',
        
        # Mining control / Mining-Steuerung
        'mining_status': 'Mining',
        'mining_running': 'LÄUFT',
        'mining_stopped': 'GESTOPPT',
        'mining_starting': 'STARTE MINING!',
        'mining_stopping': 'STOPPE MINING!',
        'mining_already_running': 'Mining läuft bereits - überspringe Start',
        'mining_already_stopped': 'Mining bereits gestoppt',
        'configuring_mining': 'Konfiguriere Mining...',
        'subscribe_success': 'Subscribe erfolgreich',
        'subscribe_error': 'Subscribe Fehler',
        'subscribe_no_response': 'Subscribe: Keine Antwort von Excavator',
        'algorithm_added': 'Algorithm \'{algo}\' hinzugefügt',
        'algorithm_error': 'Algorithm Fehler',
        'algorithm_no_response': 'Algorithm: Keine Antwort von Excavator',
        'worker_started': 'Worker {id} gestartet',
        'worker_error': 'Worker Fehler',
        'worker_no_response': 'Worker Start: Keine Antwort von Excavator',
        'start_error': 'Start-Fehler',
        'start_failed_retry': 'Start fehlgeschlagen, versuche später erneut',
        'stopping_mining': 'Stoppe Mining...',
        'workers_cleared': 'Alle Worker entfernt',
        'algorithms_cleared': 'Alle Algorithmen entfernt',
        'stop_error': 'Stop-Fehler',
        
        # GPU monitoring / GPU-Überwachung
        'gpu_monitoring_error': 'GPU Monitoring Fehler',
        'gpu_usage_high': 'Anderes Programm nutzt GPU (>{percent}%) - pausiere Mining',
        'gpu_usage_normal': 'GPU wieder verfügbar - setze Mining fort',
        'gpu_not_found': 'GPU nicht gefunden',
        
        # Power/Energy display / Leistungsanzeige
        'solar_production': 'Solar',
        'consumption': 'Verbrauch',
        'house_consumption': '(Haus)',
        'grid_export': 'Einspeisung',
        'grid_import': 'Bezug',
        'to_grid': '(ins Netz)',
        'from_grid': '(aus Netz)',
        'available_power': 'Verfügbar',
        'for_mining': '(für Mining)',
        'temperature': 'Temp',
        'enough_power': 'Genug Power! {current}/{required}',
        'not_enough_power': 'Nicht genug Power {current}/{required}',
        
        # Email notifications / E-Mail-Benachrichtigungen
        'email_sent': 'E-Mail gesendet',
        'email_failed': 'E-Mail-Versand fehlgeschlagen',
        'email_alarm_subject': '⚠️ Solaranlage Alarm',
        'email_error_subject': '🚨 Kritischer Fehler',
        'email_daily_subject': '☀️ Täglicher Solar-Report',
        'email_alarm_body': 'Alarm in Solaranlage erkannt:\n\nName: {name}\nID: {id}\nLevel: {level}\n\nNetz: {grid}\nPV: {pv}\nTemperatur: {temp}',
        'email_error_body': 'Kritischer Fehler im Überwachungssystem:\n\n{error}',
        
        # CSV logging / CSV-Protokollierung
        'csv_initialized': 'CSV-Log-Datei initialisiert',
        'data_logged': 'Daten protokolliert',
        'logging_error': 'Logging-Fehler',
        
        # Excavator API
        'api_error': 'API Fehler ({count}x)',
        'excavator_not_responding': 'Excavator antwortet nicht! Prozess neu starten?',
        'excavator_already_running': 'Excavator läuft bereits (Version {version})',
        'excavator_not_found': 'Excavator nicht gefunden',
        'please_adjust_path': 'Bitte EXCAVATOR_PATH in der Konfiguration anpassen!',
        'starting_excavator': 'Starte Excavator',
        'api_port': 'API Port',
        'priority_set': 'Priorität auf BELOW_NORMAL gesetzt (Gaming-freundlich)',
        'waiting_for_api': 'Warte auf API...',
        'excavator_started': 'Excavator gestartet! Version: {version}',
        'excavator_start_timeout': 'Timeout beim Warten auf Excavator API',
        'excavator_start_error': 'Fehler beim Starten von Excavator',
        
        # Status output format / Status-Ausgabe-Format
        'status_line': '[{index}] {time}',
        'status_solar': '☀️  Solar:         {power:4.0f} W',
        'status_consumption': '🏠 Verbrauch:      {power:4.0f} W (Haus)',
        'status_export': '📤 Einspeisung:   {power:4.0f} W (ins Netz)',
        'status_import': '📥 Bezug:         {power:4.0f} W (aus Netz)',
        'status_available': '✨ Verfügbar:     {power:4.0f} W (für Mining)',
        'status_mining': '⛏️  Mining:       {status}',
        'status_weather': '🌡️  Wetter:        {temp}°C, ☁️ {clouds}%, ☀️ {radiation} W/m²',
        'status_power_check': '➕ {message}',
        
        # Additional Excavator messages / Zusätzliche Excavator-Meldungen
        'excavator_process_not_responding': 'Excavator Prozess läuft, aber API antwortet nicht!',
        'terminating_old_process': 'Beende alten Prozess und starte neu...',
        'excavator_crashed': 'Excavator Prozess ist abgestürzt!',
        'restarting_excavator': 'Starte Excavator neu...',
        'connecting_to_inverter': 'Verbinde mit Inverter',
        'inverter_connection_success': 'Inverter verbunden!',
        'checking_excavator_api': 'Prüfe Excavator API auf',
        'excavator_could_not_start': 'Excavator konnte nicht gestartet werden!',
        'reading_error': 'Fehler beim Lesen',
        'alarm_warning': 'INVERTER ALARM ERKANNT!',
        'unsubscribe_error': 'Unsubscribe Fehler',
        'disconnected_from_stratum': 'Von Stratum getrennt',
        'pid': 'PID',
        'remaining_seconds': '{seconds}s verbleibend...',
        
        # Status display / Statusanzeige
        'logging_failed': 'Log-Fehler',
        'shutdown_by_user': 'Shutdown durch Benutzer',
        'critical_error': 'Kritischer Fehler',
        'monitoring_stopped': 'Monitoring beendet',
    }
}


def t(key: str, **kwargs) -> str:
    """
    Get translated string for the current language.
    
    Args:
        key: Translation key
        **kwargs: Format arguments for string interpolation
        
    Returns:
        Translated and formatted string
        
    Example:
        >>> t('worker_started', id=1)
        'Worker 1 started'  # if LANGUAGE=en
        'Worker 1 gestartet'  # if LANGUAGE=de
    """
    translation = TRANSLATIONS.get(LANGUAGE, TRANSLATIONS['en']).get(key, key)
    
    if kwargs:
        try:
            return translation.format(**kwargs)
        except KeyError:
            # If formatting fails, return unformatted string
            return translation
    
    return translation


def get_language() -> str:
    """Get current language code."""
    return LANGUAGE


def set_language(lang: str) -> bool:
    """
    Set language for translations.
    
    Args:
        lang: Language code ('en' or 'de')
        
    Returns:
        True if language was changed, False if invalid
    """
    global LANGUAGE
    
    if lang.lower() in SUPPORTED_LANGUAGES:
        LANGUAGE = lang.lower()
        return True
    
    return False
