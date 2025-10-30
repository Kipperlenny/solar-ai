#!/usr/bin/env python3
"""Quick test to check if we can read solar power."""

import asyncio
from huawei_solar import create_tcp_bridge
import os
from dotenv import load_dotenv

load_dotenv()

INVERTER_HOST = os.getenv("INVERTER_HOST", "192.168.18.206")
INVERTER_PORT = int(os.getenv("INVERTER_PORT", "6607"))

async def test_inverter():
    print(f"Connecting to inverter at {INVERTER_HOST}:{INVERTER_PORT}...")
    try:
        bridge = await create_tcp_bridge(host=INVERTER_HOST, port=INVERTER_PORT)
        print("✅ Connected!")
        
        # Read solar power (using client.get as per solar_core.py)
        input_power = await bridge.client.get("input_power")
        print(f"📊 Current Solar Power: {input_power.value}W")
        
        await bridge.close()
        return input_power.value
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    power = asyncio.run(test_inverter())
    if power is not None:
        print(f"\n✅ Inverter communication working!")
        print(f"Current production: {power}W")
        
        # Determine what should happen
        if power >= 800:
            print(f"🟢 Solar power >= 800W → Should START mining")
        elif power < 150:
            print(f"🔴 Solar power < 150W → Should STOP mining")
        else:
            print(f"🟡 Solar power between 150-800W → Keep current state")
    else:
        print(f"\n❌ Could not connect to inverter")
