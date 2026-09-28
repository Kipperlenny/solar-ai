// Pool pump solar control for Shelly Gen2+/Gen3 plugs
// Runs an on/off cycle only while the sun is strong enough to heat a solar
// collector and stands high enough (the collector lies flat, so a low sun
// hardly heats it). Otherwise the pump stays off, because wind would cool
// the water in the collector.
//
// Sun source: PV input power and sun elevation in degrees, pushed by
// solar_hub.py every minute:
//   http://<plug-ip>/script/<id>/pv?w=<watts>&el=<degrees>
// Status: http://<plug-ip>/script/<id>/status
//
// Settings come from config.toml [pool]; tools/shelly_deploy.py replaces the
// block between the CONFIG markers on upload.

// CONFIG-START
let CFG = {
  onW: 2500,
  offW: 2000,
  onMin: 1,
  offMin: 3,
  maxPvAgeSec: 300,
  minElevation: 35
};
// CONFIG-END

let state = {
  sunOk: false,
  pvW: null,
  elevation: null,
  lastPvTs: 0,
  cyclePos: 0,
  pumpOn: false
};

function setPump(on) {
  state.pumpOn = on;
  Shelly.call("Switch.Set", { id: 0, on: on });
}

function now() {
  return Shelly.getComponentStatus("sys").unixtime;
}

function updatePv(w, el) {
  state.pvW = w;
  state.elevation = el;
  state.lastPvTs = now();
  let high = el >= CFG.minElevation;
  if (!state.sunOk && w >= CFG.onW && high) state.sunOk = true;
  if (state.sunOk && (w < CFG.offW || !high)) state.sunOk = false;
}

function tick() {
  let stale = now() - state.lastPvTs > CFG.maxPvAgeSec;
  if (!state.sunOk || stale) {
    state.cyclePos = 0;
    if (state.pumpOn) setPump(false);
    return;
  }

  let wantOn = state.cyclePos < CFG.onMin;
  if (wantOn !== state.pumpOn) setPump(wantOn);
  state.cyclePos = (state.cyclePos + 1) % (CFG.onMin + CFG.offMin);
}

function reply(resp, code, obj) {
  resp.code = code;
  resp.headers = [["Content-Type", "application/json"]];
  resp.body = JSON.stringify(obj);
  resp.send();
}

HTTPServer.registerEndpoint("pv", function (req, resp) {
  let q = {};
  let parts = (req.query || "").split("&");
  for (let i = 0; i < parts.length; i++) {
    let kv = parts[i].split("=");
    q[kv[0]] = Number(kv[1]);
  }
  if (isNaN(q.w) || isNaN(q.el)) {
    reply(resp, 400, { error: "expected ?w=<watts>&el=<degrees>" });
    return;
  }
  updatePv(q.w, q.el);
  reply(resp, 200, { sunOk: state.sunOk, pumpOn: state.pumpOn });
});

HTTPServer.registerEndpoint("status", function (req, resp) {
  reply(resp, 200, { cfg: CFG, state: state, now: now() });
});

// Start safe: pump off until fresh PV data confirms enough sun
setPump(false);
Timer.set(60000, true, tick);
