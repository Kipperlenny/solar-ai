#!/usr/bin/env python3
"""Manually start mining on QuickMiner via traditional excavator commands."""

import requests

AUTH_TOKEN = "8E0095E025BA0C4A85B7741A"
BASE_URL = "http://localhost:18000"

print("Attempting to start mining via excavator commands...")
print()

# The traditional way to start mining with excavator is:
# 1. subscribe to pool
# 2. algorithm.add
# 3. worker.add

# But QuickMiner uses HTTP REST, not JSON-RPC
# Let's try calling the endpoints directly

headers = {"Authorization": AUTH_TOKEN}

# Try different start methods
print("Method 1: Trying /quickstart with minimal params...")
try:
    r = requests.get(f"{BASE_URL}/quickstart", headers=headers, timeout=5)
    print(f"Response: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("Method 2: Checking if there's a /start endpoint...")
try:
    r = requests.get(f"{BASE_URL}/start", headers=headers, timeout=5)
    print(f"Response: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("Method 3: Checking available endpoints by trying /help...")
try:
    r = requests.get(f"{BASE_URL}/help", headers=headers, timeout=5)
    print(f"Response: {r.status_code} - {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("="*60)
print("RECOMMENDATION:")
print("="*60)
print()
print("The current QuickMiner (v0.6.13.0 with excavator 1.7.1d)")
print("doesn't support the /quickstart endpoint properly.")
print()
print("Options:")
print("1. Upgrade to QuickMiner v0.7.8.0 RC (already downloaded)")
print("2. Start mining manually in QuickMiner GUI")
print("3. Use our script to STOP mining (that works via /quickstop)")
print("   and let QuickMiner auto-start when needed")
print()
