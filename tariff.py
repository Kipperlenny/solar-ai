"""Electricity tariff periods from config.toml [tariff]."""

from datetime import datetime

from config import CONFIG

_T = CONFIG["tariff"]
_PRICES = _T["prices_eur_kwh"]
_BY_PRICE = sorted(_PRICES, key=_PRICES.get)


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


_WEEKDAY = [(_minutes(a), _minutes(b), p) for a, b, p in _T["weekday_periods"]]


def period(dt: datetime) -> str:
    """Return the tariff period (e.g. 'P1') for a local time."""
    if dt.weekday() >= 5 or dt.strftime("%m-%d") in _T["holidays"]:
        return _T["weekend_period"]
    m = dt.hour * 60 + dt.minute
    for start, end, p in _WEEKDAY:
        if start <= m < end:
            return p
    raise ValueError(f"No tariff period configured for {dt:%H:%M}")


def price(p: str) -> float:
    return _PRICES[p]


def level(p: str) -> str:
    """'cheap' for the cheapest period, 'expensive' for the most expensive, else 'mid'."""
    if p == _BY_PRICE[0]:
        return "cheap"
    if p == _BY_PRICE[-1]:
        return "expensive"
    return "mid"
