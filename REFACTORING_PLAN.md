# TOI Refactoring Plan

> Telescope Operator Interface — plan to remove hardcoded state, retire `ephem`
> without slowing calculations, lean on `pyaraucaria`/`ctc`, and re-architect the
> data layer for smooth, observable, reliable operation **with identical
> functionality**.
>
> Status: proposal for review. Sections marked **[GO DEEP]** are settled and
> spelled out for direct implementation. Sections marked **[DISCUSS]** are forks
> that need a decision before implementation — each carries a recommendation.

---

## 0. Orientation

### What TOI is today
One file, `toi.py` (4430 lines), is the whole application: a single
`class TOI(QWidget, BaseAsyncWidget)` that is simultaneously the GUI root, all
telescope business logic, ~30 NATS reader coroutines, ~35 subscription
callbacks, and 5 polling loops. Child windows (`mnt_gui`, `plan_gui`,
`obs_gui`, …) read app state through `self.parent.<attr>` and are fed by TOI's
callbacks pushing values into their widget fields.

### The five structural problems (root causes, not symptoms)

1. **Three overlapping data paths deliver the same values.**
   - **Path A — ocabox component subscriptions** (`toi.py:605-652`,
     `self.mount.asubscribe_ra(self.ra_update)`, …). But **every callback
     ignores the pushed value and re-fetches** with a blocking `aget_*()`
     round-trip — e.g. `ccd_current_temp_update` (`toi.py:2830-2831`) does
     `self.ccd_temp = await self.ccd.aget_ccdtemperature()`, and
     `ccd_gain_update` (`toi.py:2852-2854`) fetches *twice*. The subscription is
     reduced to a doorbell; each change costs an extra round-trip and blocks the
     callback.
   - **Path B — raw NATS readers** (`oca_telemetry_reader`, `toi.py:230`) read
     `tic.status.{tel}.mount.motorstatus`, `.covercalibrator.coverstate`, … off
     JetStream directly for *all* telescopes, bypassing the ocabox client cache
     entirely.
   - **Path C — `base_async_widget` raw addresses** (`base_async_widget.py`):
     child GUIs talk straight to `client_api` using dotted strings from
     `OCA_ADDRESS_DICT` (`configuration/settings.py:10-41`), opening their *own*
     per-widget cycle-queries — including `add_subscription_client_side`
     (`base_async_widget.py:78`) which is an **unconditional `PeriodicCycleQuery`
     poll**. Same value (e.g. mount motorstatus) arrives via A *and* B.

2. **Telescope switching tears down and rebuilds everything**
   (`telescope_switched`, `toi.py:469-695`): stop ~35 fire-and-forget
   subscription tasks (bounded by 2.5 s / 1 s-each close timeouts),
   `dischard_cached_telescope` to force a full re-fetch, then sequentially
   `await` ~35 fresh `asubscribe_*` handshakes, then sequential `updateUI()`
   calls that each trigger the fresh-`aget` callbacks from (1). The discard is a
   documented workaround (`toi.py:568-570`) for "callbacks not firing after
   switching a few times".

3. **Plan state is duplicated between model and view.** Authoritative plan
   lives in `toi.py` (`self.plan[tel]`, `self.current_i[tel]`, `self.next_i[tel]`);
   `PlanGui` keeps shadow copies (`self.plan/self.i/self.prev_i/self.next_i`,
   `plan_gui.py:64-69`). Edit operations read the shadow index but mutate the
   real model — with real corruption bugs (§4).

4. **`ephem` is woven through 5 files** for astronomy *and* as a datetime/angle
   library (`ephem.Date`, `ephem.second/minute/hour`, `ephem.pi`). The obvious
   replacement — `pyaraucaria.coordinates.ra_dec_2_az_alt` etc. — **is itself an
   `ephem` wrapper** (`pyaraucaria/coordinates.py:17`), so it removes nothing.
   The migration branch swapped in per-object `astropy` transforms, which are
   correct but ~10-100× slower per call, hence the reported slowdown.

5. **Hardcoding and inconsistency.** Observatory coordinates appear **four times
   with three different values**, including a wrong European placeholder
   (`configuration/settings.py:3` `("48.3","14.28","1000")`). Telescope lists,
   instrument option sets, dome geometry, and limits are baked into `if
   active_tel == "wk06"` branches.

### Guiding principles (from the shared Quality Philosophy)
- Beautiful, maintainable code first; running is a side effect.
- No dirty hacks or backward-compat shims. Fix root causes.
- Minimum complexity for current requirements — no premature abstraction.
- Validate only at boundaries; single source of truth for shared state.
- Preserve the authors' voice and the code's readability. Keep the Polish
  domain vocabulary where it carries meaning; translate only where it obscures.
- **Behaviour must not change.** Every phase is independently shippable and
  verifiable against the current app.

---

## 1. Data layer — subscriptions, cache, redundancy, switching

This is the highest-value area: it drives the instability, the latency, the
redundancy, and the slow telescope switch all at once.

### 1.1 [GO DEEP] Make subscription callbacks consume the pushed value

**Problem.** Callbacks discard the value the subscription delivered and issue a
fresh blocking `aget_*()`. This is the "cache-skipping construction."

**The ocabox contract.** A subscription callback receives
`List[ValueResponse]`; the changed value is `event[0].value.v` (see
`base_async_widget.py:110-115`, the existing `update_field_callback`, which
already does this correctly). The component's local cache is *also* updated by
the same subscription (`ocabox/ocaboxapi/component.py:120`), so `aget_*()` after
a push is redundant even when it "works".

**Change.** For each `*_update(self, event)` callback that currently re-fetches,
read the value from `event` instead. Concretely, the transformation is
mechanical and identical everywhere:

```python
# BEFORE (toi.py:2830-2831)
async def ccd_current_temp_update(self, event):
    self.ccd_temp = await self.ccd.aget_ccdtemperature()

# AFTER
async def ccd_current_temp_update(self, event):
    if event and event[0].value is not None:
        self.ccd_temp = event[0].value.v
```

Apply to every callback in this class that follows the re-fetch pattern.
Inventory to fix (verified locations; confirm each before editing):
`ccd_current_temp_update` (2830), `ccd_set_temp_update` (2834),
`ccd_gain_update` (2852 — delete *both* fetches, keep the event value),
`ccd_rm_update` (2867), `ccd_binx_update` (2883), `ccd_biny_update` (nearby),
`ccd_camerastate`-family, mount `ra_update`/`dec_update`/`alt_update`/`az_update`
(re-fetch at 3144/3148/3152/3156), `focus_update` (3721-3722),
dome callbacks (3351/3384/3398/3425), filterwheel `filter_update` (3782).

Callbacks that already read the cached property (`self.<comp>.connected` at
2903/2909/3281/3585/3765/3799) are fine — but prefer `event` for consistency.

**Helper to remove the boilerplate.** Add one small factory (next to
`update_field_callback` in `base_async_widget.py`) so simple "value → attribute"
and "value → widget field" callbacks stop being hand-written:

```python
@staticmethod
def assign_from_event(default=None):
    """Return the first pushed value from a subscription event, else default."""
    def extract(event):
        if event and event[0].value is not None:
            return event[0].value.v
        return default
    return extract
```

Callbacks that also translate the value (icon, colour, formatting) keep their
body but source the value from `event`, never from a fresh `aget`.

**Guardrail.** Add a lint/CI check (or a code-review checklist item) that flags
`await self.<comp>.aget_` *inside* an `async def *_update(self, event)` — that
pattern is the regression this fixes.

**Result.** ~35 network round-trips per change cycle eliminated; callbacks stop
blocking; a slow/timed-out `aget` can no longer leave a field un-updated. This
is a pure latency/stability win with **no behavioural change** — the displayed
values are the same values, sourced from the message that triggered the
callback.

### 1.2 [DISCUSS] Collapse the three data paths into one

**Options.**

- **(A) Unify on the ocabox component tree.** Delete Path B (`oca_telemetry_reader`
  for values already available via components) and Path C
  (`base_async_widget.add_subscription`/`add_subscription_client_side`/`get_request`
  against `OCA_ADDRESS_DICT`). Every live value comes from one
  `asubscribe_*` per datum; widgets read the shared component cache via
  `aget_*` (cheap, local) or receive pushes. `OCA_ADDRESS_DICT` and
  `ALPACA_BASE_ADDRESS` (`configuration/settings.py`) are deleted.
  - *Pros:* one mental model, one cache, coalesced polling, matches the ocabox
    design intent and the ecosystem direction. Removes the most code.
  - *Cons:* the multi-telescope overview (Path B reads *all* telescopes at once
    for the switcher/overview) needs an explicit design — components are
    per-focused-telescope. Requires a small "all-telescopes status" concept.

- **(B) Introduce a `TelemetryStore` monitor abstraction.** A dedicated,
  non-GUI layer owns all subscriptions and exposes an observable store keyed by
  `(tel, address)`; widgets subscribe to the store, never to ocabox directly.
  Path B's multi-telescope needs fit naturally (the store holds all telescopes).
  Uses the stdlib `Observable[T]` pattern already ratified for ocabox-server
  (see vault: *Observable Pattern for ocabox-server*).
  - *Pros:* clean separation of monitor vs view (the single biggest structural
    debt); natural home for multi-telescope state, reconnection, and logging;
    testable without Qt.
  - *Cons:* more up-front work; a genuine new abstraction (weigh against
    "minimum complexity").

- **(C) Minimal:** do only §1.1 + delete the unconditional `PeriodicCycleQuery`
  poll (`add_subscription_client_side`), leave the rest.

**DECIDED (2026-07): B — a thin, forward-compatible `TelemetryStore`, client-side
in TOI, with only small bug/ergonomics fixes upstream in ocabox.**

Rationale, given the constraint that ocabox is heading toward a NATS-native
protocol (vault: *Future NATS-native TIC*) and must not get a big refactor now:

- The store lives **in TOI** and holds the current value of every subscribed
  address for **all telescopes**, keyed by `(tel, address)`, built on the
  ratified stdlib `Observable[T]` (not a reactive framework). Widgets subscribe
  to the store; they never touch ocabox directly.
- **Its interface is deliberately the "simple, powerful client interface" shape**
  the ocabox project wants: *"subscribe once → always-current, self-healing view
  of values → read synchronously."* That shape is **backend-agnostic and
  survives the NATS migration**: today the store is filled by ocabox component
  subscriptions; tomorrow the same store is filled by NATS-native subjects, with
  **zero change to TOI widget code**. So this is a stepping stone toward, not a
  detour from, the NATS-native direction.
- **Upstream ocabox work is limited to bug/ergonomics fixes that help every
  client and are neutral to the NATS migration** — do *not* build a new
  subscription-manager subsystem inside ocabox now (it would be thrown away):
  1. Fix the "callbacks stop firing after N telescope switches" bug
     (`toi.py:568-570` workaround) — benefits all ocabox clients.
  2. Make `ErrorPolicy.SERVICE` the easy default for live-telemetry subscriptions.
- If, after living with the TOI-side store, its interface proves its worth, it
  is a natural candidate to be **promoted into ocabox later** (or absorbed by
  the NATS-native client) — but that is a future, post-migration decision, not
  this refactor.

Do §1.1 first regardless (it stands alone and de-risks everything).

### 1.3 [DISCUSS] Stop the resubscribe storm on telescope switch

**Problem.** Switching rebuilds ~35 subscriptions and discards the cached
telescope object every time (`toi.py:563-674`).

**Options.**

- **(A) Keep all telescopes subscribed; switch only re-points the view.** If a
  `TelemetryStore` (§1.2-B) holds all telescopes' values continuously, switching
  is just changing which telescope the widgets render — near-instant, no
  teardown. Bandwidth cost: N telescopes × ~200 values at LAN rates, which the
  vault (*Future NATS-native TIC*) already deems fine.
- **(B) Keep discard-rebuild but fix the upstream bug and parallelize.** The
  discard is a workaround for "callbacks not firing after N switches"
  (`toi.py:568-570`). If that ocabox bug is fixed, the discard goes away; the
  ~35 `asubscribe_*` handshakes can be issued concurrently (`asyncio.gather`)
  instead of sequentially, and teardown parallelized.

**DECIDED (2026-07): A — fast switch via the store, plus fixing the upstream
ocabox bug.** Because §1.2 adopts the all-telescopes `TelemetryStore`, switching
becomes a **view re-point** (change which telescope the widgets render) — no
teardown, no rebuild, no discard. The expensive `dischard_cached_telescope`
workaround (`toi.py:568-570`) is removed once the upstream "callbacks stop
firing" bug is fixed (in scope — see §1.2). Confirm the all-telescopes
subscription bandwidth on the real LAN during P9 (the vault's *Future NATS-native
TIC* estimate of ~200 values × N telescopes at ~1 Hz says it is fine).

### 1.4 [GO DEEP] Resilient subscriptions (error policy + reconnection)

**Problem.** ocabox's `ConditionalCycleQuery` fires its callback exactly once on
a terminal error, then never again (vault: *Error Model across ocabox
ecosystem*, Bug 3). With the default `INTERACTIVE` error policy, a single
`NORMAL`-severity hiccup silently kills a subscription — the field just freezes.
This is a chief cause of "unreliable subscriptions".

**Change.**
- Pass `error_policy=ErrorPolicy.SERVICE` (self-recovering with staged backoff)
  when creating subscriptions for live telemetry, via
  `observatory.subscribe_async(..., error_policy=...)` and the component
  `asubscribe_*` path. (Confirm the parameter name against the installed ocabox;
  the vault documents it live as of ocabox 2.5.0.)
- Where a subscription can legitimately terminate (permanent 3002/4003), log it
  at WARNING with the address and *do not* silently swallow — surface a "stale"
  indicator on the affected widget (greyed value + tooltip "no updates since
  HH:MM"), reusing the existing greyed-snapshot styling in `plan_gui`.
- Add a per-subscription **staleness watchdog**: record the timestamp of the
  last callback; a lightweight timer flags any value not refreshed within
  `N × time_of_data_tolerance` as stale in the UI. (This is the missing health
  check the vault notes PMS also lacks.)

**Result.** Subscriptions self-heal; a dead one is *visible* rather than a
frozen-but-plausible number — critical for an operator trusting the display.

---

## 2. Ephemeris — remove `ephem` without slowing down

### 2.1 The finding that reframes this task

- `pyaraucaria.coordinates.ra_dec_2_az_alt`, `site_sidereal_time`,
  `az_alt_2_ra_dec`, `ra_dec_epoch`, and `dome_eq_azimuth` **are `ephem`
  wrappers** (`import ephem`, `pyaraucaria/coordinates.py:17`). "Migrate to
  pyaraucaria" via these does **not** remove `ephem`.
- `pyaraucaria.ephemeris` (Sun/Moon/Star/Stars) is pure `astropy`+`astroplan`,
  using per-object `SkyCoord.transform_to(AltAz)`; `Stars.get_ephemeris` loops
  per-timestamp. This is the slow path the migration branch hit.
- `ctc` is **not** an alt/az engine — it's an ML cycle-time predictor and itself
  depends on the `ephem`-backed pyaraucaria functions. It cannot replace `ephem`.
- **No fast pure-Python/numpy topocentric alt-az or sidereal exists in either
  library.** Only `eraCal2jd` (JD), string parse/format, and `airmass` are fast
  and `ephem`-free today.

**Therefore the real question is a library choice, not a code move.** The
slowness in the migration branch is the *per-object call pattern*, not astropy
itself — astropy's overhead is ~constant per call regardless of array size.

### 2.2 [GO DEEP] Consolidate all astronomy into one module — `toi_astro.py`

Regardless of the backend chosen in §2.3, first **centralize**. Today astronomy
is scattered across `toi_lib.py`, `toi.py`, `plan_gui.py`, `sky_gui.py`,
`conditions_gui.py`, `mnt_gui.py`. Create `toi_astro.py` exposing exactly the
operations TOI needs, backend-agnostic:

```
utc_now() -> datetime (UTC-aware)                # replaces ephem.now()
sidereal_time(obs, when) -> float hours
julian_date(when) -> float
almanac(obs, when) -> Almanac dataclass          # sun/moon alt/az/phase, rise/set
radec_to_altaz(obs, when, ra, dec) -> (az, alt)          # SCALAR
radec_to_altaz_batch(obs, when, ras, decs) -> (az[], alt[])   # VECTOR — the hot path
altaz_to_radec(obs, when, alt, az) -> (ra, dec)
precess(ra, dec, epoch) -> (ra, dec)
moon_separation(obs, when, ra, dec) -> float deg
airmass(alt_deg) -> float                        # already exists in pyaraucaria
```

- Return **plain types** (`datetime`, `float`, small dataclasses), never
  `ephem.Date`. All the `ephem.Date`/`ephem.second`/`ephem.hour` datetime
  arithmetic (`toi.py:2272-2358`, `conditions_gui.py:111-115,242-246`,
  `sky_gui.py:305-326`, `plan_gui.py` plot x-ticks) becomes ordinary
  `datetime`/`timedelta` math. The migration branch already wrote a correct
  `_jd_hourly_ticks` helper (`toi_lib.py`) — reuse that approach.
- Keep the string parse/format from `pyaraucaria.coordinates`
  (`ra_to_decimal`, `dec_to_decimal`, `ra_to_sexagesimal`, `parse_sexagesimal`)
  — these are fast and `ephem`-free; adopt them and delete TOI's local
  equivalents.
- Delete `from toi_lib import *` star-imports (`mnt_gui.py:20`, `sky_gui.py:16`)
  in favour of explicit `from toi_astro import ...`.

This module is where the `ephem`→replacement swap happens **once**, behind a
stable interface, instead of in 5 files. It also makes the whole thing unit-
testable against `ephem` as an oracle.

### 2.3 [DISCUSS] Which backend for the fast path

The hot path is `radec_to_altaz` for a whole plan (dozens of objects) on every
`update_plan` (`toi.py:2329-2358`) and every plan-table repaint, plus the
alt-vs-time plot loops (`plan_gui.py:1668-1673`).

- **(A) Batched astropy.** Compute *all* plan objects in one call:
  `SkyCoord(ra=[...], dec=[...]).transform_to(AltAz(obstime=T, location=loc, pressure=0))`.
  One transform for N objects ≈ the cost of one object. Cache the `AltAz` frame
  per timestamp; for the plot, build one time grid and transform once.
  - *Pros:* zero new dependencies (astropy already required), correct, southern-
    hemisphere-safe, refraction-explicit. Straightforward.
  - *Cons:* per-frame fixed overhead (~ms–tens of ms). Fine at "once per refresh
    for the whole plan"; must **never** be called per-object in a loop again.
- **(B) `pyerfa` fast path.** `pyerfa` (astropy's ERFA binding, already
  installed) exposes vectorized C routines (`erfa.atco13`/`apco13`/`gst06a`) to
  compute topocentric alt/az and sidereal time for arrays in microseconds.
  - *Pros:* ephem-class speed, fully vectorized, no astropy object overhead.
  - *Cons:* ~150-250 lines of careful astrometry to write and validate against
    `ephem`/astropy. Best contributed to `pyaraucaria` as the canonical fast
    path (benefits `ctc`, `tpg` too).
- **(C) Keep `ephem`.** It's fast, mature C. The brief says remove it, but the
  honest trade is: removing it *requires* A or B; if neither lands, keeping
  `ephem` is defensible for the compute core while still deleting its use as a
  datetime library (§2.2).

**DECIDED (2026-07): A now, then B contributed to pyaraucaria as the measured
fast path, with an LRU cache for fixed-time positions.** The pyerfa contribution
to pyaraucaria is confirmed in scope (upstream). Sequence: ship `toi_astro` on
batched astropy (P5/P6) to unblock `ephem` removal; add a pyerfa
`radec_to_altaz_batch`/`sidereal_time` to pyaraucaria (P7) as the canonical fast
primitive; `toi_astro` then calls pyaraucaria's fast path, especially for the
plot loops. The two backends are described below so the pyerfa scope is a fully
informed choice.

#### Usage patterns — batched astropy vs pyerfa vs mixed

**Batched astropy** (zero new deps; the P5 target):
```python
loc = EarthLocation(lat=..., lon=..., height=...)          # built ONCE, cached
# ---- per refresh, for the WHOLE plan at timestamp `when`: ----
frame = AltAz(obstime=Time(when), location=loc, pressure=0)  # ONE frame per timestamp
sky   = SkyCoord(ra=ra_array*u.deg, dec=dec_array*u.deg)     # vectorized over all OBs
aa    = sky.transform_to(frame)                              # ONE transform → N results
alt, az = aa.alt.deg, aa.az.deg                              # numpy arrays
```
Cost model: astropy's cost is a **fixed per-transform overhead** (frame build +
IERS/erfa setup, ~few–tens of ms) plus near-free per object. So the golden rule
is *one transform per (timestamp, whole batch)* — never per object in a loop
(that was the migration branch's fatal pattern). For the alt-vs-time plot, build
one `Time(grid)` and do one transform per object over the whole grid (or one
transform over a flattened object×time array), not the nested 10 s stepping loop.
Sun/Moon/rise-set stay on `pyaraucaria.ephemeris` (astropy/astroplan) — a handful
of calls per refresh, not per object, so their overhead is irrelevant.

**pyerfa** (astropy already ships it; the P7 upstream fast path):
```python
import erfa
# The expensive bits (precession-nutation, Earth rotation, refraction consts)
# are computed ONCE per (timestamp, site) into an "astrom" context:
astrom, eo = erfa.apco13(utc1, utc2, dut1, elong, phi, hm, xp, yp, 0, tc, rh, wl)
# Then transforms over ARRAYS of stars are pure vectorized C (microseconds):
ri, di               = erfa.atciq(rc_arr, dc_arr, 0, 0, 0, 0, astrom)  # ICRS→CIRS
aob, zob, hob, dob, rob = erfa.atioq(ri, di, astrom)                   # CIRS→observed
alt = 90.0 - np.degrees(zob);  az = np.degrees(aob)
# sidereal: erfa.gst06a(uta, utb, tta, ttb)  — also vectorized
```
The win: the O(precession/nutation) work is done once per timestamp; then N
objects cost microseconds total. This is what astropy does internally, minus the
per-`SkyCoord`/per-frame Python object overhead — so ~10–100× less overhead for
"many objects, refreshed often". Caveat: raw pyerfa needs `dut1` (UT1−UTC) and
polar motion `xp,yp`; astropy fetches these from IERS automatically. **For a
pointing/observability *display*, `dut1≈0` and `xp=yp=0` cost < ~0.3″** — far
below pointing precision — so the fast path can ignore IERS and stay pure/offline.
(Keep an optional IERS-supplied mode for anything needing sub-arcsec.)

**Mixed (the actual plan):** `pyaraucaria` gains the pyerfa `radec_to_altaz_batch`
+ `sidereal_time` fast primitives (dut1/polar-motion = 0 by default, optional
IERS). TOI's `toi_astro` uses them for the hot batch/plot paths, keeps
`pyaraucaria.ephemeris` (astropy) for Sun/Moon/rise-set (low call count), and
wraps **planned** positions in an LRU cache.

#### LRU / caching (your suggestion — yes, but scoped)
- **Cache planned alt/az** keyed by `(uobi or ra+dec, plan_ut)`: a plan's planned
  positions don't change between refreshes unless the plan or its time changes,
  so this eliminates almost all recompute on the frequent NATS-driven repaints.
- **Cache the per-timestamp context** (astropy `AltAz` frame, or pyerfa `astrom`)
  and reuse it across the whole batch and across the sidereal/sun/moon calls at
  the same timestamp.
- **Do *not* cache "current alt"** — its timestamp is always "now", so a cache
  keyed on time never hits; compute it once per refresh for the whole batch and
  move on.
- Invalidate the planned-position cache on plan mutation and on observatory-time
  jumps; bound the LRU by the max plan length.

### 2.4 [GO DEEP] Kill the per-object call sites regardless of backend

Independent of §2.3, these must change from per-object to per-batch:
- `update_plan` (`toi.py:2329-2358`): collect all OBs' ra/dec into arrays, one
  `radec_to_altaz_batch` for "current alt", one for "planned alt". Compute
  `slotTime`/sunset/sunrise once per plan, not per OB.
- `plan_gui` moon-distance column (`plan_gui.py:405-423`): stop building a fresh
  `Observer`+`FixedBody`+`Moon` per row per repaint; compute moon position once
  per timestamp, vectorize the separations.
- `PlotWindow.refresh` (`plan_gui.py:1552-1717`): build one time grid, transform
  once per object (or once for all objects × grid), instead of the nested
  `while t <= ...: RaDec2AltAz(...)` 10-second stepping loop.

These changes alone remove the migration branch's slowdown even on backend A.

---

## 3. Plan editor — correctness first, then de-duplicate state

### 3.1 [GO DEEP] Fix the confirmed corruption/consistency bugs

**Bug 1 — `AddWindow.save_ob` corrupts the plan** (`plan_gui.py:2085-2100`):

```python
# CURRENT (broken)
if len(self.parent.plan) > self.parent.i:
    self.parent.plan.append(tmp)          # ignores position; appends to END
    self.parent.i += 1
else:
    self.parent.plan[self.parent.i+1:self.parent.i+1] = tmp   # tmp is a DICT →
                                          # slice-assign inserts its KEYS as 3 items
self.parent.i = self.parent.i + 1          # i incremented a SECOND time
```

```python
# FIX
insert_at = self.parent.i + 1
self.parent.plan[insert_at:insert_at] = [tmp]   # insert the OB dict as one element
self.parent.i = insert_at
self.parent.parent.update_plan(self.parent.parent.active_tel)
self.close()
```

**Bug 2 — `EditWindow.save_ob` doesn't resync/republish**
(`plan_gui.py:1773-1783`): it mutates the plan then calls only
`update_table()`, so `meta` (slotTime, plan_ut, plan_alt) is never recomputed
and the change is **not published to NATS** (unlike Add/Copy/Del). Fix: replace
`self.parent.update_table()` with
`self.parent.parent.update_plan(self.parent.parent.active_tel)` so the edit takes
the same write path as every other mutation.

**Bug 3 — schema-name inconsistency:** `loadPlan` loads `"base_schema"`
(`plan_gui.py:840`) while `EditWindow`/`AddWindow` load `"base_schema.yaml"`
(`plan_gui.py:1759`). Pick one (the loader accepts both today, but the drift is a
latent bug). Standardize on the extension-less form and load **once** (see 3.2).

**Bug 4 — schemas reloaded per line** in `loadPlan` (`plan_gui.py:840-843`) and
`TPGWindow.get_plan` (`plan_gui.py:1208-1211`): load
`ObsValidator`/schemas once (module- or window-scoped), reuse across all lines.

**Bug 5 — `update_table` side effect:** it unconditionally sets
`self.parent.telescope_switch_status["plan"] = True` at the end
(`plan_gui.py:471`) from a pure repaint method, and its error handling is
commented out (`if True:` replacing `try:`, `plan_gui.py:176`). Remove the side
effect (move it to where a switch actually completes) and restore real exception
handling that logs (§5) instead of hiding index/parse errors.

### 3.2 [GO DEEP] Preserve scroll & selection on refresh

`update_table` (`plan_gui.py:168-471`) does `clearContents()` +
`setRowCount(0)` every call and is driven by every NATS plan message, so the
operator's scroll position and selected row jump to the top constantly. The fix
already exists on the migration branch (commit `3c2d0e7`) but is **not in
`main`**: wrap the rebuild by saving `currentRow`/`currentColumn`/
`verticalScrollBar().value()` at the top and restoring them at the end.
Port that commit. (Better long-term: switch to a `QAbstractTableModel` that
emits granular `dataChanged` instead of full rebuilds — see 3.3.)

### 3.3 [DISCUSS] Eliminate the model/view dual state

**Problem.** The shadow copies in `PlanGui` (`self.plan/self.i/…`) versus the
authoritative `toi.py` state (`self.plan[tel]/current_i/next_i`) is the root of
the index-desync class of bugs; operations read the shadow index but mutate the
real list, and the two diverge when not in control (the view rebinds to the NATS
snapshot, `plan_gui.py:185`).

**Options.**
- **(A) Single `Plan` model object** owned by `toi.py`, holding the OB list and
  the indices, exposing intent methods (`insert_after`, `move_up`, `set_next`,
  `edit`, `delete`) that keep indices consistent internally. `PlanGui` holds a
  reference and renders it via a `QAbstractTableModel`; no shadow copies, no
  index math in the view. Editing ops call model methods.
- **(B) Keep the current structure but make the view strictly index-free:** the
  view always reads `self.parent.plan[active_tel]` and `self.parent.*_i`
  directly, never caches them, and click-selection stores only a stable OB
  `uobi`, not a row index.

**Recommendation:** **A.** A `Plan` model is the right home for the fragile
index bookkeeping (first/last/up/down wrap-arounds, `check_next_i` skip logic)
and is unit-testable without Qt. It also makes the NATS publish
(`update_plan`, `toi.py:2365-2368`) a serialization of one object. **[DISCUSS]**
scope/timing — this is a bigger change than §3.1/§3.2 and should follow them.

### 3.4 [GO DEEP] Lean on the canonical parser/validator
Good news: parsing already uses `pyaraucaria.ob_validator.ObsValidator` and
`ObsPlanParser` (`plan_gui.py:37-38`) — the canonical stack (vault: *Obs Plan
Parser*). Keep it; just (a) load schemas once (§3.1 Bug 4), (b) route all
serialization through `validator.convert_from_obdict` (already used in Edit/Add)
so `savePlan` can optionally re-serialize from the parsed `ob` rather than
relying solely on the verbatim `block` text, and (c) surface parser errors
(currently the parser logs ERROR and returns None with no line info — wrap calls
to report *which* line failed to the operator).

---

## 4. Hardcoding → single sources of truth

### 4.1 [GO DEEP] One observatory location, correct and shared

**Problem.** Coordinates exist four times with three values:
- `toi.py:4159` `["-24:35:24","-70:11:47","2800"]`
- `toi.py:1176-1177` & `3058-3059` `lat=-24.598056, lon=-70.196389, elev=2817`
- `configuration/settings.py:3` `("48.3","14.28","1000")` — **wrong** (European
  placeholder; OCM is Cerro Murphy, Chile, 2817 m).

**Change.**
- Establish the canonical value **once**. Preferred: read it from the observatory
  config already pulled over NATS (`tic.config.observatory`,
  `observatory_model.get_client_configuration()` at `toi.py:4040`) — TIC is the
  source of truth. Fall back to a single constant in one config module only if
  NATS lacks it.
- Delete `OBSERVATORY_COORD` from `configuration/settings.py` and the inline
  literals at `toi.py:1176/3058`. Everything calls `toi_astro`/config, which
  holds the one `EarthLocation`/obs triple.
- Reconcile `2800` vs `2817` (use the surveyed value; confirm with the team —
  `ctc` uses `-24.598, -70.196, 2817`).

### 4.2 [GO DEEP] Telescope registry, not `if active_tel == ...` chains

**Problem.** Per-telescope data is baked into branches: instrument option lists
(`toi.py:536-558`), focus coefficients (`toi.py:3605-3607`), dome geometry
(`toi.py:1175/3057`), `m3_list`, and a hardcoded telescope list
(`toi.py:4255`) duplicating `toi_config.yaml`. Same pattern in `aux_gui.py`,
`mnt_gui.py`, `fits_gui.py`.

**Change.** Extend `toi_config.yaml` per-telescope with the currently-hardcoded
fields (instrument obstype/mode/bins/subraster/defSetUp, `m3_list`, focus
coefficients `aTemp/aHum/a0`, dome geometry `r_dome/spx/spy/gem`). Load into a
`TelescopeProfile` dataclass per telescope; replace every `if active_tel ==`
chain with `self.profiles[active_tel].<field>`. The active telescope list comes
only from config (`toi_config.yaml:2`), never from the `toi.py:4255` literal.
Validate the config against a schema at load (fail fast with a clear message if a
telescope is missing a field).

### 4.3 [GO DEEP] Named constants for limits, timeouts, geometry

Replace scattered magic numbers with named, documented, config-backed values:
- Weather limits `toi.py:4193-4197` (wind 11/14, humidity 70, temp 0, overhead
  10) → config with units in the key or a comment.
- NATS `timeout=10` scattered across `toi.py` publishes, connect `wait=3`,
  subscription close `1 s`, task-stop `2.5 s` → named constants in one place.
- Poll intervals `sleep(3)`/`sleep(1)` → named constants (and revisit whether the
  loops survive the §1 refactor at all).
- `nats_watch.py:101` hardcodes `tic.status.zb08...` — parameterize the telescope.
- `ALPACA_BASE_ADDRESS = "sim"` (`configuration/settings.py:7`) — this simulator
  default silently points the whole address dict at `sim`; if `OCA_ADDRESS_DICT`
  survives §1.2, drive the prefix from config/active telescope, never a literal.

### 4.4 [GO DEEP] Centralize NATS subject construction

Subjects like `tic.status.{tel}.toi.plan`, `tic.journal.{tel}.planner`,
`telemetry.conditions.{tel}-htsensor` are f-string-built at ~40 sites in
`toi.py`. Add one `subjects.py` with builder functions
(`toi_plan(tel)`, `journal_planner(tel)`, …) so the subject catalog is in one
place, matches the vault's *OCA NATS Subject Catalog*, and typos become
impossible. Pure mechanical extraction.

---

## 5. Observability — logging as a first-class feature

**Problem.** Error handling is uniform-but-opaque: ~everything is swallowed into
`logger.warning(f'EXCEPTION <n>: {e}')` with hand-numbered messages (0–778),
several with unreachable duplicate `except` clauses (`toi.py:291-294,305-308`),
and some `try:` blocks replaced by `if True:` (`plan_gui.py:176`). A dropped
subscription or a failed publish is invisible.

### 5.1 [GO DEEP] Structured, leveled logging
- Configure logging once at startup: a rotating file handler (reuse
  `msg_log_file`/`msg_log_lines`) + console, with a format including timestamp,
  level, logger name, telescope, and address where relevant.
- Replace `EXCEPTION <n>` numbering with meaningful messages: *what* failed,
  *which* address/telescope/subject, and the exception. Use `logger.exception`
  (captures traceback) for unexpected errors; reserve `warning` for handled,
  expected conditions.
- Delete unreachable duplicate `except` clauses and restore the commented-out
  `try` blocks (`plan_gui.py:176,468`) with real handling.
- Establish severity discipline aligned with the ecosystem error model (vault:
  *Error Model across ocabox ecosystem*): TEMPORARY→debug/retry, NORMAL→warning,
  CRITICAL→error + surface to operator.

### 5.2 [GO DEEP] Operator-visible health
- Per §1.4, a stale value shows as stale in the UI, not a frozen number.
- A single "connection/health" indicator: TIC reachable, per-telescope
  subscription health, last-update ages. This reuses the staleness watchdog data.
- Log every telescope switch (start/finish + duration) and every plan mutation
  (op, uobi, resulting indices) — the two workflows operators most need to audit.

---

## 6. Consistency, redundancy, readability

- **De-duplicate coordinate/almanac/altaz** into `toi_astro` (§2.2) — removes
  the copy-pasted `ephem.Observer()` setup blocks in `toi_lib.py`, `plan_gui.py`,
  `toi.py`.
- **Remove dead code:** commented MQTT block (`notes.txt` and in-file), the
  `if False:` sync paths, `_old` plan files, `alpaca.py`'s commented endpoint
  dumps, unreachable excepts.
- **Naming:** keep the domain Polish vocabulary that carries meaning
  (`pocisniecie_tabelki` = table-click handler) but add a short English
  docstring; translate only where a name actively misleads. Preserve author
  attribution and comment voice.
- **Keep behaviour identical:** each phase verified against the running app
  (same displayed values, same plan-file round-trips, same commands issued).
- **Do not** split `toi.py` into modules as an early step. Fix the data paths and
  bugs first (§1, §3); a class this central should be decomposed only once the
  monitor layer (§1.2) gives a natural seam (monitor / telescope-controller /
  view). Premature splitting of a live monolith is its own risk.

---

## 7. Sequencing & risk

Ordered so each phase is independently shippable, verifiable, and low-risk
before the larger structural ones. **[GO DEEP]** phases can be handed to a
straightforward implementer; **[DISCUSS]** phases need a decision recorded first.

| Phase | Content | Type | Risk | Depends on |
|------|---------|------|------|-----------|
| P1 | §1.1 callbacks consume `event`; delete double-fetch; lint guard | GO DEEP | Low | — |
| P2 | §1.4 error-policy + staleness watchdog | GO DEEP | Low | P1 |
| P3 | §3.1 plan-editor bug fixes; §3.2 scroll/selection port | GO DEEP | Low | — |
| P4 | §4.1 one observatory location; §4.4 subjects.py; §4.3 constants | GO DEEP | Low | — |
| P5 | §2.2 `toi_astro` module (backend = current ephem behind interface) | GO DEEP | Med | P4 |
| P6 | §2.4 batch all per-object call sites | GO DEEP | Med | P5 |
| P7 | §2.3 pyerfa fast path in **pyaraucaria** (upstream) + LRU cache; `toi_astro` calls it | DECIDED | Med | P5,P6 |
| P8 | §4.2 telescope registry / profiles | GO DEEP | Med | P4 |
| P9 | §1.2 all-telescopes `TelemetryStore`; collapse data paths (thin, forward-compatible) | DECIDED | High | P1,P2 |
| P9b | Upstream ocabox: fix "callbacks stop firing" bug; make `ErrorPolicy.SERVICE` easy | DECIDED | Med | — |
| P10 | §1.3 fast telescope switch (view re-point via store) | DECIDED | Med | P9,P9b |
| P11 | §3.3 Plan model + QAbstractTableModel (**after** P3 ships) | DECIDED | Med | P3 |
| P12 | §5 logging pass; §6 dead-code/readability | GO DEEP | Low | all |

**Verification for every phase:** run TOI against a live/sim TIC; confirm the
touched values display identically, plans round-trip byte-for-byte through
save/load, and issued commands are unchanged (diff NATS publishes). Keep `ephem`
installed as a test oracle through P7 to assert the new astro results match to
tolerance before removal.

---

## 8. Decisions (settled 2026-07)

1. **Ephemeris (§2.3):** batched astropy first (P5/P6) to unblock `ephem`
   removal; then a **pyerfa fast path contributed to `pyaraucaria`** (P7) with an
   LRU cache for fixed-time planned positions. `toi_astro` is the single seam.
2. **Data-layer depth (§1.2):** a **thin, forward-compatible all-telescopes
   `TelemetryStore` in TOI** whose interface is the "simple, powerful client
   view" shape and survives the coming NATS-native migration. Only small
   bug/ergonomics fixes go upstream into ocabox — no big ocabox refactor.
3. **Telescope switching (§1.3):** **fast switch = view re-point** via the store;
   the discard-and-rebuild workaround is removed once the upstream ocabox
   "callbacks stop firing" bug is fixed (P9b).
4. **Plan model (§3.3):** ship correctness fixes first (P3), then introduce the
   `Plan` model + `QAbstractTableModel` (P11).

**Upstream scope (confirmed):** fix the ocabox "callbacks stop firing" bug, and
contribute the pyerfa alt-az/sidereal fast path to pyaraucaria. Everything else
stays inside TOI.

**Still to confirm during implementation (not blockers):** the surveyed
observatory elevation (2800 vs 2817 m, §4.1); the all-telescopes subscription
bandwidth on the real LAN (§1.3); whether batched astropy alone is fast enough
before the pyerfa path lands (benchmark at P6).

P1–P8 and P12 deliver most of the stability, performance, and consistency wins
and can begin immediately; P9–P11 are the larger structural phases.
