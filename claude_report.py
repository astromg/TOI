"""
Dodatkowy plik raportu (REPORT -> Create Report) przeznaczony do analizy przez Claude.

Zapisuje do katalogu raportu plik claude_debug.json ze stanem TOI potrzebnym do diagnozy:
plan (lokalny / widok PlanGui / NATS), stan OB, focus adjust, stan taskow w tle, wersje bibliotek.
Kazda sekcja zbierana jest osobno w try/except - blad w jednej sekcji nie psuje reszty
i nigdy nie moze wywalic TOI (report() jest zwyklym slotem Qt).
"""

import asyncio
import datetime
import json
import logging
import os
import platform
import subprocess
import sys
import traceback

logger = logging.getLogger(__name__)

CLAUDE_REPORT_FILE = "claude_debug.json"
_MAX_DEPTH = 8
_MAX_STR = 2000

_PACKAGES = ["pyaraucaria", "tpg", "ctc", "ocabox", "ocabox-common", "obcom", "serverish",
             "qasync", "PyQt6", "numpy", "astropy", "ephem"]

_TOI_ATTRS = ["active_tel", "tel_acces", "tel_users", "telescope_switch_status", "toi_switch_status",
              "autofocus_started", "last_focus_position", "focus_method", "ccd_readoutmode",
              "telemetry_temp", "telemetry_humidity", "telemetry_wind", "telemetry_wind_direction",
              "ut", "current_i", "next_i", "ob_progress", "nats_ob_progress", "report",
              "nats_focus_record", "nats_focus_reference", "program_id"]

_GUI_ATTRS = ["obsGui", "mntGui", "instGui", "planGui", "skyGui", "fitsGui", "focusGui", "flatGui",
              "conditionsGui", "guiderGui", "planrunnerGui"]


def _sanitize(obj, depth=0):
    """Zamienia dowolny obiekt na cos, co da sie zapisac jako JSON."""
    if depth > _MAX_DEPTH:
        return f"<max depth> {type(obj).__name__}"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= _MAX_STR else obj[:_MAX_STR] + "...<cut>"
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v, depth + 1) for v in obj]
    try:
        import numpy
        if isinstance(obj, numpy.generic):
            return obj.item()
        if isinstance(obj, numpy.ndarray):
            return _sanitize(obj.tolist(), depth + 1)
    except Exception:
        pass
    txt = repr(obj)
    return txt if len(txt) <= _MAX_STR else txt[:_MAX_STR] + "...<cut>"


def _section(fn, toi):
    try:
        return fn(toi)
    except Exception:
        return {"_error": traceback.format_exc()}


def _meta(toi):
    here = os.path.dirname(os.path.abspath(__file__))
    git = {}
    for key, cmd in {"commit": ["git", "rev-parse", "HEAD"],
                     "branch": ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                     "status": ["git", "status", "--short"]}.items():
        try:
            git[key] = subprocess.run(cmd, cwd=here, capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception as e:
            git[key] = f"<error {e}>"
    return {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "toi_ut": getattr(toi, "ut", None),
        "cwd": os.getcwd(),
        "toi_dir": here,
        "python": sys.version,
        "platform": platform.platform(),
        "git": git,
    }


def _versions(toi):
    from importlib import metadata
    out = {}
    for name in _PACKAGES:
        info = {}
        try:
            dist = metadata.distribution(name)
            info["version"] = dist.version
            try:
                direct = dist.read_text("direct_url.json")
                if direct:
                    info["source"] = json.loads(direct)  # git url + commit_id / lokalna sciezka
            except Exception:
                pass
        except Exception as e:
            info["version"] = f"<not found: {e}>"
        mod_name = name.replace("-", "_")
        mod = sys.modules.get(mod_name)
        if mod is not None:
            info["module_file"] = getattr(mod, "__file__", None)
        out[name] = info
    return out


def _toi_state(toi):
    out = {}
    for name in _TOI_ATTRS:
        out[name] = getattr(toi, name, "<missing attribute>")
    out["telescope_set"] = getattr(toi, "telescope", None) is not None
    out["telescopes_cfg"] = toi.local_cfg["toi"]["telescopes"]
    return out


def _plans(toi):
    out = {}
    plan_gui = toi.planGui
    nats = getattr(toi, "nats_plan_status", {}) or {}
    view = getattr(plan_gui, "plan", None)

    out["planGui_view"] = {
        "i": getattr(plan_gui, "i", None),
        "prev_i": getattr(plan_gui, "prev_i", None),
        "current_i": getattr(plan_gui, "current_i", None),
        "next_i": getattr(plan_gui, "next_i", None),
        "len": len(view) if view is not None else None,
        # na co wskazuje PlanGui.plan - kluczowe dla bledow typu "OB-y zniknely po TPG/Load"
        "is_toi_plan_of_active_tel": view is toi.plan.get(toi.active_tel) if toi.active_tel else None,
        "is_nats_plan_status": view is nats.get("plan"),
        "show_ob": getattr(plan_gui, "show_ob", None),
    }
    out["nats_plan_status"] = {
        "current_i": nats.get("current_i"),
        "next_i": nats.get("next_i"),
        "len": len(nats.get("plan") or []),
        "blocks": [ob.get("block") if isinstance(ob, dict) else ob for ob in (nats.get("plan") or [])],
    }
    local = {}
    for tel, plan in toi.plan.items():
        local[tel] = {
            "len": len(plan) if plan is not None else None,
            "current_i": toi.current_i.get(tel) if isinstance(toi.current_i, dict) else None,
            "next_i": toi.next_i.get(tel) if isinstance(toi.next_i, dict) else None,
            "obs": [{"i": i, "block": ob.get("block"), "meta": ob.get("meta")} if isinstance(ob, dict)
                    else {"i": i, "raw": ob} for i, ob in enumerate(plan or [])],
        }
    out["local_plan"] = local
    out["ob"] = getattr(toi, "ob", None)
    return out


def _tpg(toi):
    plan_gui = toi.planGui
    win = getattr(plan_gui, "tpg_window", None)
    if win is None:
        return {"tpg_window": None}
    out = {"tpg_window": repr(win)}
    for name, fn in {"visible": lambda: win.isVisible(),
                     "thread_running": lambda: win.thread.isRunning(),
                     "info_text": lambda: win.info_e.toPlainText()}.items():
        try:
            out[name] = fn()
        except Exception as e:  # np. obiekt C++ juz usuniety (deleteLater)
            out[name] = f"<{type(e).__name__}: {e}>"
    return out


def _focus(toi):
    out = {}
    for tel in toi.local_cfg["toi"]["telescopes"]:
        try:
            out[tel] = {"focus_reference": toi.nats_focus_reference[tel],
                        "focus_adjust_target": toi.focus_adjust_target(tel)}
        except Exception as e:
            out[tel] = {"focus_adjust_target": f"<{type(e).__name__}: {e}>"}
    return out


def _task_info(task):
    if task is None:
        return {"state": "not created"}
    info = {"done": task.done(), "cancelled": task.cancelled()}
    try:
        info["coro"] = task.get_coro().__qualname__
    except Exception:
        info["coro"] = repr(task.get_coro())
    if task.done() and not task.cancelled():
        exc = task.exception()
        info["exception"] = repr(exc) if exc else None
    return info


def _background_tasks(toi):
    """Task w tle ktory jest 'done' a powinien dzialac = martwa petla/czytnik."""
    out = {}
    widgets = {"TOI": toi}
    widgets.update({name: getattr(toi, name, None) for name in _GUI_ATTRS})
    for wname, widget in widgets.items():
        groups = getattr(widget, "_background_tasks", None)
        if not groups:
            continue
        out[wname] = {g: [dict(name=bt.name, created=bt.created, **_task_info(bt.task)) for bt in tasks]
                      for g, tasks in groups.items()}
    try:
        all_tasks = asyncio.all_tasks()
    except RuntimeError:
        all_tasks = set()
    out["_asyncio_all_tasks"] = sorted(_task_info(t).get("coro", "?") for t in all_tasks)
    return out


def _config(toi):
    return toi.local_cfg


SECTIONS = {
    "meta": _meta,
    "versions": _versions,
    "toi_state": _toi_state,
    "plans": _plans,
    "tpg": _tpg,
    "focus": _focus,
    "background_tasks": _background_tasks,
    "local_cfg": _config,
}


def write_claude_report(toi, dir_name):
    """Zapisuje claude_debug.json w katalogu raportu. Nigdy nie rzuca wyjatku."""
    try:
        data = {"_about": "TOI state dump for analysis by Claude (claude_report.py)"}
        for name, fn in SECTIONS.items():
            data[name] = _section(fn, toi)
        with open(os.path.join(dir_name, CLAUDE_REPORT_FILE), "w") as f:
            json.dump(_sanitize(data), f, indent=1, ensure_ascii=False)
    except Exception as e:
        logger.warning(f'TOI: claude report failed: {e}')
