"""
Test script for auto-update functionality
"""
import sys
import subprocess
from packaging import version
import pkg_resources

print("=" * 80)
print("AUTO-UPDATE TEST")
print("=" * 80)

# Test 1: Check Python executable
print(f"\n1. Python Executable:")
print(f"   sys.executable: {sys.executable}")
print(f"   Should be in .venv: {'✅' if '.venv' in sys.executable else '❌'}")

# Test 2: Check current huawei-solar version
print(f"\n2. Current huawei-solar version:")
try:
    current_version = pkg_resources.get_distribution('huawei-solar').version
    print(f"   Installed: {current_version}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Test pip upgrade command (dry-run)
print(f"\n3. Test pip upgrade command:")
result = subprocess.run(
    [sys.executable, '-m', 'pip', 'install', '--upgrade', '--dry-run', 'huawei-solar'],
    capture_output=True,
    text=True,
    timeout=30
)
print(f"   Exit code: {result.returncode}")
if result.returncode == 0:
    print(f"   ✅ Command works")
    if "Requirement already satisfied" in result.stdout:
        print(f"   Package is already up-to-date")
    else:
        print(f"   Update would be performed")
else:
    print(f"   ❌ Error: {result.stderr}")

# Test 4: Check Excavator process
print(f"\n4. Check for running Excavator:")
import psutil
excavator_running = False
try:
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'excavator' in proc.info['name'].lower():
            excavator_running = True
            print(f"   Found: {proc.info['name']}")
            break
    if not excavator_running:
        print(f"   No Excavator process found")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
