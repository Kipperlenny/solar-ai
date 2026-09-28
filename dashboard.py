"""Local web dashboard for solar_hub.py: current state, the reasons behind it, and the log.

Runs as a thread inside the hub on http://localhost:<[dashboard] port>.
  /            the page
  /api/state   current state as JSON (Hub.snapshot())
  /api/log     hub.log, ?lines=<n> for the last n lines or ?lines=all
  /api/simulation  latest result of tools/simulate.py (logs/simulation.json)
  /api/bills   bills from bills/ with the FusionSolar measurement of the same period
"""

import json
import logging

import bills
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("solar_hub")


def tail(path, lines):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return b""
    if lines == "all":
        return data
    return b"\n".join(data.rstrip(b"\n").split(b"\n")[-int(lines):])


def serve(hub, port, log_file, simulation_file):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            try:
                if url.path == "/":
                    self.reply("text/html; charset=utf-8", PAGE.encode())
                elif url.path == "/api/state":
                    self.reply("application/json", json.dumps(hub.snapshot()).encode())
                elif url.path == "/api/simulation":
                    body = simulation_file.read_bytes() if simulation_file.exists() else b"{}"
                    self.reply("application/json", body)
                elif url.path == "/api/bills":
                    self.reply("application/json", json.dumps(bills.with_measurements()).encode())
                elif url.path == "/api/log":
                    lines = parse_qs(url.query).get("lines", ["500"])[0]
                    self.reply("text/plain; charset=utf-8", tail(log_file, lines))
                else:
                    self.send_error(404)
            except ValueError:
                self.send_error(400)

        def reply(self, ctype, body):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # keep HTTP requests out of hub.log

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        log.error("Dashboard could not start on port %s: %s", port, e)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Dashboard on http://localhost:%s", port)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Hub</title>
<style>
  :root {
    --bg: #f5f5f2; --card: #ffffff; --text: #1d1d1b; --muted: #6b6b66; --line: #e2e2dc;
    --on: #1f8a4c; --off: #8a8a84; --idle: #b07a12; --warn: #b3261e; --mono: ui-monospace, Consolas, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #151514; --card: #1f1f1d; --text: #ecece8; --muted: #9b9b95; --line: #33332f;
      --on: #4cc27f; --off: #7a7a74; --idle: #c9962e; --warn: #f2786f;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 2600px; margin: 0 auto; padding: 20px 24px 40px; }
  header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; margin-bottom: 16px; }
  h1 { font-size: 20px; margin: 0; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 8px; }
  .muted { color: var(--muted); }
  .stale { color: var(--warn); font-weight: 600; }
  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); margin-bottom: 12px; }
  @media (max-width: 520px) { main { padding: 12px 12px 32px; } .grid { grid-template-columns: 1fr; } }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .big { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .badge { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 99px; color: #fff; background: var(--off); }
  .badge.on { background: var(--on); }
  .badge.idle { background: var(--idle); }
  .swatch { width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--line); flex: none; }
  .state { font-weight: 600; font-size: 17px; }
  .why { margin: 6px 0 0; }
  .why::before { content: "Why: "; font-weight: 600; }
  .detail { font-size: 13px; color: var(--muted); margin-top: 6px; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin-bottom: 8px; }
  input[type=search], select { font: inherit; padding: 4px 8px; border: 1px solid var(--line);
         border-radius: 6px; background: var(--card); color: var(--text); }
  input[type=search] { flex: 1 1 200px; }
  #log { font: 12.5px/1.5 var(--mono); height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-word; }
  #log div { padding: 1px 0; border-bottom: 1px solid var(--line); }
  #log .decision { font-weight: 600; }
  #log .warn { color: var(--warn); }
  .section { margin: 20px 0 12px; }
  .section h2 { font-size: 15px; }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; white-space: normal; }
  th { color: var(--muted); font-weight: 600; font-size: 12.5px; }
  tr.base td { font-weight: 600; }
  td.pos { color: var(--on); }
  td.neg { color: var(--warn); }
  .notes { font-size: 13.5px; margin: 10px 0 0; padding-left: 18px; }
  .notes li { margin: 4px 0; }
  .warnval { color: var(--warn); font-weight: 600; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Solar Hub</h1>
    <span id="updated" class="muted">loading...</span>
  </header>

  <div class="grid">
    <div class="card"><h2>PV</h2><div class="big" id="pv">-</div></div>
    <div class="card"><h2>House</h2><div class="big" id="load">-</div></div>
    <div class="card"><h2>Grid</h2><div class="big" id="grid">-</div></div>
    <div class="card"><h2>Tariff</h2><div class="big" id="tariff">-</div><div class="detail" id="price"></div></div>
    <div class="card"><h2>Wallbox</h2><div class="big" id="wallbox">-</div><div class="detail" id="wallbox-detail"></div></div>
    <div class="card">
      <h2>Bulb</h2>
      <div class="row"><div class="swatch" id="bulb-swatch"></div><span class="state" id="bulb-state">-</span></div>
      <p class="why" id="bulb-why"></p>
      <div class="detail" id="bulb-detail"></div>
    </div>
    <div class="card">
      <h2>Boiler</h2>
      <div class="row"><span class="badge" id="boiler-badge">-</span><span class="state" id="boiler-mode">-</span></div>
      <p class="why" id="boiler-why"></p>
      <div class="detail" id="boiler-detail"></div>
    </div>
    <div class="card">
      <h2>Pool pump</h2>
      <div class="row"><span class="badge" id="pool-badge">-</span><span class="state" id="pool-sun">-</span></div>
      <p class="why" id="pool-why"></p>
    </div>
    <div class="card">
      <h2>Inverter</h2>
      <div class="row"><span class="state" id="inv-temp">-</span></div>
      <div id="inv-values"></div>
      <div class="detail" id="inv-detail"></div>
    </div>
  </div>

  <div class="card section">
    <h2>Investment estimate - the real year replayed</h2>
    <div id="sim-summary" class="muted">loading...</div>
    <div class="scroll"><table id="sim-table"></table></div>
    <ul class="notes" id="sim-notes"></ul>
  </div>

  <div class="card section">
    <h2>Full autonomy - no grid connection</h2>
    <div id="og-summary"></div>
    <div class="scroll"><table id="og-table"></table></div>
    <ul class="notes" id="og-notes"></ul>
  </div>

  <div class="card section">
    <h2>Special periods</h2>
    <div id="events-summary" class="muted"></div>
    <div class="scroll"><table id="events-table"></table></div>
  </div>

  <div class="card section">
    <h2>Bills</h2>
    <div id="bills-summary" class="muted"></div>
    <div class="scroll"><table id="bills-table"></table></div>
  </div>

  <div class="card section">
    <h2>Month by month (measured)</h2>
    <div class="scroll"><table id="month-table"></table></div>
  </div>

  <div class="card">
    <h2>Log</h2>
    <div class="controls">
      <select id="lines">
        <option value="300">last 300 lines</option>
        <option value="2000">last 2000 lines</option>
        <option value="all">whole log</option>
      </select>
      <label><input type="checkbox" id="decisions"> only decisions and warnings</label>
      <input type="search" id="filter" placeholder="filter, e.g. Boiler">
    </div>
    <div id="log"></div>
  </div>
</main>

<script>
const $ = id => document.getElementById(id);
const W = w => w == null ? "-" : `${Math.round(w).toLocaleString()} W`;
const DECISION = /Bulb state|Bulb set|Boiler (on|off)|Pool (on|off)|Wallbox|FusionSolar|started|Dashboard/;
let logLines = [];

function kelvinToRgb(k) {
  // rough warm-to-cold white for the swatch
  const t = (k - 3000) / 3500;
  return `rgb(255, ${Math.round(200 + 45 * t)}, ${Math.round(140 + 115 * t)})`;
}

function badge(el, text, cls) {
  el.textContent = text;
  el.className = "badge " + cls;
}

async function loadState() {
  let s;
  try { s = await (await fetch("/api/state")).json(); }
  catch { $("updated").textContent = "hub not reachable"; $("updated").className = "stale"; return; }
  if (!s.time) { $("updated").textContent = "waiting for the first reading..."; return; }
  const age = Math.round((Date.now() - new Date(s.time)) / 1000);
  $("updated").textContent = `data from ${s.time.slice(11)} (${age} s ago) - hub running since ${s.started.replace("T", " ")}`;
  $("updated").className = age > 180 ? "stale" : "muted";

  $("pv").textContent = W(s.pv_w);
  $("load").textContent = W(s.load_w);
  $("grid").textContent = s.export_w == null ? "-"
    : s.export_w >= 0 ? `selling ${W(s.export_w)}` : `buying ${W(-s.export_w)}`;
  $("tariff").textContent = `${s.period} - ${s.level}`;
  $("price").textContent = `${s.price_eur_kwh.toFixed(3)} €/kWh`;

  const b = s.bulb, l = b.light;
  $("bulb-state").textContent = b.state + (b.dark ? " (dark: white light)" : "");
  $("bulb-swatch").style.background = l[0] === "color" ? `rgb(${l[1]}, ${l[2]}, ${l[3]})` : kelvinToRgb(l[1]);
  $("bulb-why").textContent = b.reason;
  $("bulb-detail").textContent = `bulb: ${b.device} - ` + (l[0] === "color"
    ? `color ${l[1]}/${l[2]}/${l[3]} at ${l[4]} %` : `white ${l[1]} K at ${l[2]} %`);

  const bo = s.boiler, full = bo.on && bo.power_w != null && bo.power_w < 30;
  if (bo.on == null) badge($("boiler-badge"), "?", "");
  else if (!bo.on) badge($("boiler-badge"), "OFF", "");
  else if (full) badge($("boiler-badge"), "FULL", "idle");
  else badge($("boiler-badge"), "HEATING", "on");
  $("boiler-mode").textContent = (bo.mode ?? "-") + (full ? " (switched on, tank hot)" : "");
  $("boiler-why").textContent = s.boiler.reason;
  $("boiler-detail").textContent = `draws ${W(s.boiler.power_w)} - tank last full: ${s.boiler.last_full ?? "-"}`;

  const po = s.pool;
  if (po.sun_ok == null) badge($("pool-badge"), "?", "");
  else if (!po.sun_ok) badge($("pool-badge"), "OFF", "");
  else if (po.on) badge($("pool-badge"), "PUMPING", "on");
  else badge($("pool-badge"), "PAUSE", "idle");
  $("pool-sun").textContent = po.sun_ok == null ? "-" : po.sun_ok ? "cycle active" : "not enough sun";
  $("pool-why").textContent = s.pool.reason;

  const inv = s.inverter || {};
  if (inv.temp_c != null) {
    const v = parseFloat(inv.grid_v);
    $("inv-temp").textContent = `${inv.temp_c} °C inside`;
    $("inv-values").replaceChildren();
    for (const [label, value, warn] of [
      ["Output", `${inv.active_kw} kW`], ["Grid voltage", `${inv.grid_v} V`, v > 248],
      ["Reactive power", `${inv.reactive_kvar} kvar`], ["Power factor", inv.power_factor]]) {
      const d = document.createElement("div");
      d.textContent = `${label}: ${value}`;
      if (warn) d.className = "warnval";
      $("inv-values").appendChild(d);
    }
    $("inv-detail").textContent = `${inv.status} - cloud, updated ${inv.updated}. Grid limit 253 V (230 V +10 %).`;
  } else {
    $("inv-temp").textContent = "-";
    $("inv-detail").textContent = "waiting for the FusionSolar cloud";
  }

  const wb = s.wallbox;
  $("wallbox").textContent = !wb.found ? "-" : wb.power_w == null ? "measuring..."
    : wb.power_w >= 100 ? `charging ${W(wb.power_w)}` : "not charging";
  $("wallbox-detail").textContent = !wb.found ? "no wallbox found in FusionSolar"
    : `cloud counter ${wb.total_kwh?.toFixed(1) ?? "-"} kWh, last change ${wb.updated ?? "-"} (updates about every 2 min while charging)`;
}

const EUR = v => `${Math.round(v).toLocaleString()} €`;
const KWH = v => Math.round(v).toLocaleString();

function row(cells, cls) {
  const tr = document.createElement("tr");
  if (cls) tr.className = cls;
  for (const c of cells) {
    const obj = typeof c === "object" && c !== null ? c : {v: c};
    const td = document.createElement(obj.th ? "th" : "td");
    td.textContent = obj.v;
    if (obj.cls) td.className = obj.cls;
    tr.appendChild(td);
  }
  return tr;
}

async function loadSimulation() {
  let r;
  try { r = await (await fetch("/api/simulation")).json(); } catch { return; }
  if (!r.scenarios) { $("sim-summary").textContent = "no simulation yet (runs after the FusionSolar sync)"; return; }
  $("sim-summary").textContent = `${r.days} days of real 5-minute data (${r.first_day} to ${r.last_day}), `
    + (r.days > 365 ? "each calendar day averaged over the years logged" : `scaled to a year (${r.calendar_days} of 365 calendar days covered)`)
    + ` - calculated ${r.generated.replace("T", " ")}. PV ${KWH(r.pv_kwh_year)} kWh/year; `
    + `the inverter power limit cut off about ${KWH(r.clipped_ac_kwh_year)} kWh.`;
  const t = $("sim-table"); t.replaceChildren();
  t.appendChild(row([{v: "Scenario", th: 1}, {v: "Buy kWh", th: 1}, {v: "P1", th: 1}, {v: "P2", th: 1},
    {v: "P3", th: 1}, {v: "Export kWh", th: 1},
    ...r.export_prices.map(p => ({v: `Saves/yr, export ${Math.round(p * 100)} ct`, th: 1})),
    {v: "Cost", th: 1}, {v: "Payback", th: 1}, {v: "Return/yr", th: 1},
    {v: `vs. MSCI World ETF (${Math.round(r.finance.etf_return * 100)} %/yr)`, th: 1}]));
  for (const s of r.scenarios) {
    const b = s.buy_by_period;
    t.appendChild(row([s.name, KWH(s.buy_kwh), KWH(b.P1), KWH(b.P2), KWH(b.P3), KWH(s.export_kwh),
      ...s.saves_eur.map(v => ({v: v ? EUR(v) : "-", cls: v > 0 ? "pos" : ""})),
      s.capex_eur ? EUR(s.capex_eur) : "-", s.payback_years ? `${s.payback_years} yr` : "-",
      s.irr_pct == null ? "-" : {v: `${s.irr_pct} %`, cls: s.irr_pct > r.finance.etf_return * 100 ? "pos" : "neg"},
      s.vs_etf_eur == null ? "-" : {v: `${s.vs_etf_eur > 0 ? "+" : ""}${EUR(s.vs_etf_eur)} after ${s.lifetime_years} yr`,
                                    cls: s.vs_etf_eur > 0 ? "pos" : "neg"}],
      s.capex_eur === 0 && s.saves_eur[0] === 0 ? "base" : ""));
  }
  const a = r.assumptions, n = $("sim-notes"); n.replaceChildren();
  const f = r.finance;
  for (const text of [
    `Return/yr: the interest rate the investment earns through its savings (IRR). The ETF column compares with putting the same money into an MSCI World ETF (${Math.round(f.etf_return * 100)} %/yr, sold at the end with ${Math.round(f.capital_gains_tax * 100)} % tax on gains), while every year's savings are invested in the ETF too. Green = better than the ETF. Electricity prices +${Math.round(f.electricity_price_growth * 100)} %/yr, panels -${f.pv_degradation * 100} %/yr; panels last ${f.pv_lifetime_years} years, batteries ${f.battery_lifetime_years} (no replacement inverter included).`,
    `Prices include electricity tax and VAT (x${a.tax_factor}); the export credit is net and deducted before tax, so 6 ct is worth ${(6 * a.tax_factor).toFixed(1)} ct.`,
    `Battery: ${a.battery_power_kw} kW, ${Math.round(a.battery_efficiency * 100)} % round trip, discharges whenever the house (including the car) draws from the grid - so it also empties into the car: the worst case.`,
    `"DC on the SUN2000": a LUNA2000 on the existing inverter, it also stores what the power limit cuts off. "AC": a separate battery system.`,
    `Extra panels: ${a.extra_pv_tilt}° tilt on their own inverter, production from PVGIS scaled with each real day's weather.`,
    `Purchase prices: shop prices checked ${r.prices.checked ?? "never"} (median): battery ${r.prices.battery_eur_per_kwh} €/kWh, panels ${r.prices.panel_eur_per_kwp} €/kWp, inverter ${r.prices.inverter_eur} € - plus installation (battery ${a.battery_install_eur} €; panels ${a.pv_mounting_install_eur_per_kwp} €/kWp mounting and labour + ${a.pv_install_fixed_eur} € cabling, protection and legalization). A real quote replaces them in config.toml [simulation].`,
    `Car: 1 kWh at the wallbox = ${r.car.km_per_kwh} km in the electric car = ${r.car.diesel_eur_per_kwh.toFixed(2)} € fuel in a combustion car. Extra PV the car takes instead of exporting is worth that, not the export price - not counted above.`,
  ]) { const li = document.createElement("li"); li.textContent = text; n.appendChild(li); }

  const tn = document.createElement("li");
  tn.textContent = `Grid kWh are calibrated to the bills: the utility meter counts ${Math.round((1 - r.meter_calibration) * 100)} % less than FusionSolar. `
    + `Tariffs on the measured year (energy minus export credit per year): `
    + r.tariffs.map(t => `${t.name}: ${EUR(t.energy_eur_year)}`).join(", ") + ". Fixed costs (contracted power, meter) are the same.";
  n.appendChild(tn);

  const og = r.offgrid, ot = $("og-table"); ot.replaceChildren();
  const cheapest = list => list.sort((x, y) => x.capex_eur - y.capex_eur)[0];
  const full = cheapest(og.options.filter(o => o.emergency_days === 0));
  const ok = cheapest(og.options.filter(o => o.emergency_days <= og.assumptions.max_emergency_days));
  $("og-summary").textContent = `Today the grid costs ${EUR(og.grid_cost_today_eur)} a year: ${EUR(og.grid_cost_today_eur - og.grid_fixed_eur)} energy after export credit and ${EUR(og.grid_fixed_eur)} just for the connection (contracted power, meter, taxes). `
    + (ok ? `Cheapest setup with at most ${og.assumptions.max_emergency_days} emergency days a year: +${ok.extra_kwp} kWp and ${ok.battery_kwh} kWh for about ${EUR(ok.capex_eur)} (${ok.emergency_days} days, ${ok.emergency_hours} h on fridge and lights). ` : `No tested setup stays within ${og.assumptions.max_emergency_days} emergency days a year. `)
    + (full ? `Never in emergency mode: +${full.extra_kwp} kWp and ${full.battery_kwh} kWh for about ${EUR(full.capex_eur)}.` : "")
    + ` Peak consumption ${og.peak_load_kw} kW needs ${og.inverters} off-grid inverters of ${og.inverter_kw} kW.`;
  ot.appendChild(row(["Extra panels", "Battery", "Emergency days/yr", "Emergency hours/yr", "kWh not delivered", "Cost", "Saves/yr", "Return/yr",
    `vs. ETF after ${f.battery_lifetime_years} yr`].map(v => ({v, th: 1}))));
  for (const o of og.options) {
    ot.appendChild(row([`+${o.extra_kwp} kWp`, `${o.battery_kwh} kWh`,
      {v: o.emergency_days, cls: o.emergency_days > og.assumptions.max_emergency_days ? "neg" : ""},
      KWH(o.emergency_hours), KWH(o.shed_kwh), EUR(o.capex_eur),
      EUR(o.saves_eur), o.irr_pct == null ? "-" : `${o.irr_pct} %`,
      {v: `${o.vs_etf_eur > 0 ? "+" : ""}${EUR(o.vs_etf_eur)}`, cls: o.vs_etf_eur > 0 ? "pos" : "neg"}],
      o === full || o === ok ? "base" : ""));
  }
  const on = $("og-notes"); on.replaceChildren();
  for (const text of [
    `Technology: ${og.inverters} off-grid hybrid inverters (Deye SUN-8K or Victron MultiPlus-II class, ${EUR(og.prices.inverter_eur)} each) with 48 V LFP batteries (${og.prices.battery_eur_per_kwh} €/kWh); the extra panels (tilted ${og.assumptions.extra_pv_tilt}° for the winter sun) go directly into their solar inputs; the existing SUN2000 keeps running AC-coupled - to confirm with the installer. Emergency mode, like a grid outage today: when the battery falls to ${og.assumptions.emergency_start_soc * 100} %, the ${og.assumptions.generator_name} runs only fridge and lights (${og.assumptions.essential_kw} kW, ${og.assumptions.generator_eur_per_kwh} €/kWh fuel); everything else stays off until the sun has recharged the battery to ${og.assumptions.emergency_stop_soc * 100} %. The electric car isn't charged from the generator - those trips go with a combustion car: "Saves/yr" subtracts the energy not delivered at ${r.car.diesel_eur_per_kwh.toFixed(2)} €/kWh fuel (an upper bound, part of it is house consumption). Acceptable: ${og.assumptions.max_emergency_days} days a year (config.toml).`,
    `Installation ${EUR(og.assumptions.install_eur)} (labour and cabling). Not included: the roof space for extra panels, a room for the batteries, battery replacement after ${f.battery_lifetime_years} years, and the fees to reconnect to the grid later.`,
    `The car is treated as today: it also charges in the evening and at night. Off-grid it would have to charge from the sun during the day - with the wallbox data from the coming weeks this can be simulated.`,
  ]) { const li = document.createElement("li"); li.textContent = text; on.appendChild(li); }

  const ev = $("events-table"); ev.replaceChildren();
  $("events-summary").textContent = `Marked in config.toml [[events]]: one-off periods are left out of the average year `
    + `(${r.excluded_days} days now), recurring ones (Christmas, the yearly holiday) stay in. `
    + `Below: periods that look unusual and are not marked yet - add them to config.toml, with recurring = true or false.`;
  ev.appendChild(row(["Period", "Days", "Status", "kWh used", "Typical kWh", "Guess / note"].map(v => ({v, th: 1}))));
  for (const e of r.events) ev.appendChild(row([`${e.from} to ${e.to}`, "", e.recurring ? "marked, recurring" : "marked, left out", "", "", e.note ?? e.kind ?? ""]));
  for (const e of r.event_suggestions) ev.appendChild(row([`${e.from} to ${e.to}`, e.days, "unmarked", KWH(e.kwh), KWH(e.typical), e.guess]));

  const m = $("month-table"); m.replaceChildren();
  m.appendChild(row(["Month", "PV kWh", "House kWh", "Bought kWh", "Exported kWh", "Self-used PV", "Net energy cost (6 ct export)"]
    .map(v => ({v, th: 1}))));
  for (const x of r.months) {
    m.appendChild(row([x.month, KWH(x.pv), KWH(x.load), KWH(x.buy), KWH(x.export),
      x.self_use_pct == null ? "-" : `${x.self_use_pct} %`, EUR(x.net_eur)]));
  }
}

async function loadBills() {
  let list;
  try { list = await (await fetch("/api/bills")).json(); } catch { return; }
  const t = $("bills-table"); t.replaceChildren();
  if (!list.length) { $("bills-summary").textContent = "no bills in bills/ yet"; return; }
  $("bills-summary").textContent = `${list.length} bills from bills/. "Measured" is FusionSolar for the same days; `
    + `the virtual battery collects export credit beyond a month's energy cost and pays other bills.`;
  t.appendChild(row(["Period", "Contract", "Tariff", "Bought kWh (measured)", "Exported kWh (measured)",
    "Export credit", "Virtual battery", "Total paid"].map(v => ({v, th: 1}))));
  for (const b of list.slice().reverse()) {
    const bought = Object.values(b.kwh).reduce((a, x) => a + x, 0);
    const vb = b.virtual_battery_in_eur ? `+${b.virtual_battery_in_eur.toFixed(2)} €`
      : b.virtual_battery_used_eur ? `${b.virtual_battery_used_eur.toFixed(2)} € used` : "-";
    t.appendChild(row([`${b.from} to ${b.to}`, b.home ? "house" : "other (…" + b.contract + ")", b.tariff,
      `${KWH(bought)}` + (b.measured_buy_kwh != null ? ` (${KWH(b.measured_buy_kwh)})` : ""),
      b.export_kwh == null ? "-" : `${KWH(b.export_kwh)} (${KWH(b.measured_export_kwh)})`,
      b.export_eur == null ? "-" : `${b.export_eur.toFixed(2)} €`, vb, `${b.total_eur.toFixed(2)} €`]));
  }
}

async function loadLog() {
  try {
    const text = await (await fetch("/api/log?lines=" + $("lines").value)).text();
    logLines = text.split("\n").filter(Boolean).reverse();
    renderLog();
  } catch {}
}

function renderLog() {
  const q = $("filter").value.toLowerCase(), only = $("decisions").checked;
  const box = $("log"), frag = document.createDocumentFragment();
  for (const line of logLines) {
    const warn = / (WARNING|ERROR) /.test(line), dec = DECISION.test(line);
    if (only && !warn && !dec) continue;
    if (q && !line.toLowerCase().includes(q)) continue;
    const div = document.createElement("div");
    div.textContent = line;
    if (warn) div.className = "warn"; else if (dec) div.className = "decision";
    frag.appendChild(div);
  }
  box.replaceChildren(frag);
}

$("lines").onchange = loadLog;
$("decisions").onchange = renderLog;
$("filter").oninput = renderLog;
loadState(); loadLog(); loadSimulation(); loadBills();
setInterval(loadSimulation, 600000);
setInterval(loadBills, 600000);
setInterval(loadState, 10000);
setInterval(loadLog, 30000);
</script>
</body>
</html>
"""
