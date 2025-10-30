#!/usr/bin/env python3
"""Quick test to verify QuickMiner API control works."""

from solar_mining_api import get_available_miner

print("="*60)
print("QuickMiner API Connection Test")
print("="*60)
print()

# Get miner instance
miner = get_available_miner()
print()

# Test 1: Get miner info
print("Test 1: Getting miner info...")
try:
    result = miner.send_command('info')
    print(f"✅ Connection successful!")
    print(f"   Version: {result.get('version')}")
    print(f"   Build: {result.get('build_number')}")
    print(f"   Uptime: {result.get('uptime')}s")
    print()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print()
    exit(1)

# Test 2: Get device list
print("Test 2: Getting device list...")
try:
    result = miner.send_command('device.list')
    devices = result.get('devices', [])
    print(f"✅ Found {len(devices)} devices:")
    for dev in devices:
        dev_id = dev.get('device_id')
        name = dev.get('name', 'Unknown')
        uuid = dev.get('uuid', 'N/A')
        print(f"   [{dev_id}] {name}")
        print(f"       UUID: {uuid}")
    print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

# Test 3: Check workers (mining status)
print("Test 3: Checking mining status...")
try:
    result = miner.send_command('worker.list')
    workers = result.get('workers', [])
    if workers:
        print(f"✅ Mining active with {len(workers)} workers:")
        for worker in workers:
            algo = worker.get('algorithms', [{}])[0]
            algo_name = algo.get('name', 'Unknown')
            speed = algo.get('speed', 0)
            print(f"   Algorithm: {algo_name}")
            print(f"   Speed: {speed:.2f} H/s")
    else:
        print(f"ℹ️  Mining is currently STOPPED")
    print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

print("="*60)
print("✅ API Test Complete!")
print("="*60)
print()
print("Next steps:")
print("1. Test starting mining with: worker.add")
print("2. Test stopping mining with: worker.free")
print("3. Run solar_core.py for automatic solar-based control")
print()
