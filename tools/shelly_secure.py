"""Secure a new Shelly Gen2+/Gen3 plug with the passwords from .env.

Usage: python tools/shelly_secure.py <pool|boiler>

Sets the web/API password (SHELLY_<DEVICE>_PASSWORD, digest auth, user admin)
and protects the setup access point with WPA2 (SHELLY_<DEVICE>_AP_PASSWORD).
The access point stays enabled, so the plug is still reachable if WiFi fails.
Run it once while the device has no password yet.
"""

import hashlib
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402,F401  (loads .env)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    env = sys.argv[1].upper()
    host = os.environ[f"SHELLY_{env}_HOST"]
    password = os.environ[f"SHELLY_{env}_PASSWORD"]
    ap_password = os.getenv(f"SHELLY_{env}_AP_PASSWORD")

    info = requests.get(f"http://{host}/shelly", timeout=5).json()
    if info.get("auth_en"):
        sys.exit(f"{info['id']} already has a password")

    def rpc(method, **params):
        r = requests.post(f"http://{host}/rpc/{method}", json=params, timeout=10)
        r.raise_for_status()
        return r.json()

    if ap_password:
        rpc("WiFi.SetConfig", config={"ap": {"enable": True, "is_open": False, "pass": ap_password}})
        print("Setup access point protected with WPA2 (takes effect after a reboot)")

    realm = info["id"]
    ha1 = hashlib.sha256(f"admin:{realm}:{password}".encode()).hexdigest()
    rpc("Shelly.SetAuth", user="admin", realm=realm, ha1=ha1)
    print(f"{realm}: password set, user admin")


if __name__ == "__main__":
    main()
