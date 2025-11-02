"""Apply power limits with detailed output"""
from solar_mining_api import QuickMinerAPI, GPU_POWER_LIMIT_TDP
import traceback

qm = QuickMinerAPI()

print(f"Applying {GPU_POWER_LIMIT_TDP}% TDP power limits...\n")

# Get devices first
devices = qm.get_devices()
if not devices:
    print("❌ No devices found!")
    exit(1)

print(f"Found {len(devices)} devices:")
for device in devices:
    print(f"  • GPU {device.get('device_id')}: {device.get('name')}")

print()

# Try to apply power limit to each device
for device in devices:
    device_id = device.get("device_id")
    name = device.get("name", "Unknown")
    
    print(f"GPU {device_id} ({name}):")
    try:
        success = qm.set_power_limit(device_id, tdp_percent=GPU_POWER_LIMIT_TDP)
        if success:
            print(f"  ✅ Power limit applied successfully")
        else:
            print(f"  ❌ Power limit failed (set_power_limit returned False)")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
    print()

# Verify
print("\nVerifying power limits:")
devices = qm.get_devices()
for device in devices:
    device_id = device.get('device_id')
    name = device.get('name')
    power_limit = device.get('gpu_power_limit_current', 0)
    power_default = device.get('gpu_power_limit_default', 0)
    
    if power_default > 0:
        current_tdp = int((power_limit / power_default) * 100)
        print(f"  GPU {device_id}: {power_limit:.0f}W ({current_tdp}% TDP)")
    else:
        print(f"  GPU {device_id}: {power_limit:.0f}W (unable to calculate TDP%)")
