"""Solar hub: feeds PV data from a Huawei SDongle to Shelly devices.

Once a minute it reads PV input and house load from the SDongle (read-only,
Modbus function code 03) and pushes them to the Shelly scripts for the pool
pump and the boiler, which decide on their own. If this hub stops, both fall
back to safe behaviour by themselves.

It also drives a Shelly Color Bulb as a power indicator (see Indicator).

Settings: config.toml. Hosts and passwords: .env. Every minute a row goes to
logs/hub.csv.
"""

import csv
import logging
import os
import threading
import time
from datetime import datetime

import requests
from pymodbus.client import ModbusTcpClient
from requests.auth import HTTPDigestAuth

from config import CONFIG, ROOT
from tariff import level, period, price

HUB = CONFIG["hub"]
BULB = CONFIG["bulb"]

REG_PV_AND_LOAD = 37498  # 37498 total input power, 37500 load power: U32 W each

LOG_DIR = ROOT / "logs"
CSV_FILE = LOG_DIR / "hub.csv"

log = logging.getLogger("solar_hub")


class Shelly:
    """A Shelly Gen2+/Gen3 script endpoint configured via SHELLY_<NAME>_* in .env."""

    def __init__(self, name):
        self.name = name
        self.host = os.getenv(f"SHELLY_{name}_HOST")
        self.script_id = os.getenv(f"SHELLY_{name}_SCRIPT_ID")
        password = os.getenv(f"SHELLY_{name}_PASSWORD")
        self.auth = HTTPDigestAuth(os.getenv(f"SHELLY_{name}_USER", "admin"), password) if password else None

    def push(self, endpoint, **params):
        if not self.host:
            return None
        url = f"http://{self.host}/script/{self.script_id}/{endpoint}"
        try:
            r = requests.get(url, params=params, auth=self.auth, timeout=5)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("%s push failed: %s", self.name, e)
            return None


class Bulb:
    """Shelly Color Bulb (Gen1 HTTP API), basic auth optional."""

    def __init__(self):
        self.host = os.getenv("SHELLY_BULB_HOST")
        password = os.getenv("SHELLY_BULB_PASSWORD")
        self.auth = (os.getenv("SHELLY_BULB_USER", "admin"), password) if password else None

    def apply(self, light):
        """Set the light if the bulb is powered and on. Returns True if changed.

        light is ('white', temp, brightness) or ('color', red, green, blue, gain).
        """
        if not self.host:
            return False
        try:
            cur = requests.get(f"http://{self.host}/light/0", auth=self.auth, timeout=1.5).json()
        except (requests.RequestException, ValueError):
            return False  # switched off at the wall
        if not cur.get("ison"):
            return False  # turned off on purpose, leave it
        mode, values = light[0], light[1:]
        keys = ("temp", "brightness") if mode == "white" else ("red", "green", "blue", "gain")
        if cur.get("mode") == mode and tuple(cur.get(k) for k in keys) == values:
            return False
        params = {"mode": mode, **dict(zip(keys, values))}
        if mode == "color":
            params["white"] = 0  # the bulb can't mix white into color anyway
        requests.get(f"http://{self.host}/light/0", params=params, auth=self.auth, timeout=3)
        return True


class Indicator:
    """Derives the bulb state from PV, load and tariff with hysteresis.

    States: surplus, cheap, mid, expensive_consumed, expensive, unknown.
    """

    def __init__(self):
        self.dark = True
        self.surplus = False
        self.state = "unknown"

    def update(self, pv, load, now):
        if pv is None or load is None:
            self.state = "unknown"
            return
        export = pv - load
        if self.dark and pv >= BULB["bright_above_pv_w"]:
            self.dark = False
        elif not self.dark and pv < BULB["dark_below_pv_w"]:
            self.dark = True
        if not self.surplus and export >= BULB["surplus_on_export_w"]:
            self.surplus = True
        elif self.surplus and export < BULB["surplus_off_export_w"]:
            self.surplus = False

        lvl = level(period(now))
        if self.surplus:
            self.state = "surplus"
        elif lvl != "expensive":
            self.state = lvl
        elif pv >= BULB["consumed_above_pv_w"] and export < BULB["consumed_below_export_w"]:
            self.state = "expensive_consumed"
        else:
            self.state = "expensive"

    def light(self):
        if self.dark:
            return ("white", *BULB["dark_whites"][self.state])
        return ("color", *BULB["day_colors"][self.state])


class Hub:
    def __init__(self):
        self.sdongle = os.getenv("SDONGLE_HOST")
        self.client = ModbusTcpClient(self.sdongle, port=int(os.getenv("SDONGLE_PORT", "502")), timeout=5)
        self.pool = Shelly("POOL")
        self.boiler = Shelly("BOILER")
        self.bulb = Bulb()
        self.indicator = Indicator()
        self.lock = threading.Lock()
        self.data_ts = 0

    def read_dongle(self):
        """Return (pv_w, load_w) or (None, None)."""
        try:
            if not self.client.connected and not self.client.connect():
                log.warning("SDongle %s not reachable", self.sdongle)
                return None, None
            rr = self.client.read_holding_registers(REG_PV_AND_LOAD, count=4, device_id=HUB["sdongle_unit"])
            if rr.isError():
                raise IOError(rr)
            regs = rr.registers
            return (regs[0] << 16) | regs[1], (regs[2] << 16) | regs[3]
        except Exception as e:  # pymodbus raises various exception types
            log.warning("SDongle read failed: %s", e)
            self.client.close()
            return None, None

    def tick(self):
        pv, load = self.read_dongle()
        pool = boiler = None
        if pv is not None:
            pool = self.pool.push("pv", w=pv)
            boiler = self.boiler.push("data", pv=pv, load=load)
            self.data_ts = time.monotonic()
        now = datetime.now()
        with self.lock:
            self.indicator.update(pv, load, now)
            state, dark = self.indicator.state, self.indicator.dark
        log.info("PV %s W, load %s W, bulb %s%s, pool %s, boiler %s",
                 pv, load, state, " (dark)" if dark else "", pool, boiler)
        p = period(now)
        append_csv([
            now.isoformat(timespec="seconds"), pv, load, p, price(p), state, dark,
            pool and pool.get("sunOk"), pool and pool.get("pumpOn"),
            boiler and boiler.get("mode"), boiler and boiler.get("on"),
        ])

    def bulb_loop(self):
        while True:
            try:
                with self.lock:
                    if time.monotonic() - self.data_ts > 3 * HUB["interval_sec"]:
                        self.indicator.state = "unknown"
                    light = self.indicator.light()
                if self.bulb.apply(light):
                    log.info("Bulb set to %s", light)
            except Exception:
                log.exception("Bulb update failed")
            time.sleep(BULB["interval_sec"])

    def run(self):
        bulb_thread = threading.Thread(target=self.bulb_loop, daemon=True)
        while True:
            started = time.monotonic()
            try:
                self.tick()
            except Exception:
                log.exception("Tick failed")
            if not bulb_thread.is_alive():
                bulb_thread.start()  # after the first tick, so the bulb gets a real state
            time.sleep(max(0, HUB["interval_sec"] - (time.monotonic() - started)))


def append_csv(row):
    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "pv_w", "load_w", "period", "price_eur_kwh", "bulb_state", "dark",
                        "pool_sun_ok", "pool_pump_on", "boiler_mode", "boiler_on"])
        w.writerow(["" if v is None else v for v in row])


def main():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "hub.log"), logging.StreamHandler()],
    )
    if not os.getenv("SDONGLE_HOST"):
        raise SystemExit("SDONGLE_HOST missing - copy .env.example to .env and fill it in")
    log.info("Solar hub started")
    Hub().run()


if __name__ == "__main__":
    main()
