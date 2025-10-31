"""
Test script to apply GPU power limits via QuickMiner API.
"""
import requests
import logging

# Setup minimal logging
logging.basicConfig(level=logging.INFO)
error_logger = logging.getLogger('test')

QUICKMINER_API_HOST = "127.0.0.1"
QUICKMINER_API_PORT = 18000
AUTH_TOKEN = "8E0095E025BA0C4A85B7741A"

def get_device_uuid(device_id):
    """Get UUID for a device ID."""
    try:
        base_url = f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}"
        headers = {"Authorization": AUTH_TOKEN}
        response = requests.get(f"{base_url}/devices_cuda", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            devices = data.get("devices", [])
            device_id_str = str(device_id)
            for device in devices:
                if str(device.get("device_id", "")) == device_id_str:
                    return device.get("uuid")
        return None
    except Exception as e:
        error_logger.warning(f"Failed to get UUID: {e}")
        return None

def get_device_info(device_id):
    """Get detailed info for a specific device."""
    try:
        base_url = f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}"
        headers = {"Authorization": AUTH_TOKEN}
        response = requests.get(f"{base_url}/devices_cuda", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            devices = data.get("devices", [])
            device_id_str = str(device_id)
            for device in devices:
                if str(device.get("device_id", "")) == device_id_str:
                    return device
        return None
    except Exception as e:
        error_logger.warning(f"Failed to get device info: {e}")
        return None

def set_power_limit(device_id, tdp_percent):
    """Set GPU power limit to reduce stress."""
    try:
        uuid = get_device_uuid(device_id)
        if not uuid:
            print(f"  ✗ Could not find UUID for device {device_id}")
            return False
        
        base_url = f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}"
        headers = {"Authorization": AUTH_TOKEN}
        
        # Clamp TDP between 50-100%
        limit = max(50, min(100, tdp_percent))
        params = {"device": uuid, "limit": limit}
        
        response = requests.get(
            f"{base_url}/action/setpowerlimit",
            params=params,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("error") is None:
                print(f"  ✓ GPU {device_id} power limit set to {limit}% TDP")
                return True
            else:
                print(f"  ✗ Error: {result.get('error')}")
        else:
            print(f"  ✗ HTTP {response.status_code}: {response.text}")
        return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False

def apply_safe_power_limits(tdp_percent=85):
    """Apply conservative power limits to all GPUs."""
    print(f"\n🔋 Applying safe power limits ({tdp_percent}% TDP)...")
    
    # Get all devices
    try:
        base_url = f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}"
        headers = {"Authorization": AUTH_TOKEN}
        response = requests.get(f"{base_url}/devices_cuda", headers=headers, timeout=5)
        if response.status_code != 200:
            print(f"✗ Failed to get devices: HTTP {response.status_code}")
            return False
        
        data = response.json()
        devices = data.get("devices", [])
        success_count = 0
        
        for device in devices:
            device_id = device.get("device_id")
            device_name = device.get("name", "Unknown")
            current_tdp = device.get("gpu_tdp_current", 100)
            
            print(f"\nGPU {device_id}: {device_name}")
            print(f"  Current TDP: {current_tdp}%")
            
            if set_power_limit(device_id, tdp_percent=tdp_percent):
                success_count += 1
        
        print(f"\n✓ Power limits applied to {success_count}/{len(devices)} GPU(s)\n")
        return success_count > 0
        
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GPU Power Limit Test")
    print("=" * 60)
    
    # Show current state
    print("\n📊 Current GPU Power Status:")
    try:
        response = requests.get(
            f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}/devices_cuda",
            headers={"Authorization": AUTH_TOKEN},
            timeout=5
        )
        if response.status_code == 200:
            devices = response.json().get("devices", [])
            for d in devices:
                print(f"  GPU {d['device_id']}: {d['name']}")
                print(f"    Power: {d['gpu_power_usage']:.1f}W / {d['gpu_power_limit_current']:.0f}W ({d['gpu_tdp_current']}% TDP)")
        else:
            print(f"  Error getting devices: HTTP {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Apply 85% limit
    input("\nPress Enter to apply 85% TDP limit...")
    apply_safe_power_limits(tdp_percent=85)
    
    # Show new state
    print("\n📊 New GPU Power Status:")
    try:
        import time
        time.sleep(2)  # Wait for changes to take effect
        response = requests.get(
            f"http://{QUICKMINER_API_HOST}:{QUICKMINER_API_PORT}/devices_cuda",
            headers={"Authorization": AUTH_TOKEN},
            timeout=5
        )
        if response.status_code == 200:
            devices = response.json().get("devices", [])
            for d in devices:
                print(f"  GPU {d['device_id']}: {d['name']}")
                print(f"    Power: {d['gpu_power_usage']:.1f}W / {d['gpu_power_limit_current']:.0f}W ({d['gpu_tdp_current']}% TDP)")
        else:
            print(f"  Error getting devices: HTTP {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
