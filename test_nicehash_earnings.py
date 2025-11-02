"""
Test NiceHash Earnings API - Diagnostic Tool
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get wallet address
NICEHASH_WALLET = os.getenv("NICEHASH_WALLET", "YOUR_WALLET_ADDRESS.worker_name")
NICEHASH_API_URL = "https://api2.nicehash.com/main/api/v2/mining/external"

print("=" * 80)
print("NICEHASH EARNINGS API DIAGNOSTIC")
print("=" * 80)
print()

# Check wallet configuration
print("1. WALLET CONFIGURATION CHECK")
print("-" * 80)
print(f"Raw wallet string: {NICEHASH_WALLET}")

if "YOUR_WALLET_ADDRESS" in NICEHASH_WALLET:
    print("❌ ERROR: Wallet address not configured!")
    print("   Please set NICEHASH_WALLET in your environment or .env file")
    print()
    print("Example:")
    print('   NICEHASH_WALLET=34HKWdzLxWBduUfJE9JxaFhoXnfC6gmePG.solar_rig')
    print()
    sys.exit(1)

# Extract wallet address (remove worker name)
wallet_address = NICEHASH_WALLET.split('.')[0]
worker_name = NICEHASH_WALLET.split('.')[1] if '.' in NICEHASH_WALLET else None

print(f"✓ Wallet address: {wallet_address[:20]}...{wallet_address[-10:]}")
if worker_name:
    print(f"✓ Worker name: {worker_name}")
print()

# Test API connection
print("2. NICEHASH API CONNECTION TEST")
print("-" * 80)

url = f"{NICEHASH_API_URL}/{wallet_address}"
print(f"API URL: {url}")
print()

try:
    print("Sending request to NiceHash API...")
    response = requests.get(url, timeout=10)
    
    print(f"Response Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ SUCCESS - API responded!")
        print()
        
        data = response.json()
        
        # Display all available data
        print("3. EARNINGS DATA")
        print("-" * 80)
        
        if 'unpaidAmount' in data:
            unpaid = float(data.get('unpaidAmount', 0))
            total_balance = float(data.get('totalBalance', 0))
            total_paid = float(data.get('totalPaidAmount', 0))
            
            # Format BTC amounts
            def format_btc(btc_amount):
                if btc_amount >= 0.01:
                    return f"{btc_amount:.8f} BTC"
                else:
                    sats = btc_amount * 100_000_000
                    return f"{sats:.0f} sats ({btc_amount:.8f} BTC)"
            
            print(f"Unpaid Balance:  {format_btc(unpaid)}")
            print(f"Total Balance:   {format_btc(total_balance)}")
            print(f"Total Paid:      {format_btc(total_paid)}")
            print()
            
            # Check if mining is active
            if unpaid > 0:
                print("✅ You have unpaid earnings - mining is working!")
            else:
                print("ℹ️  No unpaid earnings yet")
                print("   This is normal if you just started mining")
                print("   Wait 5-10 minutes for NiceHash to register activity")
        else:
            print("⚠️  WARNING: Response doesn't contain expected earnings data")
            print()
            print("Raw response:")
            print(data)
        
        print()
        print("4. ADDITIONAL INFO")
        print("-" * 80)
        
        # Check for other useful fields
        if 'totalProfitability' in data:
            print(f"Total Profitability: {data['totalProfitability']}")
        
        if 'totalBalanceEUR' in data:
            print(f"Balance (EUR): €{data['totalBalanceEUR']:.2f}")
        
        if 'totalBalanceUSD' in data:
            print(f"Balance (USD): ${data['totalBalanceUSD']:.2f}")
        
    elif response.status_code == 404:
        print("⚠️  NOT FOUND (404)")
        print()
        print("This means:")
        print("  • No mining activity detected yet for this wallet")
        print("  • OR wallet address is incorrect")
        print()
        print("What to do:")
        print("  1. Verify your wallet address is correct")
        print("  2. Check if mining is actually running in QuickMiner")
        print("  3. Wait 5-10 minutes after starting mining")
        print("  4. Check NiceHash website directly")
        
    else:
        print(f"❌ ERROR - Unexpected status code: {response.status_code}")
        print()
        print("Response text:")
        print(response.text[:500])
        
except requests.exceptions.Timeout:
    print("❌ TIMEOUT - NiceHash API took too long to respond")
    print("   Check your internet connection")
    
except requests.exceptions.ConnectionError as e:
    print("❌ CONNECTION ERROR - Cannot reach NiceHash API")
    print(f"   Error: {e}")
    print("   Check your internet connection")
    
except Exception as e:
    print(f"❌ UNEXPECTED ERROR: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print()

# Recommendations
print("RECOMMENDATIONS:")
print()
print("If earnings show on NiceHash website but not in script:")
print("  • Wait 5-10 minutes after starting mining")
print("  • Earnings update every 10 minutes (20 iterations)")
print("  • Check logs/errors.log for API errors")
print()
print("If API returns 404:")
print("  • Verify NICEHASH_WALLET in .env file")
print("  • Ensure QuickMiner is actually mining")
print("  • Wait at least 10 minutes after starting mining")
print()
