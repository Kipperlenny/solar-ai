"""Quick test for NiceHash earnings display"""
from solar_mining_api import NiceHashAPI
import os
from dotenv import load_dotenv

load_dotenv()

nh = NiceHashAPI(os.getenv('NICEHASH_WALLET'))
print(f"Authenticated: {nh.authenticated}\n")

# Check raw rig data
rigs_raw = nh.get_mining_rigs()
if rigs_raw:
    print(f"Raw totalProfitability: {rigs_raw.get('totalProfitability')}")
    print(f"Type: {type(rigs_raw.get('totalProfitability'))}")
    print()

# Test earnings
earnings = nh.get_earnings_info()
if earnings:
    print("📊 EARNINGS:")
    print(f"   Unbezahlt:   {nh.format_btc(earnings['unpaid_btc'])}")
    print(f"   Verfügbar:   {nh.format_btc(earnings['available_btc'])}")
    print(f"   Total:       {nh.format_btc(earnings['total_balance_btc'])}")
    print(f"   Profit/Tag:  {nh.format_profitability(earnings['current_profitability'])} (raw: {earnings['current_profitability']})")
else:
    print("❌ No earnings data")

print()

# Test rig stats
rigs = nh.get_rig_stats()
if rigs:
    print(f"🖥️  RIGS ({len(rigs)}):")
    for rig in rigs:
        status_icon = "✅" if rig['status'] == "MINING" else "⏸️" if rig['status'] == "DISABLED" else "💤"
        print(f"\n   {status_icon} {rig['name']} ({rig['type']})")
        print(f"      Status: {rig['status']}")
        print(f"      Unbezahlt: {nh.format_btc(rig['unpaid_amount'])}")
        if rig['profitability'] > 0:
            print(f"      Profit: {nh.format_profitability(rig['profitability'])}")
        if rig['software']:
            print(f"      Software: {rig['software']}")
        
        if rig['algorithms']:
            print(f"      Algorithmen:")
            for algo in rig['algorithms']:
                print(f"         • {algo['name']}: {algo['hashrate']:.2f} {algo['unit']} ({nh.format_btc(algo['unpaid'])} unpaid)")
else:
    print("❌ No rigs data")
