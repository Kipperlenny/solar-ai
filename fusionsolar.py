"""FusionSolar cloud: 5-minute history (PV, consumption, grid meter) and wallbox power.

Usage: python fusionsolar.py      (solar_hub.py also runs it every few hours)

Appends every complete day since the last one in logs/fusionsolar.csv, from the
plant's grid connection on. Read-only: uses the web portal login via the
fusion_solar_py library (audited 2026-09-28, v0.1.2; its active_power_control
writes to the SDongle and must never be called).

.env: FUSION_SOLAR_USER, FUSION_SOLAR_PASSWORD, FUSION_SOLAR_CLOUD (portal URL
containing the plant id "NE=..."), FUSION_SOLAR_SUBDOMAIN (data host, e.g.
uni005eu5 - the portal redirects there after login).
"""

import csv
import logging
import os
import re
import time
from datetime import date, datetime, timedelta

from config import ROOT

CSV_FILE = ROOT / "logs" / "fusionsolar.csv"
FIELDS = ["timestamp", "pv_kw", "load_kw", "grid_kw"]  # grid_kw: + import, - export
WALLBOX_CSV = ROOT / "logs" / "wallbox.csv"
INVERTER_CSV = ROOT / "logs" / "inverter.csv"
INVERTER_MOC_TYPE = "20822"
# Inverter live signals: id -> (key, unit)
INVERTER_SIGNALS = {10018: "active_kw", 10019: "reactive_kvar", 10020: "power_factor",
                    10008: "grid_v", 10014: "grid_a", 10023: "temp_c", 10025: "status"}
CHARGER_MOC_TYPE = "60080"      # "Charging Pile" in the device list
SIGNAL_ENERGY_CHARGED = 10008   # kWh counter, updated by the cloud about every 2 minutes

log = logging.getLogger("solar_hub")


def _client():
    from fusion_solar_py.client import FusionSolarClient

    return FusionSolarClient(os.environ["FUSION_SOLAR_USER"], os.environ["FUSION_SOLAR_PASSWORD"],
                             huawei_subdomain=os.environ["FUSION_SOLAR_SUBDOMAIN"])


def _find_device(client, moc_type):
    """dn of the first device of a type in the plant, or None."""
    url = (f"https://{os.environ['FUSION_SOLAR_SUBDOMAIN']}.fusionsolar.huawei.com"
           "/rest/neteco/web/config/device/v1/device-list")
    r = client._session.get(url, params={"conditionParams.parentDn": client._company_id,
                                         "conditionParams.mocTypes": moc_type})
    r.raise_for_status()
    devices = r.json()["data"]
    return devices[0]["dn"] if devices else None


def _signals(client, dn):
    """{signal id: value} of a device's live data."""
    out = {}
    for group in client.get_real_time_data(dn)["data"]:
        for s in group.get("signals", []) if isinstance(group, dict) else []:
            out[s["id"]] = s.get("value", s.get("realValue"))
    return out


class Inverter:
    """Live inverter values from the cloud (updated about every 5 minutes): temperature,
    grid voltage, reactive power and status - to document the overheating and grid voltage."""

    def __init__(self):
        self.dn = None
        self.values = {}
        self.ts = None

    def poll(self, client):
        if self.dn is None:
            self.dn = _find_device(client, INVERTER_MOC_TYPE)
        sig = _signals(client, self.dn)
        values = {key: sig.get(sid) for sid, key in INVERTER_SIGNALS.items()}
        if values == self.values:
            return
        self.values, self.ts = values, datetime.now()
        new_file = not INVERTER_CSV.exists()
        with INVERTER_CSV.open("a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["timestamp", *INVERTER_SIGNALS.values()])
            w.writerow([self.ts.isoformat(timespec="seconds"), *values.values()])


class Wallbox:
    """Charging power of the Huawei wallbox, from its energy counter in the cloud.

    The wallbox can't be read locally and the cloud has no power value for it,
    so power is the average between two counter updates (about 2 minutes).
    """

    def __init__(self):
        self.client = None
        self.dn = None
        self.kwh = self.ts = None
        self.power_w = None

    def _find(self):
        return _find_device(self.client, CHARGER_MOC_TYPE)

    def poll(self):
        """Read the counter. Returns True when it has a new value."""
        if self.client is None:
            self.client = _client()
            self.dn = self._find()
        if self.dn is None:
            return False
        kwh = ts = None
        for group in self.client.get_real_time_data(self.dn)["data"]:
            for s in group.get("signals", []) if isinstance(group, dict) else []:
                if s["id"] == SIGNAL_ENERGY_CHARGED:
                    kwh, ts = float(s.get("realValue", s.get("value"))), s["latestTime"]
        if ts is None or ts == self.ts:
            if self.ts and time.time() - self.ts > 600:
                self.power_w = 0  # counter unchanged for 10 min: not charging
            return False
        if self.ts is not None:
            self.power_w = round((kwh - self.kwh) * 3.6e6 / (ts - self.ts))
        self.kwh, self.ts = kwh, ts
        new_file = not WALLBOX_CSV.exists()
        with WALLBOX_CSV.open("a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["timestamp", "total_kwh", "power_w"])
            w.writerow([datetime.fromtimestamp(ts).isoformat(), kwh, "" if self.power_w is None else self.power_w])
        return True


def _last_day():
    """Last day in the CSV, or None."""
    if not CSV_FILE.exists():
        return None
    with CSV_FILE.open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 200))
        last = f.read().decode().strip().split("\n")[-1]
    return None if last.startswith("timestamp") else date.fromisoformat(last[:10])


def _value(v):
    return "" if v in ("--", "", None) else v


def sync():
    """Fetch all complete days that are missing. Returns the number of days added."""
    if not os.getenv("FUSION_SOLAR_USER"):
        return 0
    last = _last_day()
    if last is not None and last >= date.today() - timedelta(days=1):
        return 0
    client = _client()
    plant = re.search(r"NE=\d+", os.environ["FUSION_SOLAR_CLOUD"]).group(0)
    if last is None:
        station = client.get_station_list()[0]
        last = date.fromisoformat(station["gridConnectedTime"][:10]) - timedelta(days=1)

    new_file = not CSV_FILE.exists()
    added = 0
    with CSV_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(FIELDS)
        day = last + timedelta(days=1)
        while day < date.today():
            midnight = int(datetime.combine(day, datetime.min.time()).timestamp() * 1000)
            s = client.get_plant_stats(plant, midnight)
            for i, ts in enumerate(s["xAxis"]):
                row = [_value(s[k][i]) for k in ("productPower", "usePower", "meterActivePower")]
                if any(row):
                    w.writerow([ts, *row])
            f.flush()
            added += 1
            day += timedelta(days=1)
            time.sleep(1)  # be gentle with the portal
    log.info("FusionSolar: %d day(s) added up to %s", added, day - timedelta(days=1))
    return added


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync()
