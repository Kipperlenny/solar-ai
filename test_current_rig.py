"""Test showing only the current MANAGED rig"""
from solar_mining_api import NiceHashAPI
import os
from dotenv import load_dotenv

load_dotenv()

nh = NiceHashAPI(os.getenv('NICEHASH_WALLET'))
print(f"Authenticated: {nh.authenticated}")
print(f"Worker name from wallet: {os.getenv('NICEHASH_WALLET').split('.')[-1]}\n")

# Show ALL rigs (old behavior)
print("📊 ALL RIGS (including old sessions):")
all_rigs = nh.get_rig_stats()
if all_rigs:
    for rig in all_rigs:
        print(f"   • {rig['name']} ({rig['type']}) - {rig['status']}")
else:
    print("   No rigs found")

print()

# Show only MANAGED rigs
print("🖥️  MANAGED RIGS ONLY (QuickMiner):")
managed_rigs = nh.get_rig_stats(active_only=True)
if managed_rigs:
    for rig in managed_rigs:
        print(f"   • {rig['name']} ({rig['type']}) - {rig['status']}")
else:
    print("   No managed rigs found")

print()

# Show current rig (MANAGED + matching worker name)
print("✅ CURRENT RIG (this script's rig):")
current_rig = nh.get_current_rig()
if current_rig:
    print(f"   Name: {current_rig['name']}")
    print(f"   Type: {current_rig['type']}")
    print(f"   Status: {current_rig['status']}")
    print(f"   Software: {current_rig['software']}")
    print(f"   Unpaid: {nh.format_btc(current_rig['unpaid_amount'])}")
    if current_rig['algorithms']:
        print(f"   Algorithms:")
        for algo in current_rig['algorithms']:
            print(f"      • {algo['name']}: {algo['hashrate']:.2f} {algo['unit']} ({nh.format_btc(algo['unpaid'])} unpaid)")
else:
    print("   ℹ️  No current rig found")
    print("   💡 This is normal when mining is stopped")
    print("   💡 The rig will appear when you start mining")
