"""Check if GPU power limits are actually applied"""
import os
from dotenv import load_dotenv
from solar_mining_api import QuickMinerAPI, GPU_POWER_LIMIT_TDP

load_dotenv()

print("=" * 60)
print("GPU POWER LIMIT CHECK")
print("=" * 60)

print(f"\n📋 Configuration:")
print(f"   Target TDP: {GPU_POWER_LIMIT_TDP}%")

# Create QuickMiner API instance
try:
    qm = QuickMinerAPI()
    print(f"   QuickMiner API: Connected ✅")
except Exception as e:
    print(f"   QuickMiner API: Failed ❌ ({e})")
    exit(1)

# Get current device status
print(f"\n🖥️  Current GPU Status:")
try:
    devices = qm.get_devices()
    if not devices:
        print("   ⚠️  No devices found!")
        exit(1)
    
    for device in devices:
        device_id = device.get('device_id')
        name = device.get('name', 'Unknown')
        power_limit = device.get('gpu_power_limit_current', 0)
        power_default = device.get('gpu_power_limit_default', 0)
        power_usage = device.get('gpu_power_usage', 0)
        temp = device.get('gpu_temp', 0)
        
        # Calculate current TDP percentage
        if power_default > 0:
            current_tdp = int((power_limit / power_default) * 100)
        else:
            current_tdp = 100
        
        print(f"\n   GPU {device_id}: {name}")
        print(f"      Current Power Limit: {power_limit:.0f}W ({current_tdp}% TDP)")
        print(f"      Default Power Limit: {power_default:.0f}W (100% TDP)")
        print(f"      Actual Power Usage:  {power_usage:.1f}W")
        print(f"      Temperature:         {temp}°C")
        
        # Check if matches target
        if abs(current_tdp - GPU_POWER_LIMIT_TDP) <= 2:  # Allow 2% tolerance
            print(f"      Status: ✅ CORRECT ({current_tdp}% ≈ {GPU_POWER_LIMIT_TDP}%)")
        else:
            print(f"      Status: ❌ WRONG! Expected {GPU_POWER_LIMIT_TDP}%, got {current_tdp}%")
            print(f"      ⚠️  Power limit is NOT applied!")

except Exception as e:
    print(f"   Error reading devices: {e}")
    import traceback
    traceback.print_exc()

print(f"\n💡 Actions:")
print(f"   If power limits are WRONG:")
print(f"   1. Stop mining")
print(f"   2. Run: python -c \"from solar_mining_api import QuickMinerAPI; qm = QuickMinerAPI(); qm.apply_safe_power_limits({GPU_POWER_LIMIT_TDP})\"")
print(f"   3. Start mining again")
print(f"\n   Or add to .env:")
print(f"   GPU_POWER_LIMIT_TDP={GPU_POWER_LIMIT_TDP}")

print("\n" + "=" * 60)
