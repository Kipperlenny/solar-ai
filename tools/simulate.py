"""What would a battery, more panels or a cooler inverter have saved last year?

Usage: python tools/simulate.py

Replays the real 5-minute history in logs/fusionsolar.csv (PV, consumption) with
different setups and prices every kWh bought or exported with the tariff from
config.toml. Settings and assumed prices: [simulation] in config.toml.

With more than a year of history every calendar day is averaged over the
years it appears in, so the result is always one average year - more reliable
with every winter and summer logged - and not biased towards seasons seen twice.

Production of panels we don't have yet comes from PVGIS (EU JRC, hourly
2019-2023 averages, cached in logs/pvgis/), scaled per day with what the real
panels produced that day, so the real weather of each day is kept. The same
scaling gives the production the inverter cut off at its power limit.
"""

import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bills  # noqa: E402
import prices  # noqa: E402
import sun  # noqa: E402
from config import CONFIG, ROOT  # noqa: E402
from tariff import period, price  # noqa: E402

SIM = CONFIG["simulation"]
PVGIS_DIR = ROOT / "logs" / "pvgis"
OUT_FILE = ROOT / "logs" / "simulation.json"
STEP_H = 5 / 60


# --- PVGIS ------------------------------------------------------------------

def pvgis(tilt, aspect):
    """Average W per kWp by (month, day, UTC hour), aspect 0 = south, -90 = east, 90 = west."""
    PVGIS_DIR.mkdir(parents=True, exist_ok=True)
    cache = PVGIS_DIR / f"tilt{tilt}_aspect{aspect}.json"
    if not cache.exists():
        r = requests.get("https://re.jrc.ec.europa.eu/api/v5_3/seriescalc", timeout=120, params={
            "lat": round(sun.LAT, 2), "lon": round(sun.LON, 2), "peakpower": 1, "loss": 14,
            "angle": tilt, "aspect": aspect, "startyear": 2019, "endyear": 2023,
            "pvcalculation": 1, "outputformat": "json"})
        r.raise_for_status()
        sums, counts = defaultdict(float), defaultdict(int)
        for h in r.json()["outputs"]["hourly"]:
            t = h["time"]  # "20230101:0010", UTC
            key = f"{t[4:6]}{t[6:8]}{t[9:11]}"
            sums[key] += h["P"]
            counts[key] += 1
        cache.write_text(json.dumps({k: sums[k] / counts[k] for k in sums}))
    data = json.loads(cache.read_text())
    return lambda utc: data.get(f"{utc:%m%d%H}", 0.0) / 1000  # kW per kWp


# --- data ---------------------------------------------------------------------

def load_history():
    rows = []
    with (ROOT / "logs" / "fusionsolar.csv").open() as f:
        for r in csv.DictReader(f):
            if not r["pv_kw"] or not r["load_kw"]:
                continue
            local = datetime.fromisoformat(r["timestamp"])
            p = period(local)
            rows.append({"local": local, "utc": local.astimezone().utctimetuple(), "day": r["timestamp"][:10],
                         "pv": float(r["pv_kw"]), "load": float(r["load_kw"]), "period": p, "price": price(p)})
    for r in rows:
        u = r["utc"]
        r["utc"] = datetime(u.tm_year, u.tm_mon, u.tm_mday, u.tm_hour)
    return load_history_weights(rows)


def load_history_weights(rows):
    """Weight per row so that each calendar day counts once in the average year."""
    years_per_day = defaultdict(set)
    for r in rows:
        years_per_day[r["day"][5:]].add(r["day"][:4])
    for r in rows:
        r["w"] = 1 / len(years_per_day[r["day"][5:]])
    return rows


def day_caps(rows):
    """Highest PV per day; steps at that value (with 30 min or more of it) are clipped."""
    top = defaultdict(float)
    for r in rows:
        top[r["day"]] = max(top[r["day"]], r["pv"])
    n_top = defaultdict(int)
    for r in rows:
        if r["pv"] >= top[r["day"]] - 0.01:
            n_top[r["day"]] += 1
    return {d: top[d] for d in top if n_top[d] >= 6 and top[d] > 3.5}


def in_event(day, events):
    return next((e for e in events if e["from"] <= day <= e["to"]), None)


def suggest_events(rows, events):
    """Runs of 3+ days whose consumption is far from normal for that weekday and season,
    not yet covered by an event in config.toml - probably a vacation or visitors."""
    daily = defaultdict(float)
    for r in rows:
        daily[r["day"]] += r["load"] * STEP_H
    days = sorted(daily)
    empty = set()  # nearly nobody home: left out of the comparison, so neighbours don't look "high"
    for _ in range(2):
        flagged = []
        for d in days:
            dt = date.fromisoformat(d)
            # same weekday within +-5 weeks
            ref = [daily[x] for x in days if x != d and x not in empty and date.fromisoformat(x).weekday() == dt.weekday()
                   and abs((date.fromisoformat(x) - dt).days) <= 35]
            if len(ref) < 3 or in_event(d, events):
                continue
            typical = statistics.median(ref)
            if daily[d] < 0.5 * typical:
                flagged.append((d, "low", daily[d], typical))
            elif daily[d] > 1.8 * typical:
                flagged.append((d, "high", daily[d], typical))
        empty = {d for d, kind, _, _ in flagged if kind == "low"}
    runs = []
    for d, kind, kwh, typical in flagged:
        prev = runs[-1] if runs else None
        if prev and prev["kind"] == kind and (date.fromisoformat(d) - date.fromisoformat(prev["to"])).days <= 2:
            prev["to"] = d
            prev["kwh"] += kwh
            prev["typical"] += typical
            prev["days"] += 1
        else:
            runs.append({"from": d, "to": d, "kind": kind, "kwh": kwh, "typical": typical, "days": 1})
    return [{**r, "kwh": round(r["kwh"]), "typical": round(r["typical"]),
             "guess": "vacation / nobody home" if r["kind"] == "low" else "visitors or extra load"}
            for r in runs if r["days"] >= 3]


def fit_orientation(rows, clipped):
    """Pick the PVGIS orientation whose daily shape fits the unclipped real production best."""
    best = None
    for tilt in (10, 20, 30):
        for aspect in (-30, -15, 0, 15, 30):
            model = pvgis(tilt, aspect)
            err = 0.0
            by_day = defaultdict(lambda: [0.0, 0.0, []])
            for r in rows:
                if r["day"] in clipped:
                    continue
                m = model(r["utc"])
                d = by_day[r["day"]]
                d[0] += r["pv"]
                d[1] += m
                d[2].append((r["pv"], m))
            for real, mod, pts in by_day.values():
                if real < 20 or mod <= 0:  # only fairly sunny days
                    continue
                err += sum((p / real - m / mod) ** 2 for p, m in pts)
            if best is None or err < best[0]:
                best = (err, tilt, aspect)
    return best[1], best[2]


def weather_factors(rows, model, caps):
    """Per day: real kWh / modelled kWh for 1 kWp, from the unclipped steps (about the kWp in sunny weather)."""
    real, mod = defaultdict(float), defaultdict(float)
    for r in rows:
        cap = caps.get(r["day"])
        if cap is not None and r["pv"] >= cap - 0.01:
            continue
        real[r["day"]] += r["pv"]
        mod[r["day"]] += model(r["utc"])
    return {d: real[d] / mod[d] if mod[d] > 0.05 else 0.0 for d in real}


# --- simulation ---------------------------------------------------------------

def simulate(rows, pv_of, battery_kwh=0.0, dc_extra_of=None):
    """Import/export per period for PV pv_of(row) and an optional battery.

    dc_extra_of(row): PV the inverter cut off, usable only to charge a DC-coupled battery.
    """
    eff = SIM["battery_efficiency"] ** 0.5
    p_max = SIM["battery_power_kw"] * STEP_H
    soc = 0.0
    imp, exp = defaultdict(float), 0.0
    months = defaultdict(lambda: [0.0, 0.0])  # month -> [energy cost incl. tax, export kWh]
    for r in rows:
        net = (pv_of(r) - r["load"]) * STEP_H  # kWh, + surplus
        if battery_kwh:
            dc = dc_extra_of(r) * STEP_H if dc_extra_of else 0.0
            charge = min(dc * eff, battery_kwh - soc, p_max * eff)
            soc += charge
            if net > 0:
                charge = min(net * eff, battery_kwh - soc, p_max * eff - charge)
                soc += charge
                net -= charge / eff
            elif net < 0:
                discharge = min(-net, soc * eff, p_max)
                soc -= discharge / eff
                net += discharge
        month = months[r["day"][:7]]
        w = r["w"]
        if net > 0:
            exp += net * w
            month[1] += net * w
        else:
            imp[r["period"]] -= net * w
            month[0] -= net * r["price"] * w
    return imp, exp, months


def simulate_offgrid(rows, pv_of, battery_kwh, power_kw):
    """No grid: surplus is wasted. When the battery falls to the emergency level the house runs
    on essentials only (fridge, some lights) from the generator, like during a grid outage today;
    everything else stays off until the sun has charged the battery back to the release level.

    Returns (emergency hours, emergency days, kWh not delivered, generator kWh).
    """
    og = SIM["offgrid"]
    eff = SIM["battery_efficiency"] ** 0.5
    p_max = power_kw * STEP_H
    enter, leave = og["emergency_start_soc"] * battery_kwh, og["emergency_stop_soc"] * battery_kwh
    essential = min(og["essential_kw"], og["generator_kw"]) * STEP_H
    soc = battery_kwh
    emergency = False
    hours = shed = gen_kwh = 0.0
    days = set()
    for r in rows:
        w = r["w"]
        pv = pv_of(r) * STEP_H
        load = r["load"] * STEP_H
        if not emergency and soc <= enter:
            emergency = True
        elif emergency and soc >= leave:
            emergency = False
        if emergency:
            # generator runs the essentials, all PV charges the battery, the rest of the house is off
            hours += STEP_H * w
            days.add(r["day"])
            gen_kwh += essential * w
            shed += max(0.0, load - essential) * w
            soc = min(battery_kwh, soc + min(pv, p_max) * eff)
            continue
        net = pv - load
        if net >= 0:
            soc = min(battery_kwh, soc + min(net, p_max) * eff)
            continue
        give = min(-net, p_max, soc * eff)
        soc -= give / eff
        shed += (-net - give) * w  # more than the inverters can deliver
    return hours, days, shed, gen_kwh


def grid_fixed_cost():
    """Yearly cost of just being connected, incl. taxes: contracted power, social bonus, meter rental."""
    g = SIM["grid_fixed"]
    taxed = ((g["power_p1_eur_kw_day"] + g["power_p2_eur_kw_day"]) * g["contracted_kw"]
             + g["bono_social_eur_day"]) * 365 * (1 + g["electricity_tax"])
    return (taxed + g["meter_eur_day"] * 365) * (1 + g["vat"])


def finance(capex, saving, lifetime):
    """Return per year (IRR) and the difference to putting the same money into an MSCI World ETF.

    Savings grow with the electricity price and shrink with panel degradation. For a fair
    comparison each year's saving is invested in the ETF too; after `lifetime` years both
    ETF holdings are sold and pay capital gains tax.
    """
    f = SIM["finance"]
    r, t = f["etf_return"], f["capital_gains_tax"]
    flows = [saving * ((1 + f["electricity_price_growth"]) * (1 - f["pv_degradation"])) ** y
             for y in range(lifetime)]

    def npv(rate):
        return -capex + sum(v / (1 + rate) ** (y + 1) for y, v in enumerate(flows))

    irr = None
    if capex > 0 and npv(-0.5) > 0:
        lo, hi = -0.5, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if npv(mid) > 0 else (lo, mid)
        irr = lo
    solar = sum(v * (1 + r) ** (lifetime - y - 1) for y, v in enumerate(flows))
    solar -= t * (solar - sum(flows))
    etf = capex * (1 + r) ** lifetime
    etf -= t * (etf - capex)
    return (round(irr * 100, 1) if irr is not None else None), round(solar - etf)


def cost(result, export_net, virtual_battery=True):
    """Energy cost per year of billing, as a Spanish retailer with a virtual battery bills it.

    Each month the export credit (net price) first reduces the energy cost before
    electricity tax and VAT, so it is worth export_net x tax_factor. Credit beyond
    that month's energy cost goes to the "Batería Virtual" at its net value and is
    spent on another bill after tax: worth export_net. Without a virtual battery
    (most other providers) that excess credit is lost.
    """
    total = 0.0
    for energy, export_kwh in result[2].values():
        credit = export_kwh * export_net * SIM["tax_factor"]
        if credit <= energy:
            total += energy - credit
        elif virtual_battery:
            total -= (credit - energy) / SIM["tax_factor"]
    return total


def run():
    """Run all scenarios. Returns a dict (also written to logs/simulation.json for the dashboard)."""
    events = CONFIG.get("events", [])
    all_rows = load_history()
    suggestions = suggest_events(all_rows, events)
    # One-off events don't belong to a normal year; recurring ones (Christmas, summer holidays) stay in
    one_off = [e for e in events if not e.get("recurring")]
    rows = [r for r in all_rows if not in_event(r["day"], one_off)]
    if len(rows) != len(all_rows):
        rows = load_history_weights(rows)
    days = len({r["day"] for r in rows})
    calendar_days = len({r["day"][5:] for r in rows})  # distinct calendar days covered
    caps = day_caps(rows)
    tilt, aspect = fit_orientation(rows, caps)
    model = pvgis(tilt, aspect)
    factors = weather_factors(rows, model, caps)
    inv_max = SIM["inverter_max_kw"]

    def unclipped(r):
        cap = caps.get(r["day"])
        if cap is None or r["pv"] < cap - 0.01:
            return r["pv"]
        return max(r["pv"], factors.get(r["day"], 0) * model(r["utc"]))

    def extra(kwp_east, kwp_west):
        e, w = pvgis(SIM["extra_pv_tilt"], -90), pvgis(SIM["extra_pv_tilt"], 90)
        per_kwp = {d: f / SIM["pv_kwp_installed"] for d, f in factors.items()}  # weather of the day
        return lambda r: r["pv"] + per_kwp.get(r["day"], 0) * (kwp_east * e(r["utc"]) + kwp_west * w(r["utc"]))

    measured = lambda r: r["pv"]  # noqa: E731
    lost = lambda r: min(unclipped(r), inv_max) - r["pv"] if r["day"] in caps else 0.0  # noqa: E731
    scale = 365 / calendar_days  # fills calendar days not covered yet

    # Purchase prices: latest shop prices (prices.py) where logged, plus estimated installation
    shop, price_info = prices.latest()
    unit = {
        "battery_eur_per_kwh": shop.get("battery", SIM["battery_eur_per_kwh"]),
        "panel_eur_per_kwp": shop.get("panel", SIM["panel_eur_per_kwp"]),
        "inverter_eur": shop.get("pv_inverter", SIM["pv_inverter_eur"]),
    }

    def battery_cost(kwh, own_inverter=False):
        return round(kwh * unit["battery_eur_per_kwh"] + SIM["battery_install_eur"]
                     + (unit["inverter_eur"] if own_inverter else 0))

    def pv_cost(kwp):
        return round(kwp * (unit["panel_eur_per_kwp"] + SIM["pv_mounting_install_eur_per_kwp"])
                     + unit["inverter_eur"] + SIM["pv_install_fixed_eur"])

    life_pv, life_bat = SIM["finance"]["pv_lifetime_years"], SIM["finance"]["battery_lifetime_years"]
    scenarios = [("Today (measured)", simulate(rows, measured), 0, 0)]
    scenarios.append((f"Inverter back to {inv_max:g} kW (cooling fixed)",
                      simulate(rows, lambda r: min(unclipped(r), inv_max)), 0, 0))
    for kwh in SIM["battery_sizes_kwh"]:
        scenarios.append((f"Battery {kwh} kWh (AC, own inverter)", simulate(rows, measured, kwh),
                          battery_cost(kwh, own_inverter=True), life_bat))
        scenarios.append((f"Battery {kwh} kWh (DC on the SUN2000, catches cut-off PV)",
                          simulate(rows, measured, kwh, lambda r: unclipped(r) - r["pv"]), battery_cost(kwh), life_bat))
    for kwp in SIM["extra_pv_kwp"]:
        for name, e, w in (("east", kwp, 0), ("west", 0, kwp), ("east+west", kwp / 2, kwp / 2)):
            scenarios.append((f"+{kwp} kWp {name} (own inverter)", simulate(rows, extra(e, w)), pv_cost(kwp), life_pv))
    kwp = SIM["extra_pv_kwp"][-1]
    scenarios.append((f"+{kwp} kWp east+west, battery 10 kWh on its hybrid inverter",
                      simulate(rows, extra(kwp / 2, kwp / 2), 10), pv_cost(kwp) + battery_cost(10), life_bat))

    # FusionSolar's power sensor reads a bit higher than the utility meter: scale grid flows to the bills
    bill_list = bills.with_measurements()
    calibration = bills.meter_calibration(bill_list)
    pv_scale = scale
    scale *= calibration
    ex = SIM["export_prices_eur_kwh"]
    base = scenarios[0][1]
    out_scenarios = []
    for name, res, capex, lifetime in scenarios:
        imp, exp, _ = res
        saves = [round((cost(base, p) - cost(res, p)) * scale) for p in ex]
        irr, vs_etf = finance(capex, saves[0], lifetime) if capex else (None, None)
        out_scenarios.append({
            "name": name, "buy_kwh": round(sum(imp.values()) * scale),
            "buy_by_period": {p: round(imp[p] * scale) for p in ("P1", "P2", "P3")},
            "export_kwh": round(exp * scale), "saves_eur": saves, "capex_eur": capex,
            "payback_years": round(capex / saves[0], 1) if capex and saves[0] > 0 else None,
            "lifetime_years": lifetime or None, "irr_pct": irr, "vs_etf_eur": vs_etf,
        })

    # Full autonomy: no grid connection. Existing panels (full 6 kW) + extra panels steeper for winter
    # on off-grid hybrid inverters with 48 V batteries; a generator covers what is still missing.
    og = SIM["offgrid"]
    steep = pvgis(og["extra_pv_tilt"], aspect)
    per_kwp_day = {d: f / SIM["pv_kwp_installed"] for d, f in factors.items()}
    peak_kw = max(r["load"] for r in rows)
    inverters = -(-peak_kw // og["inverter_kw"])  # ceil
    og_unit = {"battery_eur_per_kwh": shop.get("battery_48v", og["battery_eur_per_kwh"]),
               "inverter_eur": shop.get("offgrid_inverter", og["inverter_eur"])}
    grid_cost_today = cost(base, ex[0]) * scale + grid_fixed_cost()
    ev_km_per_kwh = (1 - SIM["ev_charging_loss"]) * 100 / SIM["ev_kwh_per_100km"]
    diesel_per_kwh = ev_km_per_kwh * SIM["diesel_l_per_100km"] / 100 * SIM["diesel_eur_per_l"]
    options = []
    for kwp_extra in og["extra_pv_kwp"]:
        pv_of = (lambda k: lambda r: min(unclipped(r), inv_max) + per_kwp_day.get(r["day"], 0) * k * steep(r["utc"]))(kwp_extra)
        for kwh in og["battery_kwh"]:
            hours, em_days, shed, gen_kwh = simulate_offgrid(rows, pv_of, kwh, inverters * og["inverter_kw"])
            hours, shed, gen_kwh = hours * pv_scale, shed * pv_scale, gen_kwh * pv_scale
            capex = round(kwh * og_unit["battery_eur_per_kwh"] + inverters * og_unit["inverter_eur"]
                          + kwp_extra * (unit["panel_eur_per_kwp"] + SIM["pv_mounting_install_eur_per_kwp"])
                          + og["install_eur"] + og["generator_eur"])
            # In emergency mode the electric car isn't charged: those km go with a combustion car. Upper
            # bound: all energy not delivered is valued as car charging (the car is most of it).
            diesel = shed * diesel_per_kwh
            running = (gen_kwh * og["generator_eur_per_kwh"] + diesel
                       + (og["generator_upkeep_eur_year"] if gen_kwh > 0.5 else 0))
            saving = round(grid_cost_today - running)
            irr, vs_etf = finance(capex, saving, life_bat)
            options.append({"extra_kwp": kwp_extra, "battery_kwh": kwh, "diesel_eur": round(diesel),
                            "emergency_days": round(len(em_days) * pv_scale),
                            "emergency_hours": round(hours), "shed_kwh": round(shed), "generator_kwh": round(gen_kwh),
                            "capex_eur": capex, "saves_eur": saving, "irr_pct": irr, "vs_etf_eur": vs_etf})
    offgrid = {"options": options, "peak_load_kw": round(peak_kw, 1), "inverters": int(inverters),
               "inverter_kw": og["inverter_kw"], "grid_cost_today_eur": round(grid_cost_today),
               "grid_fixed_eur": round(grid_fixed_cost()), "prices": {k: round(v) for k, v in og_unit.items()},
               "assumptions": {k: og[k] for k in ("extra_pv_tilt", "install_eur", "generator_eur", "generator_kw",
                                                   "generator_name", "generator_eur_per_kwh",
                                                   "generator_upkeep_eur_year", "essential_kw",
                                                   "emergency_start_soc", "emergency_stop_soc",
                                                   "max_emergency_days")}}

    months = defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = months[r["day"][:7]]
        m["pv"] += r["pv"] * STEP_H
        m["load"] += r["load"] * STEP_H
        net = (r["load"] - r["pv"]) * STEP_H
        if net > 0:
            m["buy"] += net
            m["buy_eur"] += net * r["price"]
        else:
            m["export"] -= net
    out_months = [{"month": k, **{f: round(v[f]) for f in ("pv", "load", "buy", "export")},
                   "self_use_pct": round(100 * (v["pv"] - v["export"]) / v["pv"]) if v["pv"] else None,
                   "net_eur": round(cost((None, None, {k: [v["buy_eur"], v["export"]]}), ex[0])),
                   "virtual_battery_eur": round(max(0.0, v["export"] * ex[0] - v["buy_eur"] / SIM["tax_factor"]), 2)}
                  for k, v in sorted(months.items())]

    # The measured year under each tariff (the monthly credit rule applies to all)
    tariffs = []
    for t in SIM["tariffs"]:
        m_cost = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            net = (r["load"] - r["pv"]) * STEP_H * r["w"]
            m = m_cost[r["day"][:7]]
            if net > 0:
                m[0] += net * t["energy_eur_kwh"].get(r["period"], t["energy_eur_kwh"].get("all", 0)) * SIM["tax_factor"]
            else:
                m[1] -= net
        tariffs.append({"name": t["name"], "export_eur_kwh": t["export_eur_kwh"],
                        "virtual_battery": t.get("virtual_battery", False),
                        "energy_eur_year": round(cost((None, None, m_cost), t["export_eur_kwh"],
                                                      t.get("virtual_battery", False)) * scale)})

    ev_km = (1 - SIM["ev_charging_loss"]) * 100 / SIM["ev_kwh_per_100km"]
    result = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "days": days, "first_day": rows[0]["day"], "last_day": rows[-1]["day"],
        "orientation": {"tilt": tilt, "aspect": aspect},
        "calendar_days": calendar_days,
        "pv_kwh_year": round(sum(r["pv"] * r["w"] for r in rows) * STEP_H * pv_scale),
        "clipped_ac_kwh_year": round(sum(lost(r) * r["w"] for r in rows) * STEP_H * pv_scale),
        "clipped_dc_kwh_year": round(sum((unclipped(r) - r["pv"]) * r["w"] for r in rows) * STEP_H * pv_scale),
        "export_prices": ex, "scenarios": out_scenarios, "months": out_months,
        "meter_calibration": calibration, "tariffs": tariffs,
        "events": events, "event_suggestions": suggestions, "offgrid": offgrid,
        "finance": SIM["finance"],
        "excluded_days": len({r["day"] for r in all_rows}) - len({r["day"] for r in rows}),
        "car": {"km_per_kwh": round(ev_km, 1),
                "diesel_eur_per_kwh": round(ev_km * SIM["diesel_l_per_100km"] / 100 * SIM["diesel_eur_per_l"], 2)},
        "prices": {**{k: round(v) for k, v in unit.items()}, **price_info},
        "assumptions": {k: SIM[k] for k in ("battery_power_kw", "battery_efficiency", "battery_install_eur",
                                            "pv_mounting_install_eur_per_kwp", "pv_install_fixed_eur",
                                            "extra_pv_tilt", "tax_factor")},
    }
    OUT_FILE.write_text(json.dumps(result, indent=1))
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    r = run()
    print(f"History: {r['days']} days ({r['first_day']} to {r['last_day']}), scaled to 365 days.")
    print(f"Existing panels fit best: tilt {r['orientation']['tilt']}°, aspect {r['orientation']['aspect']}° "
          f"(0 = south, + = west).")
    print(f"PV {r['pv_kwh_year']:,} kWh/year; the power limit cut off about {r['clipped_ac_kwh_year']:,} kWh "
          f"(AC up to {SIM['inverter_max_kw']:g} kW), {r['clipped_dc_kwh_year']:,} kWh on the DC side.\n")
    ex = r["export_prices"]
    head = "".join(f"  save/yr @{p * 100:g}ct" for p in ex)
    print(f"{'Scenario':56} {'buy kWh':>8} {'P1':>6} {'P2':>6} {'P3':>6} {'export':>7}{head}  {'cost €':>7}  payback")
    for s in r["scenarios"]:
        b = s["buy_by_period"]
        payback = f"{s['payback_years']:5.1f} yr" if s["payback_years"] else ""
        print(f"{s['name']:56} {s['buy_kwh']:8,} {b['P1']:6,} {b['P2']:6,} {b['P3']:6,} {s['export_kwh']:7,}"
              + "".join(f"  {v:14,}" for v in s["saves_eur"]) + f"  {s['capex_eur']:7,}  {payback}")
    print(f"\nCar: 1 kWh at the wallbox = {r['car']['km_per_kwh']} km in the electric car = "
          f"{r['car']['diesel_eur_per_kwh']:.2f} € fuel in a combustion car.")


if __name__ == "__main__":
    main()
