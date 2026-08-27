# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TOI (Telescope Operator Interface) is a PyQt6 desktop GUI application used by telescope operators at an
observatory (OCA — telescopes `wk06`, `zb08`, `jk15`) to control mounts, domes, instruments, and observation
plans in real time. It talks to observatory hardware/services via a NATS-based messaging backend
(`serverish` Messenger) and the `ocaboxapi`/`obcom` client libraries (private `araucaria-project` git repos
pulled in as dependencies, not vendored in this repo). Comments, variable names, and commit messages are a
mix of Polish and English — this is normal and not a localization bug.

## Running the app

Requires Poetry and Python 3.11–3.14.

```
poetry install
poetry run toi          # or: ./toi.py
poetry run nw           # runs nats_watch.py (standalone NATS message inspector)
```

The app reads `toi_config.yaml` (telescope list, NATS host/port, per-telescope paths) from the current
working directory at startup, and connects to NATS before building any GUI — if the NATS connection fails,
the app logs an error and exits without opening a window. Local machine/site overrides go in
`configuration/settings.py` (imported by `settings.py`, which falls back silently if that file doesn't
exist — see `config_service.py`'s `Config.get()` for how settings are read elsewhere in the code).

There is no build step, linter config, or automated test suite wired up (pylint is a listed dependency but
unconfigured). The `test_geometry_*.py` files at the repo root are standalone manual diagnostic scripts for
debugging Qt window-positioning bugs (esp. under Wayland) — run directly with `python3 test_geometry_v3.py`,
not via pytest. There is no CI. Verify changes by launching the app and exercising the affected window(s).

## Architecture

### Entry point and app lifecycle
`toi.py` is the main module (large — the file is a monolith containing most core app/telescope logic plus
the `TOI` class and `main()`). Startup sequence in `run_qt_app()`:
1. Load `toi_config.yaml`.
2. Open a `Messenger` connection to NATS.
3. Build an `Observatory` model from `ocaboxapi` (`observatory_model.load_client_cfg()`), which yields the
   `client_api` (`BaseClientAPI`) used for all subsequent hardware communication.
4. Construct `TOI(...)`, which builds every sub-GUI window, then call `await toi.on_start_app()`.

`main()` runs everything under `qasync` (`qs.run(...)`), so **all GUI code shares one asyncio event loop**
with Qt's event loop — this is the single most important thing to know before touching any GUI or network
code here (see below).

### The async-Qt integration pattern
Almost every stateful window subclasses **both** a Qt widget and `BaseAsyncWidget`
(`base_async_widget.py`), using `metaclass=MetaAsyncWidgetQtWidget` to resolve the diamond metaclass
conflict between Qt and Python's `ABC`. This pattern repeats in `toi.py` (`TOI`), `mnt_gui.py` (`MntGui`),
`obs_gui.py` (`ObsGui`), `instrument_gui.py` (`InstrumentGui`, `CCDGui`), `plan_gui.py` (`PlanGui`), and
`pery_gui.py` (`PeryphericalGui`). `BaseAsyncWidget` provides:
- `add_background_task(coro, group=...)` — register a coroutine to run as an `asyncio.Task` once
  `run_background_tasks()` is called (typically from `on_start_app()`). Long-lived polling/monitoring loops
  (mount connection, telemetry, almanac, NATS subscriptions) are registered this way, grouped so they can be
  stopped together (`stop_background_tasks()`), e.g. when switching telescopes or closing a window.
- `add_subscription(...)` / `add_subscription_client_side(...)` — subscribe to a NATS/cycle-query address
  with sync or async callbacks, tracked so they can be cleanly stopped.
- `get_request()` / `put_base_request()` — the standard wrappers for GET/PUT calls through `client_api`,
  with consistent logging and exception handling for `CommunicationRuntimeError`/`CommunicationTimeoutError`.
  Prefer these over calling `client_api` directly when adding new hardware calls.
- Every subclass must implement `on_start_app()` (abstract) — this is where a window kicks off its
  background tasks and does async initialization after construction (Qt widgets can't have async `__init__`).

`BaseWindow` (`base_window.py`) is a much simpler, unrelated base class used by windows that don't need
async behavior (popups, plot/report windows) — it just defers `setGeometry()` until `showEvent` so windows
that are created hidden get positioned correctly once shown.

### GUI window map
`TOI` (in `toi.py`) is the top-level widget that owns one instance of each major window/controller:
- `mnt_gui.py` (`MntGui`) — mount control (slew, track, park), uses `BaseAsyncWidget` subscriptions.
- `obs_gui.py` (`ObsGui`, `CzuwakWindow`) — main observation window; `CzuwakWindow` ("watcher") is a
  cross-telescope status/alert monitor.
- `instrument_gui.py` (`InstrumentGui`, `CCDGui`) — camera/instrument control, including CCD tab.
- `plan_gui.py` (`PlanGui`, huge file, ~2000+ lines) — observation plan/queue manager: load/edit/reorder
  observing blocks (OBs), talks to `tpg` (`TelescopePlanGenerator`) and `ctc` (`CycleTimeCalc`, cycle-time
  estimation) external libraries, and to `pyaraucaria.obs_plan.obs_plan_parser`/`ob_validator` for parsing
  and validating OB definitions (see `Plans/*.txt` for the plan file format).
- `sky_gui.py` (`SkyGui`, `SkyView`) — sky-position radar/visualization of telescope pointing.
- `fits_gui.py` (`FitsWindow`, `FFS_Worker`) — FITS viewer; runs `ffs_lib` star-detection stats in a
  separate `QThread` (`FFS_Worker`) so image analysis doesn't block the Qt main thread.
- `focus_gui.py` / `calcFocus/calc_focus.py` — autofocus routine; fits sharpness vs. focuser-encoder
  position (methods: `rms`, `rms_quad`, `lorentzian`) across a sequence of FITS frames.
- `flat_gui.py`, `guider_gui.py`, `planrunner_gui.py`, `conditions_gui.py` — flat-fielding, guider,
  plan-runner (automated execution) status, and weather/seeing conditions windows respectively.
- `pery_gui.py` — peripherals (lights, M3 mirror, dome flats), not currently instantiated from `TOI`.
- `aux_gui.py` — an older bundle of window classes (`AuxGui`, `FlatGui`, `FocusGui`, `GuiderGui`, ...) mostly
  superseded by the dedicated `*_gui.py` modules above; not imported by `toi.py` (import is commented out).
  Check before extending — it may be dead code or a reference implementation.

Shared, non-GUI helpers live in `toi_lib.py` (OB/sequence parsing, coordinate/time conversions, almanac,
icon helpers) and are imported with `from toi_lib import *` throughout — check there before adding a
duplicate helper.

### PyQt5→PyQt6 compatibility shim
Code imports Qt classes from `PyQtX` (`from PyQtX import QtWidgets, QtCore`, etc.), never directly from
`PyQt6`. `PyQtX/QtWidgets.py`, `QtGui.py`, `QtCore.py` re-export `PyQt6.*` and patch back in PyQt5-style
enum aliases (e.g. `QFrame.NoFrame`, `QTableWidget.SelectRows`) that PyQt6 moved behind scoped enums. When
adding new Qt code, import through `PyQtX`, and if an old-style unscoped enum constant is missing, add the
alias in the relevant `PyQtX/Qt*.py` file rather than switching that one call site to `PyQt6` directly.

### Configuration layers
There are two independent, similarly-named config mechanisms — don't conflate them:
1. **`toi_config.yaml`** — loaded directly in `toi.py`/GUI modules as `local_cfg`; per-telescope operational
   settings (data directories, log file paths, light-controller IPs, NATS host/port, CTC parameters).
2. **`settings.py` / `configuration/settings.py` via `config_service.Config.get(name, default)`** — Python
   constants (`OCA_ADDRESS_DICT` mapping logical method names to Alpaca-style address strings,
   `OBSERVATORY_COORD`, `ALPACA_BASE_ADDRESS`). `configuration/settings.py` is a git-ignored local override
   file (see the `try/except ImportError` in `settings.py`); it won't exist on a fresh checkout.

### External/private dependencies
`pyaraucaria`, `ocabox`, `ocabox-common`, `ctc`, and `tpg` (the last two imported as `ctc`/`tpg` packages)
are pulled from private `araucaria-project` GitHub repos or a local sibling path (`tpg`) per
`pyproject.toml` — their source isn't in this repo. When code behaves unexpectedly at the boundary with
`ocaboxapi`, `obcom`, `pyaraucaria`, `tpg`, or `ctc`, check the installed package version/source rather
than assuming the logic lives here.
