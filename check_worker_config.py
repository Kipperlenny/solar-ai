"""Check QuickMiner config vs .env worker name"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Read .env settings
env_wallet = os.getenv('NICEHASH_WALLET', '')
env_worker = env_wallet.split('.')[-1] if '.' in env_wallet else 'NO_WORKER_NAME'
quickminer_path = os.getenv('QUICKMINER_PATH', 'H:\\miner\\NiceHashQuickMiner.exe')

print("=" * 60)
print("WORKER NAME CONFIGURATION CHECK")
print("=" * 60)

print(f"\n📝 .env Configuration:")
print(f"   NICEHASH_WALLET: {env_wallet}")
print(f"   Worker Name:     {env_worker}")

# Try to read QuickMiner config
config_path = Path(quickminer_path).parent / "nhqm.conf"
print(f"\n📂 QuickMiner Config Path:")
print(f"   {config_path}")

if config_path.exists():
    print(f"   ✅ File exists!")
    
    try:
        with open(config_path, 'r') as f:
            qm_config = json.load(f)
        
        # Extract relevant settings from authorization section
        auth = qm_config.get('authorization', {})
        qm_btc_address = auth.get('BTC', 'NOT_SET')
        qm_worker = auth.get('workerName', 'NOT_SET')
        qm_unique_id = auth.get('uniqueID', 'NOT_SET')
        qm_region = auth.get('serviceLocation', -1)
        qm_auto_start = qm_config.get('bMiningAutoStart', False)
        qm_is_mining = qm_config.get('bIsMining', False)
        
        print(f"\n🖥️  QuickMiner Configuration:")
        print(f"   BTC Address:     {qm_btc_address}")
        print(f"   Worker Name:     {qm_worker}")
        print(f"   Unique ID:       {qm_unique_id}")
        print(f"   Service Region:  {qm_region}")
        print(f"   Auto-Start:      {qm_auto_start}")
        print(f"   Currently Mining: {qm_is_mining}")
        
        # Compare
        print(f"\n🔍 COMPARISON:")
        
        # Extract wallet address from .env (before the dot)
        env_address = env_wallet.split('.')[0] if '.' in env_wallet else env_wallet
        
        if env_address == qm_btc_address:
            print(f"   ✅ BTC Address matches!")
        else:
            print(f"   ❌ BTC Address MISMATCH!")
            print(f"      .env:       {env_address}")
            print(f"      QuickMiner: {qm_btc_address}")
        
        if env_worker == qm_worker:
            print(f"   ✅ Worker Name matches: '{env_worker}'")
        else:
            print(f"   ❌ Worker Name MISMATCH!")
            print(f"      .env:       '{env_worker}'")
            print(f"      QuickMiner: '{qm_worker}'")
            print(f"\n   ⚠️  THIS IS THE PROBLEM!")
            print(f"   → QuickMiner will create rig: '{qm_worker}'")
            print(f"   → Your script expects rig: '{env_worker}'")
        
        print(f"\n💡 RECOMMENDATION:")
        if env_worker != qm_worker:
            print(f"   Option 1: Update .env to match QuickMiner")
            print(f"      NICEHASH_WALLET={env_address}.{qm_worker}")
            print(f"\n   Option 2: Update QuickMiner config to match .env")
            print(f"      1. Open QuickMiner")
            print(f"      2. Go to Settings")
            print(f"      3. Change Worker Name to: {env_worker}")
            print(f"      4. Save and restart QuickMiner")
            print(f"\n   Option 3: Use unique name for this solar rig")
            print(f"      Recommended: NICEHASH_WALLET={env_address}.solar-miner")
            print(f"      Then update QuickMiner to use 'solar-miner' as worker name")
        else:
            print(f"   ✅ Configuration is correct!")
            print(f"   Both use worker name: '{env_worker}'")
        
    except Exception as e:
        print(f"   ❌ Error reading config: {e}")
else:
    print(f"   ❌ File NOT found!")
    print(f"\n   Possible locations:")
    print(f"   - {config_path}")
    print(f"   - H:\\miner\\nhqm.conf")
    print(f"   - C:\\Program Files\\NiceHashQuickMiner\\nhqm.conf")

print("\n" + "=" * 60)
