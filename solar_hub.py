"""Solar hub: feeds PV data from a Huawei SDongle to Shelly devices.

Once a minute it reads PV input and house load from the SDongle (read-only,
Modbus function code 03) and pushes them to the Shelly scripts for the pool
pump and the boiler, which decide on their own. If this hub stops, both fall
back to safe behaviour by themselves.

It also drives a Shelly Color Bulb as a power indicator (see Indicator).

Settings: config.toml. Hosts and passwords: .env. Every minute a row goes to
logs/hub.csv; every few hours the 5-minute history from the FusionSolar cloud
is appended to logs/fusionsolar.csv (fusionsolar.py), new bills in bills/ are read (bills.py). A local dashboard (dashboard.py) shows the current state, the
reasons behind it and the log.
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

import aircon
import bills
import prices
import dashboard
from tools import simulate
import fusionsolar
import sun
from config import CONFIG, ROOT
from tariff import level, period, price

HUB = CONFIG["hub"]
BULB = CONFIG["bulb"]

REG_PV_AND_LOAD = 37498  # 37498 total input power, 37500 load power: U32 W each

LOG_DIR = ROOT / "logs"
CSV_FILE = LOG_DIR / "hub.csv"
DEVICES_CSV = LOG_DIR / "devices.csv"  # per minute: boiler power (hot water use), pool, wallbox, inverter

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
        self.note = "not checked yet"

    def apply(self, light):
        """Set the light if the bulb is powered and on. Returns True if changed.

        light is ('white', temp, brightness) or ('color', red, green, blue, gain).
        """
        if not self.host:
            self.note = "SHELLY_BULB_HOST not configured"
            return False
        try:
            cur = requests.get(f"http://{self.host}/light/0", auth=self.auth, timeout=1.5).json()
        except (requests.RequestException, ValueError):
            self.note = "unreachable (switched off at the wall?)"
            return False
        if not cur.get("ison"):
            self.note = "switched off in the app, left alone"
            return False
        self.note = "on"
        mode, values = light[0], light[1:]
        keys = ("temp", "brightness") if mode == "white" else ("red", "green", "blue", "gain")
        if cur.get("mode") == mode and tuple(cur.get(k) for k in keys) == values:
            return False
        params = {"mode": mode, **dict(zip(keys, values))}
        if mode == "color":
            params["white"] = 0  # the bulb can't mix white into color anyway
        requests.get(f"http://{self.host}/light/0", params=params, auth=self.auth, timeout=3)
        return True


def flow(export):
    return f"exporting {export} W" if export >= 0 else f"importing {-export} W"


class Indicator:
    """Derives the bulb state from PV, load and tariff with hysteresis.

    States: surplus, cheap, mid, export, expensive_consumed, expensive, unknown.
    reason explains the current state in words.
    """

    def __init__(self):
        self.dark = True
        self.surplus = False
        self.exporting = False
        self.state = "unknown"
        self.reason = "no data yet"

    def update(self, pv, load, now):
        if pv is None or load is None:
            self.state, self.reason = "unknown", "no data from the SDongle"
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
        if not self.exporting and export >= BULB["export_on_w"]:
            self.exporting = True
        elif self.exporting and export < BULB["export_off_w"]:
            self.exporting = False

        p = period(now)
        lvl = level(p)
        tariff = f"{lvl} tariff {p} ({price(p):.3f} EUR/kWh)"
        if self.surplus:
            self.state = "surplus"
            self.reason = (f"{flow(export)}: surplus (starts at {BULB['surplus_on_export_w']} W export, "
                           f"ends below {BULB['surplus_off_export_w']} W) - switch on big loads")
        elif lvl != "expensive":
            self.state = lvl
            self.reason = (f"{tariff}, {flow(export)} - not a surplus "
                           f"(needs {BULB['surplus_on_export_w']} W export)")
        elif self.exporting:
            self.state = "export"
            self.reason = (f"{tariff}, but {flow(export)} (starts at {BULB['export_on_w']} W, "
                           f"ends below {BULB['export_off_w']} W) - small loads OK")
        elif (pv >= BULB["consumed_above_pv_w"]
              and -BULB["consumed_max_import_w"] < export < BULB["consumed_below_export_w"]):
            self.state = "expensive_consumed"
            self.reason = (f"{tariff}; PV {pv} W is there but a load takes it, {flow(export)} "
                           f"(grid near zero: under {BULB['consumed_below_export_w']} W export "
                           f"and {BULB['consumed_max_import_w']} W import)")
        else:
            self.state = "expensive"
            spare = (f"too little to spare (yellow from {BULB['export_on_w']} W)" if export >= 0
                     else "buying from the grid")
            self.reason = f"{tariff}, PV {pv} W, {flow(export)} - {spare}"

    def light(self):
        if self.dark:
            return ("white", *BULB["dark_whites"][self.state])
        return ("color", *BULB["day_colors"][self.state])


def clock(unixtime):
    return datetime.fromtimestamp(unixtime).strftime("%a %H:%M") if unixtime else "never"


def boiler_reason(s):
    """Explain the boiler script's decision from its /status answer."""
    if not s:
        return "no answer from the boiler plug"
    cfg, st, t, w = s["cfg"], s["state"], s["now"], s.get("apower")
    mode = st["mode"]
    if mode == "night":
        r = f"night ({cfg['nightStart']}-{cfg['nightEnd']}): off"
    elif mode == "evening":
        r = f"from {cfg['forceStart']} always on, so the tank is hot for the evening"
    elif mode == "legionella":
        r = f"not full for over {cfg['maxNotFullSec'] // 3600} h: heating for legionella protection"
    elif mode == "fallback":
        r = (f"no hub data for {cfg['maxDataAgeSec'] // 60} min: "
             f"{'on' if st['on'] else 'off'} (on from {cfg['fallbackStart']})")
    elif mode == "no_time":
        r = "plug has no clock time: on to be safe"
    elif mode == "surplus":
        imp = (st["loadW"] or 0) - (st["pvW"] or 0)
        settle = cfg["settleSec"] - (t - st["onSince"])
        if st["on"] and settle > 0:
            r = (f"surplus try: switched on because PV reached {cfg['tryPvW']} W, "
                 f"other loads get {settle} s more to regulate down")
        elif st["on"]:
            r = (f"heating from surplus: {flow(-imp)}, allowed up to {cfg['maxImportW']} W import "
                 f"(readings over the limit: {st['overCount']}/{cfg['badReadings']})")
        elif t < st["nextTryTs"]:
            r = (f"last surplus try failed (import over {cfg['maxImportW']} W {cfg['badReadings']}x in a row), "
                 f"next try from {clock(st['nextTryTs'])} if PV >= {cfg['tryPvW']} W")
        else:
            r = f"waiting for surplus: PV {st['pvW']} W, needs {cfg['tryPvW']} W to try"
    else:
        r = f"mode {mode}"
    if st["on"] and w is not None and w < cfg["fullBelowW"] and t - st["onSince"] >= 60:
        r += f"; but the tank is full (draws {w:.0f} W, thermostat off), so grid import doesn't count"
    return r


def pool_reason(s):
    """Explain the pool script's decision from its /status answer."""
    if not s:
        return "no answer from the pool plug"
    cfg, st = s["cfg"], s["state"]
    if s["now"] - st["lastPvTs"] > cfg["maxPvAgeSec"]:
        return f"no PV data from the hub for over {cfg['maxPvAgeSec'] // 60} min: pump off"
    el = st["elevation"]
    if st["sunOk"]:
        phase = "pumping" if st["pumpOn"] else "pause, the collector heats up"
        return (f"cycle {cfg['onMin']} min on / {cfg['offMin']} min off, now {phase}: "
                f"strong sun, PV {st['pvW']} W (stops below {cfg['offW']} W), "
                f"sun {el}° high (needs {cfg['minElevation']}°)")
    if el < cfg["minElevation"]:
        return f"sun only {el}° high, the flat collector needs {cfg['minElevation']}°: pump off"
    return f"sun too weak for the collector: PV {st['pvW']} W, cycling starts at {cfg['onW']} W"


class Hub:
    def __init__(self):
        self.sdongle = os.getenv("SDONGLE_HOST")
        self.client = ModbusTcpClient(self.sdongle, port=int(os.getenv("SDONGLE_PORT", "502")), timeout=5)
        self.pool = Shelly("POOL")
        self.boiler = Shelly("BOILER")
        self.bulb = Bulb()
        self.indicator = Indicator()
        self.lock = threading.Lock()
        self.dongle_lock = threading.Lock()  # the Modbus client is shared by tick() and fast_loop()
        self.data_ts = 0
        self.started = datetime.now().isoformat(timespec="seconds")
        self.snap = {}
        self.wallbox = fusionsolar.Wallbox()
        self.inverter = fusionsolar.Inverter()
        self.aircon = aircon.AirCon()

    def read_dongle(self):
        """Return (pv_w, load_w) or (None, None)."""
        with self.dongle_lock:
            return self._read_dongle()

    def _read_dongle(self):
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
        now = datetime.now()
        if pv is not None:
            pool = self.pool.push("pv", w=pv, el=sun.position(now)[1])
            boiler = self.boiler.push("data", pv=pv, load=load)
            self.data_ts = time.monotonic()
        pool_status, boiler_status = self.pool.push("status"), self.boiler.push("status")
        p = period(now)
        with self.lock:
            prev = self.snap
            self.indicator.update(pv, load, now)
            state, dark, reason = self.indicator.state, self.indicator.dark, self.indicator.reason
            self.snap = {
                "time": now.isoformat(timespec="seconds"),
                "started": self.started,
                "pv_w": pv, "load_w": load, "export_w": None if pv is None else pv - load,
                "period": p, "price_eur_kwh": price(p), "level": level(p),
                "bulb": {"state": state, "reason": reason, "dark": dark},
                "boiler": {
                    "on": boiler_status and boiler_status["state"]["on"],
                    "mode": boiler_status and boiler_status["state"]["mode"],
                    "power_w": boiler_status and boiler_status.get("apower"),
                    "last_full": boiler_status and clock(boiler_status["state"]["lastFullTs"]),
                    "reason": boiler_reason(boiler_status),
                },
                "pool": {
                    "on": pool_status and pool_status["state"]["pumpOn"],
                    "sun_ok": pool_status and pool_status["state"]["sunOk"],
                    "reason": pool_reason(pool_status),
                },
            }
        log.info("PV %s W, load %s W, bulb %s%s, pool %s, boiler %s",
                 pv, load, state, " (dark)" if dark else "", pool, boiler)
        if prev.get("bulb", {}).get("state") != state:
            log.info("Bulb state -> %s: %s", state, reason)
        for name in ("boiler", "pool"):
            cur = self.snap[name]
            if cur["on"] is not None and prev.get(name, {}).get("on") != cur["on"]:
                log.info("%s %s: %s", name.capitalize(), "on" if cur["on"] else "off", cur["reason"])
        append_devices_csv([
            now.isoformat(timespec="seconds"), self.snap["boiler"]["on"], self.snap["boiler"]["mode"],
            self.snap["boiler"]["power_w"], self.snap["pool"]["on"], self.wallbox.power_w,
            self.inverter.values.get("temp_c"), self.inverter.values.get("grid_v"),
        ])
        append_csv([
            now.isoformat(timespec="seconds"), pv, load, p, price(p), state, dark,
            pool and pool.get("sunOk"), pool and pool.get("pumpOn"),
            boiler and boiler.get("mode"), boiler and boiler.get("on"),
        ])

    def snapshot(self):
        """Current state for the dashboard."""
        with self.lock:
            snap = dict(self.snap)
            snap["bulb"] = {**snap.get("bulb", {}), "state": self.indicator.state,
                            "reason": self.indicator.reason, "light": self.indicator.light(),
                            "device": self.bulb.note}
        wb = self.wallbox
        snap["wallbox"] = {"power_w": wb.power_w, "total_kwh": wb.kwh,
                           "updated": wb.ts and datetime.fromtimestamp(wb.ts).strftime("%H:%M:%S"),
                           "found": wb.dn is not None}
        snap["aircon"] = dict(self.aircon.state)
        snap["inverter"] = {**self.inverter.values,
                            "updated": self.inverter.ts and self.inverter.ts.strftime("%H:%M:%S")}
        return snap

    def bulb_loop(self):
        while True:
            try:
                with self.lock:
                    if time.monotonic() - self.data_ts > 3 * HUB["interval_sec"]:
                        self.indicator.state = "unknown"
                        self.indicator.reason = f"no fresh SDongle data for {3 * HUB['interval_sec']} s"
                    state, light = self.indicator.state, self.indicator.light()
                if self.bulb.apply(light):
                    log.info("Bulb set to %s %s", state, light)
            except Exception:
                log.exception("Bulb update failed")
            time.sleep(BULB["interval_sec"])

    def cloud_loop(self):
        """Wallbox power and inverter values from the FusionSolar cloud, every minute."""
        from fusion_solar_py.exceptions import FusionSolarException

        charging = None
        failures = 0
        backoff_min = (1, 2, 5, 10, 30)  # never hammer the account with logins
        while True:
            try:
                self.wallbox.poll()
                self.inverter.poll(self.wallbox.client)
                failures = 0
                now = self.wallbox.power_w is not None and self.wallbox.power_w >= 500
                if self.wallbox.power_w is not None and now != charging:
                    log.info("Wallbox %s: %s W", "charging" if now else "not charging", self.wallbox.power_w)
                    charging = now
            except (FusionSolarException, requests.RequestException, ValueError) as e:
                # the portal session expires about every 30 min; a fresh login fixes it
                wait = backoff_min[min(failures, len(backoff_min) - 1)]
                log.warning("FusionSolar session expired or cloud not reachable (%s), logging in again in %d min",
                            type(e).__name__, wait)
                self.wallbox.client = None
                failures += 1
                time.sleep(wait * 60)
                continue
            except Exception:
                log.exception("FusionSolar live poll failed")
                self.wallbox.client = None
            time.sleep(60)

    def ac_loop(self):
        """Air conditioner state every 5 minutes (MELCloud asks for no more than once a minute)."""
        was_on = None
        failures = 0
        while True:
            try:
                if self.aircon.poll():
                    failures = 0
                    s = self.aircon.state
                    if s["on"] != was_on:
                        log.info("Air conditioner %s (switched by you): %s, room %s °C, target %s °C",
                                 "on" if s["on"] else "off", s["mode"], s["room_c"], s["target_c"])
                        was_on = s["on"]
            except Exception as e:
                failures += 1
                log.warning("MELCloud not reachable (%s: %s), trying again in %d min",
                            type(e).__name__, e, 5 * min(failures, 6))
                time.sleep(5 * 60 * (min(failures, 6) - 1))
            time.sleep(5 * 60)

    def fast_loop(self, every):
        """For tests: PV, load and grid every few seconds to logs/fast.csv ([hub] fast_log_sec)."""
        path = LOG_DIR / "fast.csv"
        while True:
            started = time.monotonic()
            pv, load = self.read_dongle()
            if pv is not None:
                new_file = not path.exists()
                with path.open("a", newline="") as f:
                    w = csv.writer(f)
                    if new_file:
                        w.writerow(["timestamp", "pv_w", "load_w", "grid_w", "wallbox_w"])
                    w.writerow([datetime.now().isoformat(timespec="seconds"), pv, load, load - pv,
                                "" if self.wallbox.power_w is None else self.wallbox.power_w])
            time.sleep(max(1, every - (time.monotonic() - started)))

    def history_loop(self):
        while True:
            try:
                new_bills = bills.scan()
                if prices.due():
                    new_bills += prices.check()  # new prices: recalculate too
                    try:
                        new_bills += prices.check_fuel()
                    except Exception:
                        log.exception("Fuel price check failed")
                if fusionsolar.sync() or new_bills or not simulate.OUT_FILE.exists():
                    simulate.run()
                    log.info("Investment simulation updated")
            except Exception:
                log.exception("FusionSolar sync or simulation failed")
            time.sleep(600)  # cheap: sync only logs in when a day is missing, bills are cached

    def run(self):
        bulb_thread = threading.Thread(target=self.bulb_loop, daemon=True)
        dashboard.serve(self, CONFIG["dashboard"]["port"], LOG_DIR / "hub.log", simulate.OUT_FILE)
        threading.Thread(target=self.history_loop, daemon=True).start()
        if HUB.get("fast_log_sec"):
            threading.Thread(target=self.fast_loop, args=(HUB["fast_log_sec"],), daemon=True).start()
        if os.getenv("FUSION_SOLAR_USER"):
            threading.Thread(target=self.cloud_loop, daemon=True).start()
        if os.getenv("MELCLOUD_USER"):
            threading.Thread(target=self.ac_loop, daemon=True).start()
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


def append_devices_csv(row):
    new_file = not DEVICES_CSV.exists()
    with DEVICES_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "boiler_on", "boiler_mode", "boiler_w", "pool_on", "wallbox_w",
                        "inverter_temp_c", "grid_v"])
        w.writerow(["" if v is None else v for v in row])


def main():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "hub.log", encoding="utf-8"), logging.StreamHandler()],
    )
    logging.getLogger("fusion_solar_py").setLevel(logging.CRITICAL)  # its expected session errors, see cloud_loop
    if not os.getenv("SDONGLE_HOST"):
        raise SystemExit("SDONGLE_HOST missing - copy .env.example to .env and fill it in")
    log.info("Solar hub started")
    Hub().run()


if __name__ == "__main__":
    main()
