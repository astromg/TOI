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
the app logs an error and exits without opening a window. All local configuration lives in
`toi_config.yaml`.

There is no build step, linter config, or automated test suite wired up (pylint is a listed dependency but
unconfigured). The `test_geometry_*.py` files at the repo root are standalone manual diagnostic scripts for
debugging Qt window-positioning bugs (esp. under Wayland) — run directly with `python3 test_geometry_v3.py`,
not via pytest. There is no CI. Verify changes by launching the app and exercising the affected window(s).

For dead-code checks, run linters ad hoc without adding them to the project: `uvx ruff check --select
F401,F841,F811 .` and `uvx --from vulture python -m vulture . --exclude 'test_geometry_*,PyQtX'` (the plain
`uvx vulture` launcher fails on macOS without `realpath`). Treat vulture's "unused attribute" hits with care:
`ReportWindow.report()` in `obs_gui.py` reads a list of `TOI` attribute names via `eval` and dumps them to
`telemetry.txt`, and `claude_report.py` reads attributes via `getattr`, so string references are real uses.
Assignments to `mousePressEvent`, attributes of `ephem` bodies (`_ra`, `_dec`, `_epoch`, `horizon`), and
window references kept on `self` only to prevent garbage collection are also not dead.

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
`obs_gui.py` (`ObsGui`), `instrument_gui.py` (`InstrumentGui`, `CCDGui`) and `plan_gui.py` (`PlanGui`).
`BaseAsyncWidget` provides:
- `add_background_task(coro, group=...)` — register a coroutine to run as an `asyncio.Task` once
  `run_background_tasks()` is called (typically from `on_start_app()`). Long-lived polling/monitoring loops
  (mount connection, telemetry, almanac, NATS subscriptions) are registered this way, grouped so they can be
  stopped together (`stop_background_tasks()`), e.g. when switching telescopes or closing a window.
- `add_subscription(...)` / `add_subscription_client_side(...)` — subscribe to a NATS/cycle-query address
  with sync or async callbacks, tracked so they can be cleanly stopped.
- `get_request()` / `put_base_request()` — the standard wrappers for GET/PUT calls through `client_api`,
  with consistent logging and exception handling for `CommunicationRuntimeError`/`CommunicationTimeoutError`.
  They currently have no callers (their only user, `pery_gui.py`, was removed); the live code talks to
  hardware through `ocaboxapi` component objects (`aget_*`/`aput_*`/`asubscribe_*`) and NATS readers.
- Every subclass must implement `on_start_app()` (abstract) — this is where a window kicks off its
  background tasks and does async initialization after construction (Qt widgets can't have async `__init__`).

**What kills the app (no `sys.excepthook` is installed yet):** an exception escaping a *plain* Qt slot or a Qt
virtual override (`paintEvent`, `QThread`/worker `run`, …) makes PyQt6 call qFatal → `Aborted (core dumped)`.
In an `@qs.asyncSlot` coroutine or a background task it only prints a traceback. A NATS reader whose
`try` wraps the whole `async for` dies silently on its first bad message — put a per-message `try` inside the
loop (see `nats_weather_loop`, `nats_safety_reader`). `tpg` calls `sys.exit()` on bad input, so `TPG_Worker.run`
catches `SystemExit` — without that the whole process silently exits with code 0. `plan_gui.py` has no
`asyncSlot`s, so every plan-window button is a plain slot. When inserting OBs into a running plan, shift
`current_i`/`next_i` (see `AddWindow.save_ob`, `loadPlan`). Open crash items are tracked in the knowledge-base
note "TOI Crash Review 2026-10-14".

`BaseWindow` (`base_window.py`) is a much simpler, unrelated base class used by windows that don't need
async behavior (popups, plot/report windows) — it just defers `setGeometry()` until `showEvent` so windows
that are created hidden get positioned correctly once shown.

### GUI window map
`TOI` (in `toi.py`) is the top-level widget that owns one instance of each major window/controller:
- `mnt_gui.py` (`MntGui`) — mount control (slew, track, park), uses `BaseAsyncWidget` subscriptions.
- `obs_gui.py` (`ObsGui`, `CzuwakWindow`) — main observation window. Its operator message box (`msg_e`) is
  filled only from the `tic.status.<tel>.toi.log` subscription, so operator-visible messages go through
  `TOI.update_log(...)` (the old `TOI.msg()` was a no-op and has been removed). `CzuwakWindow` ("watcher") is
  still constructed as `TOI.czuwakGui`, but all code that used it is commented out.
- `instrument_gui.py` (`InstrumentGui`, `CCDGui`) — camera/instrument control, including CCD tab.
- `plan_gui.py` (`PlanGui`, huge file, ~2000+ lines) — observation plan/queue manager: load/edit/reorder
  observing blocks (OBs), talks to `tpg` (`TelescopePlanGenerator`) and `ctc` (`CycleTimeCalc`, cycle-time
  estimation) external libraries, and to `pyaraucaria.obs_plan.obs_plan_parser`/`ob_validator` for parsing
  and validating OB definitions (see `Plans/*.txt` for the plan file format).
- `sky_gui.py` (`SkyGui`, `SkyView`) — sky-position radar/visualization of telescope pointing.
- `fits_gui.py` (`FitsWindow`, `FFS_Worker`) — FITS viewer; runs `ffs_lib` star-detection stats in a
  separate `QThread` (`FFS_Worker`) so image analysis doesn't block the Qt main thread.
- `aux_gui.py` (`AuxWindow`) — one window with tabs, in order: Telescope (the active telescope's
  OCA manual page fetched over HTTP from the intranet, `toi.oca_manual_url`), Optical path (`SchematicView`, hidden when the
  telescope has no optical graph), Calibration, Focus, Guider (layout template only, guider does not work),
  Plan Runner, Conditions (combo: FWHM / zero point of all telescopes; drawn only while the tab is shown).
  `TOI` keeps the old names for the tabs: `focusGui` (`FocusTab`), `flatGui` (`CameraCalibration`), `guiderGui`
  (`GuiderTab`), `planrunnerGui` (`PlanrunnerTab`), `conditionsGui` (`ConditionsTab`). The observation window
  has no buttons for these any more; a closed Aux or FITS window is reopened from the ⚙ menu in `ObsGui`. Tabs are pages of a
  `QTabWidget` — never call `show()` on one (it paints over the current tab); use `auxGui.show_tab(page)`.
  Tabs come up by themselves: M3 changing port → Optical path (`m3_update` → `auxGui.m3_moved`), a
  SKYFLAT/DOMEFLAT or FOCUS OB starting → Calibration / Focus (`nats_toi_ob_status_reader` → `auxGui.ob_started`,
  map `AuxWindow.OB_TABS`); the first reading after a telescope switch never switches.
  Calibration (`CalibrationTab`) has one page per kind of instrument (`camera` → `CameraCalibration`,
  `spectrograph` → `SpectrographCalibration`, still empty); each instrument tab class in `instrument_gui.py`
  declares `calibration = "camera"|"spectrograph"`, and `InstrumentGui.instrument_changed` switches the page.
  `CameraCalibration` shows last evening/morning sky flats and science per filter from the flat_overwatch
  subjects (`toi.flat_overwatch_subject` in `toi_config.yaml`, read by `reader_nats_flat_overwatch(item)`),
  kept per telescope in `flat_records`; the TPG window's "Make SKYFLATS" switch turns those records into the
  `flat_history` passed to tpg (`TPGWindow._flat_history`). Autofocus fits use `pyaraucaria.focus`
  (`calcFocus/calc_focus.py` is the old local version). In the Focus tab Recalculate only computes; SET
  (`focus_set_result`) moves the focuser. Autofocus uses a camera (`FocusTab.set_camera`, from the instrument
  window's camera tabs) and its filters from `TOI.instrument_filters` (today the telescope's wheel).
- Focus auto-adjust (in `toi.py`) — every focuser move made by TOI must go through
  `focus_move(tel, pos, source)` (not a bare `aput_move`), because it also publishes the adjust baseline to
  `tic.status.<tel>.toi.focus_reference`. Adjust target = reference position + Δ`focus_model` since the
  reference was set. See README "FOCUS ADJUST".

Shared, non-GUI helpers live in `toi_lib.py` (OB/sequence parsing, coordinate/time conversions, almanac,
icon helpers) and are imported with `from toi_lib import *` throughout — check there before adding a
duplicate helper.

### PyQt5→PyQt6 compatibility shim
Code imports Qt classes from `PyQtX` (`from PyQtX import QtWidgets, QtCore`, etc.), never directly from
`PyQt6`. `PyQtX/QtWidgets.py`, `QtGui.py`, `QtCore.py` re-export `PyQt6.*` and patch back in PyQt5-style
enum aliases (e.g. `QFrame.NoFrame`, `QTableWidget.SelectRows`) that PyQt6 moved behind scoped enums. When
adding new Qt code, import through `PyQtX`, and if an old-style unscoped enum constant is missing, add the
alias in the relevant `PyQtX/Qt*.py` file rather than switching that one call site to `PyQt6` directly.

### Configuration
**`toi_config.yaml`** — loaded directly in `toi.py`/GUI modules as `local_cfg`; per-telescope operational
settings (data directories, log file paths, light-controller IPs, NATS host/port, CTC parameters). Telescope
and service configuration published by TIC comes from `observatory_model` (`get_client_configuration()`,
`get_telescopes_configuration()`). The old `settings.py`/`configuration/settings.py`/`config_service.py`
layer (`OCA_ADDRESS_DICT` with `sim.*` addresses) was removed together with `pery_gui.py`, its only user.

### External/private dependencies
`pyaraucaria`, `ocabox`, `ocabox-common`, `ctc`, and `tpg` (the last two imported as `ctc`/`tpg` packages)
are pulled from private `araucaria-project` GitHub repos or a local sibling path (`tpg`) per
`pyproject.toml` — their source isn't in this repo. When code behaves unexpectedly at the boundary with
`ocaboxapi`, `obcom`, `pyaraucaria`, `tpg`, or `ctc`, check the installed package version/source rather
than assuming the logic lives here.
