"""
Quick Log Viewer für Error Logs
"""

from pathlib import Path
from datetime import datetime, timedelta

ERROR_LOG = Path("logs/errors.log")

def view_recent_errors(hours=24):
    """Zeigt Fehler der letzten X Stunden."""
    if not ERROR_LOG.exists():
        print("✅ Keine Fehler geloggt!")
        return
    
    cutoff = datetime.now() - timedelta(hours=hours)
    
    print(f"🔍 Fehler der letzten {hours} Stunden:\n")
    print("=" * 100)
    
    with open(ERROR_LOG, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    recent_errors = []
    for line in lines:
        try:
            # Parse timestamp
            timestamp_str = line.split(' | ')[0]
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
            
            if timestamp >= cutoff:
                recent_errors.append(line.strip())
        except:
            # Mehrzeilige Einträge (Tracebacks etc.)
            if recent_errors:
                recent_errors[-1] += '\n' + line.strip()
    
    if not recent_errors:
        print(f"✅ Keine Fehler in den letzten {hours} Stunden!")
    else:
        for error in recent_errors:
            print(error)
            print("-" * 100)

def view_error_summary():
    """Zeigt Fehler-Zusammenfassung."""
    if not ERROR_LOG.exists():
        print("✅ Keine Fehler geloggt!")
        return
    
    with open(ERROR_LOG, 'r', encoding='utf-8') as f:
        content = f.read()
    
    error_types = {}
    
    # Zähle verschiedene Fehlertypen
    for line in content.split('\n'):
        if ' | ERROR | ' in line:
            try:
                error_msg = line.split(' | ERROR | ')[1]
                error_type = error_msg.split(':')[0]
                error_types[error_type] = error_types.get(error_type, 0) + 1
            except:
                pass
    
    print("📊 Fehler-Zusammenfassung:\n")
    print("=" * 60)
    for error_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
        print(f"{error_type:40s} : {count:4d}x")
    print("=" * 60)

if __name__ == "__main__":
    import sys
    
    hours = 24
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except:
            pass
    
    view_error_summary()
    print("\n")
    view_recent_errors(hours)
