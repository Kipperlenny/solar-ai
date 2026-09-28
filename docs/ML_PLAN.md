# Machine learning plan

Status: plan only, nothing built yet (2026-09-28).

## Why, and why not everything

The investment simulation (`tools/simulate.py`) stays deterministic: it replays
measured data and needs no model. Machine learning is worth it where we have to
*predict* or *recognise* something the sensors don't tell us:

| # | Goal | Why it helps | Needs |
|---|---|---|---|
| 1 | Forecast PV and consumption for the next 48 h | Decide tonight: charge the car from the grid or wait for tomorrow's sun; plan boiler and pool; show "tomorrow" on the dashboard and bulb | History (have), weather forecast (Open-Meteo) |
| 2 | Recognise car charging in the history | Put the car into the investment simulation as a flexible load worth the fuel it replaces instead of a fixed one | 3-4 weeks of `logs/wallbox.csv` as labels |
| 3 | Detect unusual days | Better than today's rule for vacations/visitors; spot a faulty device or the inverter getting hotter than usual | History, `logs/inverter.csv` |

Later, once 1 and 2 work: suggest (not execute) the cheapest charging plan for
the car for the next days.

## Data

- `logs/fusionsolar.csv`: 5-minute PV, consumption, grid since 2025-10-13
- `logs/wallbox.csv`: wallbox counter/power since 2026-09-28 (labels for #2)
- `logs/inverter.csv`: inverter temperature, voltage, power since 2026-09-28
- `logs/hub.csv`: 1-minute PV/load while the PC runs, tariff period, device states
- `[[events]]` in `config.toml`: marked vacations/visitors (labels for #3)
- Weather: Open-Meteo archive (history) and forecast API, free, no key; gets
  the coordinates from `.env` (rounded to ~1 km)
- Calendar features: hour, weekday, month, holidays (`tariff.py`), sun
  position (`sun.py`)

## Models

1. **Forecast** - gradient boosted trees (LightGBM) per 15-minute step, one
   model for PV (features: forecast irradiance/cloud cover/temperature, sun
   elevation and azimuth, clear-sky PVGIS value, inverter limit) and one for
   consumption without the car (features: time, weekday, temperature, events).
   Baseline to beat: "same as yesterday" and PVGIS x weather. Metric: MAE of the
   daily kWh and of the evening P1 hours; backtest over the whole history with
   rolling origin (train on the past only).
2. **Car charging recognition** - classifier per 5-minute step (charging /
   not charging) plus power estimate, features: load level and steps, time of
   day, PV surplus. Train on the weeks with wallbox data, check against the
   wallbox's energy counter, then label
   the history before. Metric: kWh per day vs. the counter.
3. **Unusual days** - residual of model 1 (actual minus forecast consumption)
   over several days; flag runs, confirm in `[[events]]`. For the inverter:
   temperature vs. power and room temperature, flag drifts.

No deep learning: ~100,000 rows fit gradient boosting on a CPU in seconds.
The RTX 5080 is only worth it if we ever try sequence models on years of data.

## Environment

Windows Smart App Control blocks the compiled parts of pandas and
scikit-learn in the Windows venv, so the ML runs in **WSL Debian**:

- Python venv in WSL with pandas, scikit-learn, LightGBM (CUDA optional)
- Reads the CSVs from `logs/` via `/mnt/c/...` (read-only)
- Writes results as JSON to `logs/ml/` (`forecast.json`, `car_history.csv`,
  `anomalies.json`); the hub on Windows only reads them for the dashboard
- Runs from a scheduled task (forecast every 3 h, retraining weekly)

No device is ever controlled by a model directly; the Shelly rules stay as
they are. Everything stays on the PC; only the weather API sees the rounded
coordinates.

## Order and timing

1. WSL environment + weather history download (1 evening)
2. Forecast model + backtest + dashboard card "next 48 h" (1-2 evenings)
3. After ~4 weeks of wallbox data: car recognition, then the car as flexible
   load in the simulation
4. Unusual-day detection from the forecast residuals
5. Charging plan suggestions

## Open questions

- Is the car at home during the day on weekdays? (limits how much charging can
  move to the sun)
- Room temperature near the inverter: a Shelly H&T sensor would help model 3
- Retrain monthly or when the error grows?
