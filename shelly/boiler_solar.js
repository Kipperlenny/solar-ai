// Electric hot water boiler control for Shelly Gen2+/Gen3 plugs
//
// nightStart-nightEnd   off
// nightEnd-forceStart   heat from surplus only: switch on, wait for other
//                       loads (e.g. a surplus-charging wallbox) to regulate
//                       down, switch off again if the grid covers the boiler
// forceStart-nightStart always on, the boiler's thermostat regulates
// Legionella:           if the boiler was not full for maxNotFullSec, heat
//                       outside the night
// No hub data:          on from fallbackStart instead of the surplus logic
//
// "Full" = switched on, but the boiler draws almost nothing (thermostat off).
//
// solar_hub.py pushes PV and house load every minute:
//   http://<plug-ip>/script/<id>/data?pv=<watts>&load=<watts>
// Status: http://<plug-ip>/script/<id>/status
//
// Settings come from config.toml [boiler]; tools/shelly_deploy.py replaces
// the block between the CONFIG markers on upload.

// CONFIG-START
let CFG = {
  nightStart: "23:00",
  nightEnd: "09:00",
  forceStart: "16:00",
  fallbackStart: "12:00",
  tryPvW: 2000,
  maxImportW: 300,
  badReadings: 2,
  settleSec: 120,
  retrySec: 900,
  fullBelowW: 30,
  fullAfterSec: 120,
  maxNotFullSec: 86400,
  maxDataAgeSec: 600
};
// CONFIG-END

function minutes(hhmm) {
  return Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
}

let NIGHT_START = minutes(CFG.nightStart);
let NIGHT_END = minutes(CFG.nightEnd);
let FORCE_START = minutes(CFG.forceStart);
let FALLBACK_START = minutes(CFG.fallbackStart);

let state = {
  mode: "start",
  on: false,
  onSince: 0,
  pvW: null,
  loadW: null,
  lastDataTs: 0,
  nextTryTs: 0,
  overCount: 0,
  lowSince: 0,
  lastFullTs: 0
};

function now() {
  return Shelly.getComponentStatus("sys").unixtime;
}

function minuteOfDay() {
  let t = Shelly.getComponentStatus("sys").time;
  if (!t) return null;
  return minutes(t);
}

function setBoiler(on, t) {
  if (on === state.on) return;
  state.on = on;
  state.overCount = 0;
  state.lowSince = 0;
  if (on) state.onSince = t;
  Shelly.call("Switch.Set", { id: 0, on: on });
}

function trackFull(t) {
  let sw = Shelly.getComponentStatus("switch:0");
  if (!sw.output || t - state.onSince < 60 || sw.apower >= CFG.fullBelowW) {
    state.lowSince = 0;
    return;
  }
  if (!state.lowSince) state.lowSince = t;
  if (t - state.lowSince >= CFG.fullAfterSec && t - state.lastFullTs > 600) {
    state.lastFullTs = t;
    Shelly.call("KVS.Set", { key: "boiler_last_full", value: JSON.stringify(t) });
  }
}

function surplusWanted(t) {
  if (!state.on) return state.pvW >= CFG.tryPvW && t >= state.nextTryTs;
  if (state.overCount >= CFG.badReadings) {
    state.nextTryTs = t + CFG.retrySec;
    return false;
  }
  return true;
}

function decide() {
  let t = now();
  let m = minuteOfDay();
  trackFull(t);

  let want;
  if (m === null) {
    state.mode = "no_time";
    want = true;
  } else if (m >= NIGHT_START || m < NIGHT_END) {
    state.mode = "night";
    want = false;
  } else if (m >= FORCE_START) {
    state.mode = "evening";
    want = true;
  } else if (t - state.lastFullTs > CFG.maxNotFullSec) {
    state.mode = "legionella";
    want = true;
  } else if (t - state.lastDataTs > CFG.maxDataAgeSec) {
    state.mode = "fallback";
    want = m >= FALLBACK_START;
  } else {
    state.mode = "surplus";
    want = surplusWanted(t);
  }
  setBoiler(want, t);
}

function onData(pv, load) {
  let t = now();
  state.pvW = pv;
  state.loadW = load;
  state.lastDataTs = t;

  // Only judge surplus heating once the wallbox had time to react,
  // and only while the boiler actually draws power.
  let sw = Shelly.getComponentStatus("switch:0");
  if (state.mode === "surplus" && state.on && t - state.onSince >= CFG.settleSec &&
      sw.apower >= CFG.fullBelowW) {
    if (load - pv > CFG.maxImportW) state.overCount++;
    else state.overCount = 0;
  }
  decide();
}

function parseQuery(q) {
  let o = {};
  if (!q) return o;
  let parts = q.split("&");
  for (let i = 0; i < parts.length; i++) {
    let kv = parts[i].split("=");
    o[kv[0]] = Number(kv[1]);
  }
  return o;
}

function reply(resp, code, obj) {
  resp.code = code;
  resp.headers = [["Content-Type", "application/json"]];
  resp.body = JSON.stringify(obj);
  resp.send();
}

HTTPServer.registerEndpoint("data", function (req, resp) {
  let q = parseQuery(req.query);
  if (isNaN(q.pv) || isNaN(q.load)) {
    reply(resp, 400, { error: "expected ?pv=<watts>&load=<watts>" });
    return;
  }
  onData(q.pv, q.load);
  reply(resp, 200, { mode: state.mode, on: state.on });
});

HTTPServer.registerEndpoint("status", function (req, resp) {
  let sw = Shelly.getComponentStatus("switch:0");
  reply(resp, 200, { cfg: CFG, state: state, apower: sw.apower, now: now() });
});

// Start from the real switch state, restore when the boiler was last full
state.on = Shelly.getComponentStatus("switch:0").output;
state.onSince = now();
Shelly.call("KVS.Get", { key: "boiler_last_full" }, function (res) {
  if (res && res.value) state.lastFullTs = JSON.parse(res.value);
  decide();
  Timer.set(30000, true, decide);
});
