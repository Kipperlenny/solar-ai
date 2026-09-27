// Pool pump solar control for Shelly Gen2+/Gen3 plugs
// Runs an on/off cycle only while the sun is strong enough to heat a solar
// collector. Otherwise the pump stays off, because wind would cool the water
// in the collector.
//
// Sun source: PV input power of a PV system with the same orientation,
// pushed by solar_hub.py every minute:
//   http://<plug-ip>/script/<id>/pv?w=<watts>
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
  maxPvAgeSec: 300
};
// CONFIG-END

let state = {
  sunOk: false,
  pvW: null,
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

function updatePv(w) {
  state.pvW = w;
  state.lastPvTs = now();
  if (!state.sunOk && w >= CFG.onW) state.sunOk = true;
  if (state.sunOk && w < CFG.offW) state.sunOk = false;
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
  let q = req.query || "";
  let w = q.indexOf("w=") === 0 ? Number(q.slice(2)) : NaN;
  if (isNaN(w)) {
    reply(resp, 400, { error: "expected ?w=<watts>" });
    return;
  }
  updatePv(w);
  reply(resp, 200, { sunOk: state.sunOk, pumpOn: state.pumpOn });
});

HTTPServer.registerEndpoint("status", function (req, resp) {
  reply(resp, 200, { cfg: CFG, state: state, now: now() });
});

// Start safe: pump off until fresh PV data confirms enough sun
setPump(false);
Timer.set(60000, true, tick);
