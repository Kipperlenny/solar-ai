"""Test QuickMiner power limit API directly"""
import requests
import json
from solar_mining_api import QuickMinerAPI

qm = QuickMinerAPI()

# Get device UUID
devices = qm.get_devices()
if not devices:
    print("No devices found!")
    exit(1)

device = devices[0]
device_id = device.get("device_id")
name = device.get("name")

# Get UUID
uuid = qm._get_device_uuid(device_id)
print(f"GPU {device_id}: {name}")
print(f"UUID: {uuid}")

if not uuid:
    print("Failed to get UUID!")
    exit(1)

# Try API call
headers = {"Authorization": qm.auth_token} if qm.auth_token else {}
params = {"device": uuid, "limit": 85}

print(f"\nAPI Request:")
print(f"  URL: {qm.base_url}/action/setpowerlimit")
print(f"  Params: {params}")
print(f"  Headers: {headers}")

response = requests.get(
    f"{qm.base_url}/action/setpowerlimit",
    params=params,
    headers=headers,
    timeout=5
)

print(f"\nAPI Response:")
print(f"  Status: {response.status_code}")
print(f"  Content: {response.text}")

if response.status_code == 200:
    result = response.json()
    print(f"  JSON: {json.dumps(result, indent=2)}")
    
    if result.get("error") is None:
        print(f"\n✅ Success!")
    else:
        print(f"\n❌ Error: {result.get('error')}")
else:
    print(f"\n❌ HTTP Error: {response.status_code}")
