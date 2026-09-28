"""Mitsubishi air conditioner via MELCloud: state and power, read-only for now.

Uses pymelcloud (audited 2026-09-28, v2.11.0; it only talks to app.melcloud.com
and only changes the unit via Device/SetAta, which this module never calls).
.env: MELCLOUD_USER, MELCLOUD_PASSWORD. Every poll appends a row to logs/ac.csv;
power is the average from the unit's energy counter between two changes.
"""

import asyncio
import csv
import logging
import os
import time
from datetime import datetime

from config import ROOT

CSV_FILE = ROOT / "logs" / "ac.csv"

log = logging.getLogger("solar_hub")


class AirCon:
    def __init__(self):
        self.token = None
        self.state = {}          # latest values for the dashboard
        self._energy = None      # (kWh, monotonic time) of the last counter change

    async def _read(self):
        import aiohttp
        import pymelcloud

        async with aiohttp.ClientSession() as session:
            if self.token is None:
                self.token = await pymelcloud.login(os.environ["MELCLOUD_USER"], os.environ["MELCLOUD_PASSWORD"],
                                                    session)
            devices = await pymelcloud.get_devices(self.token, session)
            units = devices.get(pymelcloud.DEVICE_TYPE_ATA, [])
            if not units:
                return None
            unit = units[0]
            await unit.update()
            return {
                "name": unit.name,
                "on": unit.power,
                "mode": unit.operation_mode,
                "room_c": unit.room_temperature,
                "target_c": unit.target_temperature,
                "fan": unit.fan_speed,
                "energy_kwh": unit.total_energy_consumed,
            }

    def poll(self):
        """Read the unit once. Returns True on success."""
        if not os.getenv("MELCLOUD_USER"):
            return False
        try:
            values = asyncio.run(self._read())
        except Exception:
            self.token = None  # log in again next time
            raise
        if values is None:
            return False
        now = time.monotonic()
        energy = values["energy_kwh"]
        power_w = self.state.get("power_w")
        if energy is not None:
            if self._energy is None:
                self._energy = (energy, now)
            elif energy != self._energy[0]:
                power_w = round((energy - self._energy[0]) * 3.6e6 / (now - self._energy[1]))
                self._energy = (energy, now)
        if not values["on"]:
            power_w = 0
        self.state = {**values, "power_w": power_w, "updated": datetime.now().strftime("%H:%M")}
        new_file = not CSV_FILE.exists()
        with CSV_FILE.open("a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["timestamp", "on", "mode", "room_c", "target_c", "fan", "energy_kwh", "power_w"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), values["on"], values["mode"], values["room_c"],
                        values["target_c"], values["fan"], energy, "" if power_w is None else power_w])
        return True
