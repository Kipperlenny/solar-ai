"""
GPU Thermal Log Viewer - Easy to read display of thermal events and statistics
"""
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

THERMAL_LOG = Path("logs/gpu_thermal.csv")

def view_thermal_log(recent_hours=None, device_id=None, show_throttle_only=False):
    """
    Display GPU thermal log in a human-readable format.
    
    Args:
        recent_hours: Only show events from last N hours (None = show all)
        device_id: Filter by specific GPU device ID (None = show all)
        show_throttle_only: Only show throttling events (ignore normal temps)
    """
    if not THERMAL_LOG.exists():
        print(f"❌ Thermal log not found: {THERMAL_LOG}")
        print("   Run the mining script first to generate thermal data.")
        return
    
    print("=" * 100)
    print("GPU THERMAL MONITORING LOG")
    print("=" * 100)
    
    # Read all events
    events = []
    with open(THERMAL_LOG, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(row)
    
    if not events:
        print("\nNo thermal events logged yet.")
        return
    
    # Filter by time if requested
    if recent_hours:
        cutoff_time = datetime.now().timestamp() - (recent_hours * 3600)
        events = [e for e in events if float(e['unix_timestamp']) >= cutoff_time]
        print(f"\n📅 Showing events from last {recent_hours} hours")
    else:
        print(f"\n📅 Showing all events (total: {len(events)})")
    
    # Filter by device if requested
    if device_id is not None:
        events = [e for e in events if e['device_id'] == str(device_id)]
        print(f"🎯 Filtering for GPU {device_id}")
    
    # Filter throttle events only if requested
    if show_throttle_only:
        events = [e for e in events if e['thermal_action'] != 'normal']
        print(f"⚠️  Showing throttle events only")
    
    if not events:
        print(f"\n✓ No events match your filters.")
        return
    
    print(f"\n📊 Found {len(events)} matching events")
    print("=" * 100)
    
    # Statistics
    stats_by_gpu = defaultdict(lambda: {
        'max_core_temp': 0,
        'max_vram_temp': 0,
        'avg_core_temp': [],
        'avg_vram_temp': [],
        'throttle_count': 0,
        'critical_count': 0,
        'min_tdp': 100,
        'max_tdp': 0,
    })
    
    # Display events
    print("\n📋 THERMAL EVENTS:")
    print("-" * 100)
    print(f"{'Timestamp':<20} {'GPU':<4} {'Action':<18} {'Core°C':<7} {'VRAM°C':<7} {'TDP%':<5} {'Fan%':<5} {'Notes':<30}")
    print("-" * 100)
    
    for event in events:
        timestamp = event['timestamp']
        gpu = f"GPU{event['device_id']}"
        action = event['thermal_action']
        core_temp = float(event['gpu_core_temp_c']) if event['gpu_core_temp_c'] else 0
        vram_temp = float(event['gpu_vram_temp_c']) if event['gpu_vram_temp_c'] else 0
        tdp = float(event['gpu_tdp_percent']) if event['gpu_tdp_percent'] else 0
        fan = float(event['gpu_fan_speed_percent']) if event['gpu_fan_speed_percent'] else 0
        notes = event['notes'][:28] if event['notes'] else ''
        
        # Color coding for action
        action_display = action
        if action == 'critical_shutdown':
            action_display = f"🚨 {action}"
        elif action in ['throttle_start', 'throttle_increase']:
            action_display = f"⚠️  {action}"
        elif action == 'throttle_release':
            action_display = f"✅ {action}"
        
        print(f"{timestamp:<20} {gpu:<4} {action_display:<20} {core_temp:<7.1f} {vram_temp:<7.1f} {tdp:<5.0f} {fan:<5.0f} {notes:<30}")
        
        # Update stats
        dev_id = event['device_id']
        stats_by_gpu[dev_id]['max_core_temp'] = max(stats_by_gpu[dev_id]['max_core_temp'], core_temp)
        stats_by_gpu[dev_id]['max_vram_temp'] = max(stats_by_gpu[dev_id]['max_vram_temp'], vram_temp)
        stats_by_gpu[dev_id]['avg_core_temp'].append(core_temp)
        stats_by_gpu[dev_id]['avg_vram_temp'].append(vram_temp)
        stats_by_gpu[dev_id]['min_tdp'] = min(stats_by_gpu[dev_id]['min_tdp'], tdp)
        stats_by_gpu[dev_id]['max_tdp'] = max(stats_by_gpu[dev_id]['max_tdp'], tdp)
        
        if action in ['throttle_start', 'throttle_increase']:
            stats_by_gpu[dev_id]['throttle_count'] += 1
        if action == 'critical_shutdown':
            stats_by_gpu[dev_id]['critical_count'] += 1
    
    # Display summary statistics
    print("\n" + "=" * 100)
    print("📊 THERMAL STATISTICS")
    print("=" * 100)
    
    for dev_id, stats in sorted(stats_by_gpu.items()):
        gpu_name = events[0].get('device_name', f'GPU {dev_id}')
        print(f"\nGPU {dev_id} ({gpu_name}):")
        print(f"  Core Temperature:")
        print(f"    Max:     {stats['max_core_temp']:.1f}°C")
        if stats['avg_core_temp']:
            avg_core = sum(stats['avg_core_temp']) / len(stats['avg_core_temp'])
            print(f"    Average: {avg_core:.1f}°C")
        
        print(f"  VRAM Temperature:")
        print(f"    Max:     {stats['max_vram_temp']:.1f}°C")
        if stats['avg_vram_temp']:
            avg_vram = sum(stats['avg_vram_temp']) / len(stats['avg_vram_temp'])
            print(f"    Average: {avg_vram:.1f}°C")
        
        print(f"  TDP Range: {stats['min_tdp']:.0f}% - {stats['max_tdp']:.0f}%")
        print(f"  Throttle Events: {stats['throttle_count']}")
        print(f"  Critical Events: {stats['critical_count']}")
        
        if stats['critical_count'] > 0:
            print(f"  ⚠️  WARNING: GPU reached critical temperature {stats['critical_count']} time(s)!")
    
    print("\n" + "=" * 100)

if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    recent_hours = None
    device_id = None
    throttle_only = False
    
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--hours="):
                recent_hours = int(arg.split("=")[1])
            elif arg.startswith("--gpu="):
                device_id = int(arg.split("=")[1])
            elif arg == "--throttle":
                throttle_only = True
            elif arg in ["-h", "--help"]:
                print("Usage: python view_thermal_log.py [options]")
                print("\nOptions:")
                print("  --hours=N      Show only events from last N hours")
                print("  --gpu=N        Show only events for GPU N")
                print("  --throttle     Show only throttling events (hide normal temps)")
                print("\nExamples:")
                print("  python view_thermal_log.py                    # Show all events")
                print("  python view_thermal_log.py --hours=2          # Last 2 hours")
                print("  python view_thermal_log.py --gpu=0            # GPU 0 only")
                print("  python view_thermal_log.py --throttle         # Throttle events only")
                print("  python view_thermal_log.py --hours=24 --gpu=1 --throttle  # Combined filters")
                sys.exit(0)
    
    view_thermal_log(recent_hours=recent_hours, device_id=device_id, show_throttle_only=throttle_only)
