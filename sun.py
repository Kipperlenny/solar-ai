"""Sun position from WEATHER_LATITUDE / WEATHER_LONGITUDE in .env (NOAA approximation, about 1°)."""

import os
from datetime import datetime, timezone
from math import acos, atan2, cos, degrees, pi, radians, sin, tan

import config  # noqa: F401 - loads .env

LAT = float(os.getenv("WEATHER_LATITUDE", "nan"))
LON = float(os.getenv("WEATHER_LONGITUDE", "nan"))


def position(when: datetime) -> tuple[float, float]:
    """Sun (azimuth, elevation) in degrees.

    Azimuth: 0 = north, 90 = east, 180 = south, 270 = west. Elevation: height
    above the horizon, negative at night.
    """
    t = when.astimezone(timezone.utc)
    hour = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * pi / 365 * (t.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * cos(g) - 0.032077 * sin(g)
                       - 0.014615 * cos(2 * g) - 0.040849 * sin(2 * g))
    decl = (0.006918 - 0.399912 * cos(g) + 0.070257 * sin(g) - 0.006758 * cos(2 * g)
            + 0.000907 * sin(2 * g) - 0.002697 * cos(3 * g) + 0.00148 * sin(3 * g))
    hour_angle = radians((hour * 60 + eqtime + 4 * LON) / 4 - 180)
    lat = radians(LAT)
    az = degrees(atan2(sin(hour_angle), cos(hour_angle) * sin(lat) - tan(decl) * cos(lat))) + 180
    cos_zenith = sin(lat) * sin(decl) + cos(lat) * cos(decl) * cos(hour_angle)
    elevation = 90 - degrees(acos(max(-1.0, min(1.0, cos_zenith))))
    return round(az % 360, 1), round(elevation, 1)
