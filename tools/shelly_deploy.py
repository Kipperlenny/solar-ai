"""Upload a Shelly script with its settings from config.toml and (re)start it.

Usage: python tools/shelly_deploy.py <pool|boiler>

The block between "// CONFIG-START" and "// CONFIG-END" in the script is
replaced with the [pool] / [boiler] section of config.toml. Host, script id
and password come from .env (SHELLY_<DEVICE>_HOST, _SCRIPT_ID, _USER,
_PASSWORD). If the script id does not exist on the device yet, it is created.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CONFIG, ROOT  # noqa: E402

SCRIPTS = {
    "pool": ("shelly/pool_pump_solar.js", "Pool Solar"),
    "boiler": ("shelly/boiler_solar.js", "Boiler Solar"),
}
CHUNK = 1024


def render(path, cfg):
    code = (ROOT / path).read_text(encoding="utf-8")
    block = "// CONFIG-START\nlet CFG = " + json.dumps(cfg, indent=2) + ";\n// CONFIG-END"
    code, n = re.subn(r"// CONFIG-START.*?// CONFIG-END", lambda _: block, code, flags=re.S)
    if n != 1:
        sys.exit(f"{path}: expected exactly one CONFIG-START/CONFIG-END block")
    return code


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SCRIPTS:
        sys.exit(__doc__)
    device = sys.argv[1]
    path, name = SCRIPTS[device]
    env = device.upper()
    host = os.environ[f"SHELLY_{env}_HOST"]
    auth = HTTPDigestAuth(os.getenv(f"SHELLY_{env}_USER", "admin"), os.environ[f"SHELLY_{env}_PASSWORD"])
    script_id = int(os.environ[f"SHELLY_{env}_SCRIPT_ID"])
    code = render(path, CONFIG[device])

    def rpc(method, **params):
        r = requests.post(f"http://{host}/rpc/{method}", json=params, auth=auth, timeout=10)
        r.raise_for_status()
        return r.json()

    existing = {s["id"] for s in rpc("Script.List")["scripts"]}
    if script_id not in existing:
        new_id = rpc("Script.Create", name=name)["id"]
        if new_id != script_id:
            sys.exit(f"Created script id {new_id}, but .env says {script_id} - fix SHELLY_{env}_SCRIPT_ID")
    else:
        rpc("Script.Stop", id=script_id)

    for i in range(0, len(code), CHUNK):
        rpc("Script.PutCode", id=script_id, code=code[i:i + CHUNK], append=i > 0)
    rpc("Script.SetConfig", id=script_id, config={"name": name, "enable": True})
    rpc("Script.Start", id=script_id)
    print(rpc("Script.GetStatus", id=script_id))


if __name__ == "__main__":
    main()
