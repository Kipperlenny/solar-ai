"""Logs shop prices of batteries, panels and inverters once a week to logs/prices.csv.

Usage: python prices.py      (solar_hub.py runs it when the last check is older than [prices] interval_days)

The products are listed in config.toml [prices]; each price is converted to a
price per unit (kWh of battery, kWp of panels, or piece) so the simulation can
use the latest median. Only shops whose robots.txt allows it; one request per
product per week. Installation labour can't be scraped - that stays an estimate
in [simulation] until there is a quote.
"""

import csv
import json
import logging
import re
import statistics
import subprocess
import time
from datetime import date, datetime

import requests

from config import CONFIG, ROOT

CSV_FILE = ROOT / "logs" / "prices.csv"
FUEL_CSV = ROOT / "logs" / "fuel.csv"
# Official daily prices of every filling station in Spain (Ministerio de Industria), per province
FUEL_API = ("https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/"
            "EstacionesTerrestres/FiltroProvincia/{province:02d}")
HEADERS = {"User-Agent": "Mozilla/5.0 (solar-ai price logger, personal use, weekly)"}

log = logging.getLogger("solar_hub")


def extract_price(html):
    """First product price in a shop page: JSON-LD offers, meta tags or embedded "price" data."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]):
            offers = item.get("offers") if isinstance(item, dict) and item.get("@type") == "Product" else None
            offers = offers[0] if isinstance(offers, list) else offers
            if offers and offers.get("price"):
                return float(offers["price"])
    m = (re.search(r'(?:product:price:amount|itemprop="price")[^>]*content="([\d.]+)"', html)
         or re.search(r'"price":\s*"?([\d.]+)', html))
    return float(m.group(1)) if m and float(m.group(1)) > 0 else None


def last_check():
    if not CSV_FILE.exists():
        return None
    with CSV_FILE.open() as f:
        rows = list(csv.DictReader(f))
    return date.fromisoformat(rows[-1]["date"]) if rows else None


def check():
    """Fetch all configured products and append their prices. Returns the number of prices logged."""
    items = CONFIG["prices"]["items"]
    new_file = not CSV_FILE.exists()
    logged = 0
    with CSV_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "key", "name", "shop", "price_eur", "per", "size", "price_per_unit"])
        for item in items:
            try:
                r = requests.get(item["url"], headers=HEADERS, timeout=30)
                r.raise_for_status()
                price = extract_price(r.text)
            except requests.RequestException as e:
                log.warning("Price check %s failed: %s", item["name"], e)
                price = None
            if price:
                shop = re.sub(r"^www\.", "", item["url"].split("/")[2])
                w.writerow([date.today().isoformat(), item["key"], item["name"], shop, price,
                            item["per"], item["size"], round(price / item["size"], 2)])
                logged += 1
            time.sleep(2)
    log.info("Prices: %d of %d products logged", logged, len(items))
    return logged


def check_fuel():
    """Log today's median diesel and petrol 95 prices in [fuel] municipality. Returns True if logged."""
    fuel = CONFIG.get("fuel", {})
    if not fuel.get("province"):
        return False
    # curl: Python's TLS handshake with this server is reset, Windows' curl works
    out = subprocess.run(["curl", "-s", "-m", "60", "-H", "Accept: application/json",
                          FUEL_API.format(province=fuel["province"])], capture_output=True, timeout=90)
    data = json.loads(out.stdout.decode("utf-8-sig"))
    stations = [s for s in data["ListaEESSPrecio"]
                if not fuel.get("municipality") or s["Municipio"] == fuel["municipality"]]

    def prices(field):
        return [float(s[field].replace(",", ".")) for s in stations if s[field]]

    diesel, petrol = prices("Precio Gasoleo A"), prices("Precio Gasolina 95 E5")
    if not diesel or not petrol:
        return False
    new_file = not FUEL_CSV.exists()
    with FUEL_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "area", "stations", "diesel_median", "diesel_min", "petrol95_median", "petrol95_min"])
        w.writerow([date.today().isoformat(), fuel.get("municipality") or f"province {fuel['province']}",
                    len(stations), statistics.median(diesel), min(diesel), statistics.median(petrol), min(petrol)])
    log.info("Fuel: diesel %.3f, petrol 95 %.3f EUR/l (median of %d stations)",
             statistics.median(diesel), statistics.median(petrol), len(stations))
    return True


def latest_fuel():
    """(diesel median, petrol 95 median, date) of the last fuel check, or None."""
    if not FUEL_CSV.exists():
        return None
    with FUEL_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return (float(rows[-1]["diesel_median"]), float(rows[-1]["petrol95_median"]), rows[-1]["date"]) if rows else None


def due():
    last = last_check()
    return last is None or (date.today() - last).days >= CONFIG["prices"]["interval_days"]


def latest():
    """{key: median price per unit of the latest check of each product}, plus the history per key."""
    if not CSV_FILE.exists():
        return {}, {}
    with CSV_FILE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    newest = {}
    history = {}
    for r in rows:
        newest[(r["key"], r["name"], r["shop"])] = r
        history.setdefault(r["key"], {}).setdefault(r["date"], []).append(float(r["price_per_unit"]))
    per_key = {}
    for (key, _, _), r in newest.items():
        per_key.setdefault(key, []).append(float(r["price_per_unit"]))
    medians = {k: statistics.median(v) for k, v in per_key.items()}
    trend = {k: {d: round(statistics.median(v), 2) for d, v in sorted(h.items())} for k, h in history.items()}
    return medians, {"trend": trend, "products": list(newest.values()), "checked": rows[-1]["date"]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    check()
    check_fuel()
    print(json.dumps(latest()[0], indent=1), datetime.now())
