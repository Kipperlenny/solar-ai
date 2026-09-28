"""Reads the electricity bills (PDF) in bills/ into logs/bills.json (Naturgy's layout).

Usage: python bills.py      (solar_hub.py also runs it every few hours)

Per bill: contract (last 4 digits only), tariff, period, kWh per period and
price, exported kWh and credit, "Batería Virtual" charged or used, contracted
power and total. The PDFs contain personal data: bills/ and logs/ are not in git.
"""

import json
import re
from pathlib import Path

from config import ROOT

BILLS_DIR = ROOT / "bills"
OUT_FILE = ROOT / "logs" / "bills.json"


def _num(s):
    """Spanish number: '1.075' -> 1075, '0,180200' -> 0.1802."""
    return float(s.replace(".", "").replace(",", "."))


def _date(s):
    d, m, y = s.split("/")
    return f"{y}-{m}-{d}"


def parse(path):
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() for page in PdfReader(path).pages[:2])
    num = r"(-?[\d.]+(?:,\d+)?)"

    def find(pattern, conv=_num):
        m = re.search(pattern, text)
        return conv(m.group(1)) if m else None

    period = re.search(r"Período electricidad del (\d\d/\d\d/\d{4}) al (\d\d/\d\d/\d{4})", text)
    bill = {
        "file": path.name,
        "contract": (find(r"Contrato:\s*(\d+)", str) or "")[-4:],
        "tariff": find(r"Concepto Cálculo Importe\n(.+)", str),
        "from": _date(period.group(1)) if period else None,
        "to": _date(period.group(2)) if period else None,
        "kwh": {}, "price": {},
        "export_kwh": None, "export_eur": None,
        "virtual_battery_in_eur": find(r"Importe a cargar en la Batería Virtual\s+" + num),
        "virtual_battery_used_eur": find(r"Uso Batería Virtual\s+" + num),
        "power_kw": find(r"Término potencia P1\s+" + num + r" kW"),
        "total_eur": find(r"Total a pagar\s+" + num),
        "max_demand": find(r"potencias máximas demandadas en el último año han sido (.+?)\.\n", str),
    }
    for name, p in (("Punta", "P1"), ("Llano", "P2"), ("Valle", "P3")):
        m = re.search(rf"Consumo electricidad {name}\s+{num} kWh x {num}", text)
        if m:
            bill["kwh"][p], bill["price"][p] = _num(m.group(1)), _num(m.group(2))
    m = re.search(rf"Consumo electricidad\s+{num} kWh x {num}", text)
    if m and not bill["kwh"]:
        bill["kwh"]["all"], bill["price"]["all"] = _num(m.group(1)), _num(m.group(2))
    # Export credit, one line per price (e.g. a tariff change within the month)
    block = re.search(r"Valoración excedentes(.*?)Subtotal Compensación", text, re.S)
    if block:
        lines = re.findall(rf"{num} kWh x {num} €/kWh\s+{num} €", block.group(1))
        bill["export_kwh"] = sum(abs(_num(k)) for k, _, _ in lines)
        bill["export_eur"] = round(sum(_num(e) for _, _, e in lines), 2)
        bill["export_price"] = sorted({_num(p) for _, p, _ in lines})
    return bill


def measured(bill, history):
    """FusionSolar kWh bought and exported in the bill's period (inclusive)."""
    buy = export = 0.0
    for ts, grid in history:
        if bill["from"] <= ts[:10] <= bill["to"]:
            if grid > 0:
                buy += grid / 12
            else:
                export -= grid / 12
    return round(buy), round(export)


def with_measurements():
    """Bills plus the FusionSolar measurement of the same period (for the dashboard)."""
    import csv

    if not OUT_FILE.exists():
        return []
    bills = json.loads(OUT_FILE.read_text())
    with (ROOT / "logs" / "fusionsolar.csv").open() as f:
        history = [(r["timestamp"], float(r["grid_kw"])) for r in csv.DictReader(f) if r["grid_kw"]]
    home = {b["contract"] for b in bills if b["export_kwh"] is not None}  # the contract with the panels
    for b in bills:
        b["home"] = b["contract"] in home
        if b["home"] and b["from"]:
            b["measured_buy_kwh"], b["measured_export_kwh"] = measured(b, history)
    return bills


def meter_calibration(bills):
    """Utility meter kWh / FusionSolar kWh over all home bills with export (about 0.93)."""
    billed = measured_sum = 0.0
    for b in bills:
        if b.get("home") and b["export_kwh"] is not None:
            billed += sum(b["kwh"].values()) + b["export_kwh"]
            measured_sum += b["measured_buy_kwh"] + b["measured_export_kwh"]
    return round(billed / measured_sum, 3) if measured_sum else 1.0


def scan():
    """Parse all PDFs in bills/ (cached by file name). Returns the number of new bills."""
    known = json.loads(OUT_FILE.read_text()) if OUT_FILE.exists() else []
    done = {b["file"] for b in known}
    new = [parse(p) for p in sorted(BILLS_DIR.glob("*.pdf")) if p.name not in done]
    if new:
        bills = sorted(known + new, key=lambda b: (b["contract"], b["from"] or ""))
        OUT_FILE.write_text(json.dumps(bills, indent=1, ensure_ascii=False))
    return len(new)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{scan()} new bill(s)")
    for b in json.loads(OUT_FILE.read_text()):
        print(b["contract"], b["from"], b["to"], b["kwh"], "export", b["export_kwh"], b["export_eur"],
              "VB+", b["virtual_battery_in_eur"], "VB-", b["virtual_battery_used_eur"], "total", b["total_eur"])
