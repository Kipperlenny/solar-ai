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
import time
from datetime import date, datetime

import requests

from config import CONFIG, ROOT

CSV_FILE = ROOT / "logs" / "prices.csv"
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
    print(json.dumps(latest()[0], indent=1), datetime.now())
