# Solar AI

Use your own PV production to run household loads at the right time – with
a Huawei inverter, a few Shelly devices and a small Python hub.

- **Pool pump** behind a solar collector: runs only in strong sun.
- **Electric hot water boiler**: heats from surplus during the day, is
  always hot in the evening, off at night, with a legionella safeguard.
- **Color bulb** as a traffic light: shows whether there is surplus or how
  expensive grid power is right now.

Works alongside a wallbox that charges from surplus (e.g. Huawei FusionSolar
"surplus charging") without reading or controlling it.

## How it works

```
Huawei SDongle ──Modbus read──> solar_hub.py ──HTTP──> Shelly plug + script  (pool pump)
                                 every 60 s     ├──> Shelly plug + script  (boiler)
                                                └──> Shelly Color Bulb     (indicator)
```

[solar_hub.py](solar_hub.py) reads the total PV input power and the house
load from the SDongle (unit 100, registers 37498/37500) and pushes them to
the scripts running on the Shelly plugs. **The plugs decide themselves** and
fall back to safe behaviour when the hub is not running – so the hub can run
on a PC that is not on 24/7. Every minute a row goes to `logs/hub.csv`.

The inverter is only **read** (Modbus function code 03). Nothing is ever
written to it.

## Hardware

| Device | Used for | Tested with |
|---|---|---|
| Huawei SUN2000 inverter + SDongle | PV power and house load | SUN2000-6KTL-L1, SDongle with Modbus TCP enabled |
| Shelly Gen2+/Gen3 plug with scripting | pool pump, boiler | Shelly Outdoor Plug S Gen3 (16 A) |
| Shelly Color Bulb (Gen1) | indicator | SHCB-1, firmware 1.14.0 |

Each device is optional: leave its host empty in `.env` and it is skipped.

## Setup

1. Give every device a fixed IP in your router.
2. Install:

   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   copy .env.example .env
   ```

3. Fill in `.env`: device IPs and a new password per Shelly device.
4. Secure the Shelly plugs (sets the password and protects the setup access
   point) and upload their scripts:

   ```powershell
   .venv\Scripts\python tools\shelly_secure.py boiler
   .venv\Scripts\python tools\shelly_deploy.py boiler
   ```

   For the Color Bulb, set a password in its web interface or app.
5. Test the hub in the foreground, then install it as a Windows task that
   starts at logon:

   ```powershell
   .venv\Scripts\python solar_hub.py
   powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1
   ```

## Configuration

All settings are in [config.toml](config.toml) and commented there. The
`[pool]` and `[boiler]` sections are written into the Shelly scripts by
`tools/shelly_deploy.py`, so redeploy after changing them. For everything
else restart the hub.

### Pool pump – [shelly/pool_pump_solar.js](shelly/pool_pump_solar.js)

A collector only heats the pool in strong sun; otherwise wind cools the
water. The pump cycles (default 1 min on / 3 min off) while PV >= `onW` and
stops below `offW`. PV power of a system with the same orientation is a
better sun sensor than a weather model. Without hub data for 5 minutes the
pump stays off.

### Boiler – [shelly/boiler_solar.js](shelly/boiler_solar.js)

| Time (defaults) | Behaviour |
|---|---|
| 23:00–09:00 | off |
| 09:00–16:00 | surplus: switch on at PV >= 2 kW, wait 2 min, switch off again (retry after 15 min) if the grid still has to deliver > 300 W |
| 16:00–23:00 | always on, the boiler's thermostat regulates – full before the evening showers |

The plug can't measure the water temperature, so the logic is deliberately
pessimistic: the tank is always full in the evening, and if it wasn't full
(thermostat cut off) for 24 h it heats outside the night. Without hub data
it heats from 12:00. Set the plug's "power on" state to *on*, so the boiler
works after a power cut even if the script doesn't.

**Surplus-charging wallbox:** such a wallbox absorbs all surplus, so the
surplus can't be computed. Huawei wallboxes also can't be read via Modbus
(the vendor doesn't support it). The boiler therefore simply tries: it
switches on, gives the wallbox time to regulate down and checks the grid
import (house load minus PV).

### Color bulb – indicator in [solar_hub.py](solar_hub.py)

| State | Day | Dark (PV below 400 W) |
|---|---|---|
| surplus: export >= 2 kW, enough for a dryer | very dark green | cool white |
| cheapest tariff period | bright green | cool white |
| middle tariff period | bright yellow/orange | neutral white |
| most expensive period, PV >= 2 kW but no export (e.g. wallbox charging) | orange | warm white |
| most expensive period, no PV | dark red | warm white |

In the dark the bulb is a normal lamp at full brightness and shows the state
only as color temperature: it can't mix its white LEDs with color, and RGB
white is too dim. The bulb is powered through the wall switch; after
switching it on it gets its color within a few seconds.

### Tariff – [tariff.py](tariff.py)

Periods, holidays and prices come from `[tariff]` in config.toml. The
defaults are the Spanish 2.0TD tariff (P1 punta, P2 llano, P3 valle; weekends
and fixed-date national holidays are P3).

## Files

| Path | Purpose |
|---|---|
| `solar_hub.py` | the hub |
| `config.toml`, `config.py` | settings |
| `tariff.py` | tariff periods |
| `shelly/*.js` | scripts running on the Shelly plugs |
| `tools/shelly_deploy.py` | upload a Shelly script with its settings |
| `tools/shelly_secure.py` | set password and protect the setup AP of a new Shelly |
| `tools/install_windows_task.ps1` | run the hub at logon |
| `logs/hub.csv` | one row per minute: PV, load, tariff, device states |

Script status on a plug: `http://<plug>/script/<id>/status` (user `admin`).

## History

This project started as a controller that mined crypto on the GPU with solar
surplus. That code was removed; it is still in the git history.

## License

CC BY-NC-SA 4.0, see [LICENSE](LICENSE).
