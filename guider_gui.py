#!/usr/bin/env python3
"""The Guider tab of the Aux window: a TOI client of the guider service (ocabox-tcs ``guiding_svc.guider``).

The service runs on services01 and does all the work (camera, solver, pulses); TOI, like the guider web UI
(``http://192.168.7.45:8090/``), only shows its state and sends commands. Interface: knowledge base,
"Guider service - NATS interface". Today only jk15 has a guider (``guider_beso``, the BESO fibre).

This module is the window only. What feeds it (``TOI``, over NATS):
- :meth:`GuiderTab.set_guiders` — discovered guider services, ``{tel: info}`` (``info`` = ``details.metrics.guider``
  of ``svc.status.guiding_svc.guider.<variant>``, plus ``status`` and ``status_time``),
- :meth:`GuiderTab.show_state` — ``PipelineState`` of the pipeline (``….pipeline.<pipe>.state``),
- :meth:`GuiderTab.show_frame` — JPEG bytes of a thumbnail (``frame.thumbnail.ready`` → HTTP),
- :meth:`GuiderTab.add_journal` — events and journal lines.
Commands go through :meth:`GuiderTab.command`, which checks control of the telescope and calls
``self.rpc(cmd, data)`` (a coroutine function set by TOI, or None: nothing is sent yet).

All positions are guider sensor pixels (``dimensions``, 1936×1216 for guider_beso); the thumbnail is smaller and
is drawn scaled to that size, so the overlays need no conversion.
"""

import asyncio
import logging
import math
import time
from collections import deque

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQtX.QtCore import QRectF, Qt, QTimer
from PyQtX.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PyQtX.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QGraphicsScene, QGraphicsView, QGridLayout,
                             QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox, QTextEdit, QVBoxLayout, QWidget)

from toi_theme import theme

logger = logging.getLogger(__name__)

DEFAULT_DIMENSIONS = (1936, 1216)       # guider_beso; the thumbnail payload says the real size
DRIFT_WINDOW_S = 300                    # dryf na wykresie i RMS: ostatnie 5 min (jak web UI)
EXP_PRESETS = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
PULSE_STEPS = [1, 5, 10, 30]            # px obrazu (klawisze 1-4 w podgladzie)
METHODS = [("single_star", "single star"), ("fiber", "fiber")]
MODES = ["off", "monitoring", "guiding"]
# ostrosc teleskopu dla instrumentu guidera (BESO: oca-manual beso.md "Focusing"; nadpisuje toi.guider_focus) i
# tolerancja - dalej i guider wlaczony = ostrzezenie (przy ostrosci Andora kamera BESO widzi sam szum, 2026-11-10)
GUIDER_FOCUS = {"jk15": 21950}
FOCUS_TOLERANCE = 300
RETICLE_MOVED_PX = 1.0      # reticle dalej od skalibrowanej pozycji - pokazujemy o ile
MODE_COLORS = {"off": None, "monitoring": "change_bg", "guiding": "ok_bg"}
# kolory dryfu: bez znaczenia ok/zle (czerwony = zle w TOI), tylko dwie odroznialne serie
DRIFT_X_COLOR = "#a070d0"
DRIFT_Y_COLOR = "#40b0c0"


def _xy(value):
    """[x, y] / (x, y) -> (float, float) or None"""
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _num(value, fmt="{:.1f}", none="—"):
    try:
        return fmt.format(float(value))
    except (TypeError, ValueError):
        return none


# ############### FRAME VIEW ##########################

class GuiderScene(QGraphicsScene):
    """The guider frame in sensor pixels with the overlays; shown by the main view and the reticle close-up."""

    def __init__(self):
        super().__init__()
        self.dims = DEFAULT_DIMENSIONS
        self.setSceneRect(0, 0, *self.dims)
        self.pixmap_item = self.addPixmap(QPixmap())
        self.pixmap_item.setZValue(0)
        self.overlay = []               # elementy nakladki, przerysowywane przy kazdym stanie
        self.state = None
        self.show_candidates = False

    def set_dimensions(self, dims):
        dims = (int(dims[0]), int(dims[1]))
        if dims != self.dims and dims[0] > 0 and dims[1] > 0:
            self.dims = dims
            self.setSceneRect(0, 0, *dims)
            self._fit_pixmap()

    def set_frame(self, pixmap):
        self.pixmap_item.setPixmap(pixmap)
        self._fit_pixmap()

    def _fit_pixmap(self):
        pm = self.pixmap_item.pixmap()
        if pm.isNull():
            return
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.pixmap_item.setScale(self.dims[0] / pm.width())

    def clear_frame(self):
        self.pixmap_item.setPixmap(QPixmap())

    # --- nakladka ---

    @staticmethod
    def _pen(key, width=1.5, style=Qt.PenStyle.SolidLine, alpha=255):
        color = theme.qcolor(key)
        color.setAlpha(alpha)
        pen = QPen(color, width, style)
        pen.setCosmetic(True)       # grubosc w pikselach ekranu, niezaleznie od powiekszenia
        return pen

    def _add(self, item, z=5):
        item.setZValue(z)
        self.overlay.append(item)
        return item

    def _circle(self, xy, r, pen):
        return self._add(self.addEllipse(QRectF(xy[0] - r, xy[1] - r, 2 * r, 2 * r), pen))

    def _line(self, a, b, pen):
        return self._add(self.addLine(a[0], a[1], b[0], b[1], pen))

    def _label(self, xy, text, key):
        item = self._add(self.addSimpleText(text))
        item.setBrush(QBrush(theme.qcolor(key)))
        item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)     # tekst zawsze tej samej wielkosci
        item.setPos(xy[0], xy[1])
        return item

    def _cross(self, xy, r_in, r_out, pen):
        x, y = xy
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self._line((x + dx * r_in, y + dy * r_in), (x + dx * r_out, y + dy * r_out), pen)

    def draw_state(self, state):
        """Overlays after the guider state ``state`` (``PipelineState`` dict, or None - nothing)."""
        self.state = state
        for item in self.overlay:
            self.removeItem(item)
        self.overlay = []
        if not state:
            return
        method = state.get("method")
        mode = state.get("mode")
        reticle = _xy(state.get("central_point"))
        # promien otworu: z parametrow metody fiber, inaczej z detektora otworu (single star go nie ma)
        fiber_r = float((state.get("method_params") or {}).get("fiber_radius_px")
                        or (state.get("hole_detect") or {}).get("radius_px") or 5.0)

        # szerokie szukanie: klikniecia i ponowne lapanie tylko w tym kole
        wide_r = state.get("wide_search_radius_px")
        if reticle and wide_r and method != "fiber":
            self._circle(reticle, float(wide_r), self._pen("dim_fg", 1, Qt.PenStyle.DashLine, 160))

        # kandydaci z detekcji (klawisz D)
        if self.show_candidates and method != "fiber":
            pen = self._pen("dim_fg", 1)
            for cand in state.get("candidates") or []:
                c = _xy(cand)
                if c:
                    self._add(self.addRect(QRectF(c[0] - 6, c[1] - 6, 12, 12), pen))

        # reticle = wejscie swiatlowodu: krzyz z otwartym srodkiem i okrag promienia otworu
        if reticle:
            pen = self._pen("change_fg", 1.5)
            self._cross(reticle, fiber_r * 2, fiber_r * 6, pen)
            self._circle(reticle, fiber_r, self._pen("change_fg", 1, Qt.PenStyle.DotLine))
            if method == "fiber":
                win = float((state.get("method_params") or {}).get("analysis_radius_px") or 15.0)
                self._add(self.addRect(QRectF(reticle[0] - win, reticle[1] - win, 2 * win, 2 * win),
                                       self._pen("change_fg", 1, Qt.PenStyle.DashLine, 160)))

        # zmierzone wejscie swiatlowodu (refine reticle)
        hole = state.get("hole_candidate") or {}
        hole_xy = _xy((hole.get("x"), hole.get("y"))) if hole else None
        if hole_xy:
            self._circle(hole_xy, fiber_r, self._pen("warn_fg", 1.5, Qt.PenStyle.DashLine))

        # kotwica: gdzie petla trzyma gwiazde (tylko w guiding i gdy rozna od reticle)
        anchor = _xy(state.get("guide_anchor"))
        if mode == "guiding" and anchor and (not reticle or math.dist(anchor, reticle) > 0.5):
            pen = self._pen("warn_fg", 1.5, Qt.PenStyle.DashLine)
            self._cross(anchor, 4, 14, pen)
            self._label((anchor[0] + 10, anchor[1] + 10), "anchor", "warn_fg")

        # gwiazda trzymana w tej klatce + linia do celu
        star = _xy(state.get("acquired_pos"))
        if star and state.get("acquired"):
            self._circle(star, 10, self._pen("ok_fg", 2))      # ADU - w diagnostyce obok
            target = anchor if anchor else reticle
            if mode == "guiding" and target and math.dist(star, target) > 0.5:
                self._line(star, target, self._pen("ok_fg", 1))

        # przewidywane polozenie po impulsie
        pred = _xy(state.get("predicted_pos"))
        if pred and star:
            self._line(star, pred, self._pen("change_fg", 1, Qt.PenStyle.DotLine))
            self._circle(pred, 6, self._pen("change_fg", 1, Qt.PenStyle.DotLine))


class FrameView(QGraphicsView):
    """Main view of the guider frame: wheel zooms around the cursor, left click locks on a star (single star, inside
    the wide-search circle), right click moves the reticle; keys when it has focus: arrows - manual pulse by the
    chosen step, 1-4 step, R re-acquire, D candidates, H reticle home, +/-/0 zoom."""

    def __init__(self, scene, tab):
        super().__init__(scene)
        self.tab = tab
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setMinimumSize(300, 200)
        self.zoomed = False
        self._pan = None
        self.message = ""

    def set_message(self, text):
        """text in the middle of the view (no guider, no state yet); "" - none"""
        if text != self.message:
            self.message = text
            self.viewport().update()

    def drawForeground(self, painter, rect):
        if self.message:
            painter.save()
            painter.resetTransform()
            painter.setPen(theme.qcolor("dim_fg"))
            font = QFont()
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            painter.restore()

    def fit(self):
        self.zoomed = False
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.zoomed:
            self.fit()

    def zoom(self, factor):
        self.zoomed = True
        self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.25 if event.angleDelta().y() > 0 else 0.8)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            return
        p = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton:
            self.tab.click_star(p.x(), p.y())
        elif event.button() == Qt.MouseButton.RightButton:
            self.tab.click_reticle(p.x(), p.y())

    def mouseMoveEvent(self, event):
        if self._pan is not None:
            d = event.position() - self._pan
            self._pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))

    def mouseReleaseEvent(self, event):
        self._pan = None

    def keyPressEvent(self, event):
        key = event.key()
        arrows = {Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1), Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0)}
        steps = {Qt.Key.Key_1: 0, Qt.Key.Key_2: 1, Qt.Key.Key_3: 2, Qt.Key.Key_4: 3}
        if key in arrows:
            self.tab.pulse(*arrows[key])
        elif key in steps:
            self.tab.step_s.setCurrentIndex(steps[key])
        elif key == Qt.Key.Key_R:
            self.tab.reacquire()
        elif key == Qt.Key.Key_D:
            self.tab.candidates_b.toggle()
        elif key == Qt.Key.Key_H:
            self.tab.reticle_home()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom(1.25)
        elif key == Qt.Key.Key_Minus:
            self.zoom(0.8)
        elif key == Qt.Key.Key_0:
            self.fit()
        else:
            super().keyPressEvent(event)


class CloseUpView(QGraphicsView):
    """Close-up of the injection region: the same scene, centred on the reticle, fixed zoom."""

    HALF_SIZE = 25      # px sensora od reticle

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.center = None

    def follow(self, xy):
        self.center = xy
        self._place()

    def _place(self):
        if self.center:
            h = self.HALF_SIZE
            self.fitInView(QRectF(self.center[0] - h, self.center[1] - h, 2 * h, 2 * h),
                           Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place()


# ############### TAB ##########################

class GuiderTab(QWidget):
    """Guider of the active telescope: frame with overlays, drift, controls. See the module docstring."""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.rpc = None                 # coroutine function (cmd, data) -> reply; ustawia GuiderLink
        self.link = None                # guider_client.GuiderLink - czyta NATS dla pokazywanego teleskopu
        self.guiders = {}               # tel -> info z discovery
        self.tel = None                 # teleskop, ktorego guidera pokazujemy (aktywny)
        self.state = None
        self.state_time = None
        self.frame_time = None
        self.drift = deque()            # (t, dx, dy) wzgledem drift_ref
        self.drift_ref = None
        self.prev_state = None
        self.mkUI()
        self.stale_timer = QTimer(self)
        self.stale_timer.timeout.connect(self.check_stale)
        self.stale_timer.start(2000)
        theme.on_change(self.apply_theme)
        self.apply_theme()
        self.updateUI()

    # --- dane od TOI ---

    @property
    def info(self):
        return self.guiders.get(self.tel)

    def set_guiders(self, guiders):
        self.guiders = dict(guiders)
        self.updateUI()

    def set_telescope(self, tel):
        if tel != self.tel:
            self.tel = tel
            self.state = None
            self.state_time = None
            self.prev_state = None
            self.scene.clear_frame()
            self.clear_drift()
            self.journal_e.clear()
        if self.link is not None:
            self.link.follow(tel)
        self.updateUI()

    def updateUI(self):
        """After a telescope switch or new discovery: header, availability of controls, message on the frame."""
        tel = self.tel
        info = self.info
        if info is None:
            self.title_l.setText(f"{tel or '--'}: no guider" if tel else "no telescope")
            self.frame_v.set_message(f"No guider service for {tel}" if tel else "")
            self.scene.draw_state(None)
        else:
            cam = (info.get("pipelines") or [{}])[0].get("camera_id", "")
            self.title_l.setText(f"{tel} · {cam}")
            if not self.state:
                self.frame_v.set_message("waiting for the guider state…")
        self.show_service()
        self._enable()

    def show_service(self):
        info = self.info
        status = (info or {}).get("status")
        if info is None:
            self.service_l.setText("")
            theme.paint(self.service_l)
            return
        key = {"ok": "ok_bg", "busy": "ok_bg", "idle": None, "degraded": "warn_bg", "failed": "bad_bg",
               "stopped": "bad_bg"}.get(str(status).lower(), "warn_bg")
        self.service_l.setText(f" {status or '?'} ")
        theme.paint(self.service_l, bg=key)

    STALE_S = 10        # s bez stanu przy wlaczonym guiderze = cos nie tak (serwis, NATS)

    def guider_focus(self):
        cfg = (getattr(self.parent, "local_cfg", None) or {}).get("toi", {}).get("guider_focus") or {}
        value = cfg.get(self.tel, GUIDER_FOCUS.get(self.tel))
        return float(value) if value is not None else None

    def show_focus(self):
        """Telescope focus vs the focus of the guider's instrument, and FOCUS ADJUST (it would move the focus back
        to the main camera model); red only while the guider is running."""
        w = self.diag["focus"]
        pos = getattr(self.parent, "focus_value", None)
        want = self.guider_focus()
        adjust = bool((getattr(self.parent, "toi_switch_status", {}).get(self.tel) or {}).get("focus_adjust"))
        running = bool(self.state and self.state.get("mode") in ("monitoring", "guiding"))
        if self.info is None or pos is None:
            w.setText("—")
            theme.paint(w)
            return
        txt = f"{float(pos):.0f}"
        bad = False
        tips = []
        if want is not None and abs(float(pos) - want) > FOCUS_TOLERANCE:
            txt += f" ≠ {want:.0f}"
            bad = True
            tips.append(f"the guider's instrument needs focus ~{want:.0f}; stars may be invisible")
        if adjust:
            txt += "  FOCUS ADJUST on"
            bad = True
            tips.append("FOCUS ADJUST is on - it moves the focus to the main camera model; switch it off")
        w.setText(txt)
        if not tips:
            tips.append(f"telescope focus (guider instrument ~{want:.0f})" if want is not None else "telescope focus")
        w.setToolTip("\n".join(tips))
        theme.paint(w, fg=("bad_fg" if running else "warn_fg") if bad else None)

    def check_stale(self):
        """Every 2 s: focus check; a running guider (monitoring / guiding) publishes its state every frame, none
        for STALE_S means the service or the link is down - say so instead of showing an old picture as current."""
        self.show_focus()
        s = self.state
        if not s or self.info is None or s.get("mode") == "off" or self.state_time is None:
            return
        age = time.time() - self.state_time
        if age > self.STALE_S:
            self.frame_v.set_message(f"no guider state for {age:.0f} s")
            self.service_l.setText(f" stale {age:.0f} s ")
            theme.paint(self.service_l, bg="bad_bg")

    def showEvent(self, event):
        super().showEvent(event)
        self.draw_drift()       # w tle stan przychodzi, ale wykres rysujemy tylko widoczny

    def show_state(self, state):
        """New ``PipelineState`` of the guider of the shown telescope."""
        self.prev_state, self.state = self.state, state
        self.state_time = time.time()
        self.frame_v.set_message("guider OFF" if state.get("mode") == "off" else "")
        self.scene.draw_state(state)
        self.closeup_v.follow(_xy(state.get("central_point")))
        self._update_drift(state)
        self._show_controls(state)
        self._show_diagnostics(state)
        self._enable()

    def show_frame(self, data, dims=None):
        """JPEG (bytes) of the latest guider frame; ``dims`` = sensor size from the thumbnail message."""
        pm = QPixmap()
        if not pm.loadFromData(data):
            logger.warning("GuiderTab: thumbnail not decoded")
            return
        if dims:
            self.scene.set_dimensions(dims)
        self.scene.set_frame(pm)
        self.frame_time = time.time()
        if not self.frame_v.zoomed:
            self.frame_v.fit()

    def add_journal(self, text, level="info", ts=None):
        """A line in the journal; ``level`` info / warning / error / sent (our command, dimmed), ``ts`` serverish
        UTC array of the message (None - now)."""
        key = {"warning": "warn_fg", "error": "bad_fg", "critical": "bad_fg", "sent": "dim_fg"}.get(str(level).lower())
        color = theme.hex(key) if key else theme.hex("field_fg")
        try:
            t = "{:02d}:{:02d}:{:02d}".format(*ts[3:6])
        except (TypeError, ValueError, IndexError):
            t = time.strftime("%H:%M:%S", time.gmtime())
        self.journal_e.append(f'<span style="color:{color}">{t} {text}</span>')

    # --- komendy ---

    def command(self, cmd, **data):
        """Send command ``cmd`` to the guider of the shown telescope, if TOI has control of it."""
        if self.info is None:
            return
        if not self.parent.tel_acces.get(self.tel):
            self.parent.WarningWindow("WARNING: U don't have control")
            return
        if self.rpc is None:
            self.add_journal(f"not sent (guider NATS not connected yet): {cmd} {data or ''}", "warning")
            return
        self.add_journal(f"→ {cmd} {data or ''}", "sent")
        asyncio.ensure_future(self._send(cmd, data))

    async def _send(self, cmd, data):
        try:
            reply = await self.rpc(cmd, data)
        except Exception as e:      # noqa: BLE001 - odpowiedz operatorowi, nie wyjatek z Qt
            self.add_journal(f"{cmd}: no reply ({e})", "error")
            return
        result = reply.get("result") if isinstance(reply, dict) else None
        if isinstance(reply, dict) and reply.get("status") != "ok":
            self.add_journal(f"{cmd}: {reply.get('error')} {reply.get('detail', '')}", "error")
        elif isinstance(result, dict) and result.get("status") not in (None, "ok"):
            why = result.get("reason") or result.get("error") or result.get("message") or result.get("status")
            self.add_journal(f"{cmd} refused: {why}", "warning")

    def set_mode(self, mode):
        if self.state and self.state.get("mode") == mode:
            return
        self.command("set_mode", mode=mode)

    def method_chosen(self, index):
        method = self.method_s.itemData(index)
        if self.state and method != self.state.get("method"):
            self.command("set_state", patch={"method": method})

    def click_star(self, x, y):
        s = self.state
        if not s or s.get("method") == "fiber":
            return
        reticle = _xy(s.get("central_point"))
        r = s.get("wide_search_radius_px")
        if reticle and r and math.dist((x, y), reticle) > float(r):
            self.add_journal("star outside the wide-search circle - not selected", "warning")
            return
        self.command("lock_at", x=round(x, 1), y=round(y, 1))

    def click_reticle(self, x, y):
        if self.state:
            self.command("acquire_at", x=round(x, 1), y=round(y, 1))

    def reacquire(self):
        self.command("acquire")

    def drop_to_reticle(self):
        self.command("drop_to_reticle")

    def refine_reticle(self):
        self.command("refine_reticle")

    def reticle_home(self):
        home = _xy((self.state or {}).get("central_point_default"))
        if home:
            self.command("acquire_at", x=home[0], y=home[1])

    def pulse(self, sx, sy):
        step = PULSE_STEPS[self.step_s.currentIndex()]
        self.command("pulse_pixels", dx_px=sx * step, dy_px=sy * step)

    def apply_camera(self):
        s = self.state or {}
        patch = {}
        exp = self.exp_s.value()
        if s.get("exp_time") is None or abs(exp - float(s["exp_time"])) > 1e-6:
            patch["exp_time"] = exp
        if self.gain_s.value() != (s.get("gain") if s.get("gain") is not None else -1):
            patch["gain"] = self.gain_s.value()
        if self.wide_s.value() != (s.get("wide_search_radius_px") or 0):
            patch["wide_search_radius_px"] = self.wide_s.value()
        if patch:
            self.command("set_state", patch=patch)

    # --- wyswietlanie ---

    def _enable(self):
        s = self.state
        have = self.info is not None and s is not None
        for w in (self.off_b, self.mon_b, self.guide_b, self.method_s, self.reacquire_b, self.home_b,
                  self.apply_b, self.exp_s, self.gain_s, self.wide_s, self.step_s, *self.pad):
            w.setEnabled(have)
        single = have and s.get("method") != "fiber"
        self.drop_b.setEnabled(bool(single and s.get("mode") == "guiding" and s.get("acquired")))
        self.reacquire_b.setEnabled(bool(single))
        hole = (s or {}).get("hole_candidate") or {}
        self.refine_b.setEnabled(bool(have and hole.get("refinable")))

    def _show_controls(self, s):
        mode = s.get("mode")
        for m, b in zip(MODES, (self.off_b, self.mon_b, self.guide_b)):
            theme.paint(b, bg=MODE_COLORS[m] if m == mode else None,
                        extra="font-weight: bold;" if m == mode else "")
        i = self.method_s.findData(s.get("method"))
        if i < 0:
            self.method_s.addItem(str(s.get("method")), s.get("method"))
            i = self.method_s.count() - 1
        self.method_s.blockSignals(True)
        self.method_s.setCurrentIndex(i)
        self.method_s.blockSignals(False)

        hole = s.get("hole_candidate") or {}
        if hole.get("refinable") and hole.get("offset_px") is not None:
            self.refine_b.setText(f"Refine reticle {float(hole['offset_px']):.1f} px")
        else:
            self.refine_b.setText("Refine reticle")
        self.refine_b.setToolTip(hole.get("reason") or "no reticle-target measurement - put a bright source on "
                                                       "the reticle")

        # pola kamery: nie nadpisujemy tego, co operator wlasnie zmienia (rozni sie od poprzedniego stanu)
        prev = self.prev_state or {}
        for widget, key, default in ((self.exp_s, "exp_time", 1.0), (self.gain_s, "gain", -1),
                                     (self.wide_s, "wide_search_radius_px", 0)):
            value = s.get(key)
            if value is None:
                value = default
            if not widget.hasFocus() or prev.get(key) != s.get(key):
                widget.blockSignals(True)
                widget.setValue(value)
                widget.blockSignals(False)

    def _show_diagnostics(self, s):
        acq = bool(s.get("acquired"))
        self.diag["acquired"].setText("yes" if acq else "no")
        theme.paint(self.diag["acquired"], fg="ok_fg" if acq else "warn_fg")
        adu = s.get("acquired_adu")
        sat = float((s.get("method_params") or {}).get("saturation_adu") or 62000)
        self.diag["adu"].setText(_num(adu, "{:.0f}"))
        theme.paint(self.diag["adu"], fg="bad_fg" if adu is not None and float(adu) >= sat else None)
        self.diag["fwhm"].setText(_num(s.get("fwhm_recent")))
        self.diag["phase"].setText(str(s.get("frame_phase") or "—"))
        exp = s.get("current_exp_time") or s.get("exp_time")
        self.diag["exp"].setText(_num(exp, "{:g} s") + (" (auto)" if s.get("current_exp_time") else ""))
        r = _xy(s.get("central_point"))
        home = _xy(s.get("central_point_default"))
        moved = math.dist(r, home) if r and home else 0.0
        self.diag["reticle"].setText((f"{r[0]:.1f}, {r[1]:.1f}" if r else "—")
                                     + (f"   moved {moved:.1f} px from home" if moved > RETICLE_MOVED_PX else ""))
        self.diag["reticle"].setToolTip(f"reticle moved {moved:.1f} px from the calibrated position "
                                        f"{home[0]:.1f}, {home[1]:.1f} (Reticle home brings it back)"
                                        if moved > RETICLE_MOVED_PX else "reticle at the calibrated position")
        theme.paint(self.diag["reticle"], fg="warn_fg" if moved > RETICLE_MOVED_PX else None)
        a = _xy(s.get("guide_anchor"))
        self.diag["anchor"].setText(f"{a[0]:.1f}, {a[1]:.1f}" if a else "—")
        self.diag["delta"].setText(f"{_num(s.get('last_correction_dx_px'))}, {_num(s.get('last_correction_dy_px'))}")
        hole = s.get("hole_candidate") or {}
        self.diag["hole"].setText(f"{_num(hole.get('offset_px'))} px, snr {_num(hole.get('snr'), '{:.0f}')}"
                                  if hole else "—")

    # --- dryf ---

    def clear_drift(self):
        self.drift.clear()
        self.drift_ref = None
        self.draw_drift()

    def _update_drift(self, s):
        """Drift = star position minus a fixed reference: the guide anchor, else the position at the lock; a new
        reference (and a fresh plot) after a mode change or a new lock (as in the web UI)."""
        prev = self.prev_state or {}
        star = _xy(s.get("acquired_pos")) if s.get("acquired") else None
        new_session = prev.get("mode") != s.get("mode") or (not prev.get("acquired") and s.get("acquired"))
        ref = _xy(s.get("guide_anchor"))
        if ref is None:
            ref = self.drift_ref if (self.drift_ref and not new_session) else star
        if ref != self.drift_ref:
            self.drift.clear()
            self.drift_ref = ref
        now = time.time()
        if star and self.drift_ref and s.get("mode") != "off":
            self.drift.append((now, star[0] - self.drift_ref[0], star[1] - self.drift_ref[1]))
        while self.drift and now - self.drift[0][0] > DRIFT_WINDOW_S:
            self.drift.popleft()
        if self.isVisible():
            self.draw_drift()

    def draw_drift(self):
        ax, ax2 = self.drift_ax, self.scatter_ax
        ax.clear()
        ax2.clear()
        now = time.time()
        t = [p[0] - now for p in self.drift]
        dx = [p[1] for p in self.drift]
        dy = [p[2] for p in self.drift]
        lim = max([5.0] + [abs(v) * 1.1 for v in dx + dy])
        dim, text = theme.hex("dim_fg"), theme.hex("text")
        # przebieg w czasie: x i y, wspolna skala z rozrzutem
        ax.axhline(0, color=dim, lw=0.5)
        ax.plot(t, dx, color=DRIFT_X_COLOR, lw=1)
        ax.plot(t, dy, color=DRIFT_Y_COLOR, lw=1)
        ax.set_ylim(-lim, lim)
        ax.set_xlim(-DRIFT_WINDOW_S, 0)
        ax.set_xticks([-300, -240, -180, -120, -60, 0], ["-5 min", "-4", "-3", "-2", "-1", "0"])
        ax.tick_params(labelsize=7, pad=1)
        ax.text(0.01, 0.97, "x", color=DRIFT_X_COLOR, transform=ax.transAxes, va="top", fontsize=8)
        ax.text(0.05, 0.97, "y", color=DRIFT_Y_COLOR, transform=ax.transAxes, va="top", fontsize=8)
        # rozrzut x-y (os y obrazu w dol, jak na podgladzie)
        ax2.axhline(0, color=dim, lw=0.5)
        ax2.axvline(0, color=dim, lw=0.5)
        if dx:
            ax2.plot(dx, dy, ".", color=dim, ms=3, alpha=0.5)
            ax2.plot(dx[-1:], dy[-1:], "o", color=text, ms=4)
        ax2.set_xlim(-lim, lim)
        ax2.set_ylim(lim, -lim)
        ax2.set_aspect("equal")
        ax2.tick_params(labelsize=7, pad=1)
        theme.style_figure(self.drift_fig, (ax,))
        theme.style_figure(self.scatter_fig, (ax2,))
        self.drift_canvas.draw_idle()
        self.scatter_canvas.draw_idle()

        if len(dx) > 1:
            rx = math.sqrt(sum(v * v for v in dx) / len(dx))
            ry = math.sqrt(sum(v * v for v in dy) / len(dy))
            self.rms_l.setText(f"RMS [px]  x {rx:.2f}  y {ry:.2f}  total {math.hypot(rx, ry):.2f}")
        else:
            self.rms_l.setText("RMS [px]  —")

    # --- motyw i uklad ---

    def apply_theme(self):
        theme.paint(self.journal_e, bg="field_bg")
        self.scene.draw_state(self.state)
        self.show_service()
        if self.state:
            self._show_controls(self.state)
            self._show_diagnostics(self.state)
        self.draw_drift()

    SIDE = 170          # zblizenie reticle i rozrzut: dwa kwadraty tej samej wielkosci
    COLUMN = 2 * SIDE + 6

    def mkUI(self):
        # pasek: teleskop/kamera, status serwisu, tryb, metoda, cel
        bar = QHBoxLayout()
        self.title_l = QLabel("")
        font = self.title_l.font()
        font.setBold(True)
        self.title_l.setFont(font)
        self.service_l = QLabel("")
        self.service_l.setToolTip("status of the guider service (services01)")
        self.off_b = QPushButton("OFF")
        self.mon_b = QPushButton("MONITOR")
        self.guide_b = QPushButton("GUIDE")
        self.off_b.setToolTip("off: the camera idles, nothing is sent to the mount")
        self.mon_b.setToolTip("monitoring: frames and solver, no pulses")
        self.guide_b.setToolTip("guiding: holds the star at the anchor (single star) or at the fibre (fiber)")
        for b, m in ((self.off_b, "off"), (self.mon_b, "monitoring"), (self.guide_b, "guiding")):
            b.clicked.connect(lambda checked=False, m=m: self.set_mode(m))
        self.method_s = QComboBox()
        for value, name in METHODS:
            self.method_s.addItem(name, value)
        self.method_s.activated.connect(self.method_chosen)
        self.method_s.setToolTip("single star: holds the star you clicked; fiber: centres all light on the fibre")
        self.reacquire_b = QPushButton("Re-acquire")
        self.reacquire_b.setToolTip("force a wide search around the target (R)")
        self.reacquire_b.clicked.connect(self.reacquire)
        self.drop_b = QPushButton("Drop → reticle")
        self.drop_b.setToolTip("move the held star onto the reticle (fibre); needs single star + guiding + acquired")
        self.drop_b.clicked.connect(self.drop_to_reticle)
        self.refine_b = QPushButton("Refine reticle")
        self.refine_b.clicked.connect(self.refine_reticle)
        self.home_b = QPushButton("Reticle home")
        self.home_b.setToolTip("back to the calibrated fibre position (H)")
        self.home_b.clicked.connect(self.reticle_home)
        bar.addWidget(self.title_l)
        bar.addWidget(self.service_l)
        bar.addSpacing(12)
        for w in (self.off_b, self.mon_b, self.guide_b):
            bar.addWidget(w)
        bar.addSpacing(12)
        bar.addWidget(self.method_s)
        bar.addStretch(1)
        for w in (self.reacquire_b, self.drop_b, self.refine_b, self.home_b):
            bar.addWidget(w)

        # obraz
        self.scene = GuiderScene()
        self.frame_v = FrameView(self.scene, self)
        self.frame_v.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.frame_v.setToolTip("left click: lock star · right click: move reticle · wheel: zoom · middle drag: pan\n"
                                "keys: arrows pulse, 1-4 step, R re-acquire, D candidates, H reticle home, 0 fit")

        # prawa kolumna, stala szerokosc
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        # zblizenie reticle | rozrzut dryfu - dwa rowne kwadraty
        self.closeup_v = CloseUpView(self.scene)
        self.closeup_v.setFixedSize(self.SIDE, self.SIDE)
        self.closeup_v.setToolTip("close-up of the reticle (fibre entrance); dashed ring = measured entrance")
        self.scatter_fig = Figure(dpi=100)
        self.scatter_canvas = FigureCanvas(self.scatter_fig)
        self.scatter_canvas.setFixedSize(self.SIDE, self.SIDE)
        self.scatter_ax = self.scatter_fig.add_axes([0.17, 0.12, 0.8, 0.8])
        self.scatter_canvas.setToolTip("drift x-y of the last 5 min; big dot = latest")
        squares = QHBoxLayout()
        squares.setSpacing(6)
        squares.addWidget(self.closeup_v)
        squares.addWidget(self.scatter_canvas)
        col.addLayout(squares)

        # dryf w czasie: cala szerokosc kolumny
        self.drift_fig = Figure(dpi=100)
        self.drift_canvas = FigureCanvas(self.drift_fig)
        self.drift_canvas.setFixedSize(self.COLUMN, 110)
        self.drift_ax = self.drift_fig.add_axes([0.08, 0.2, 0.9, 0.76])
        col.addWidget(self.drift_canvas)
        rms_row = QHBoxLayout()
        self.rms_l = QLabel("RMS [px]  —")
        clear_b = QPushButton("clear")
        clear_b.setToolTip("clear the drift plots")
        clear_b.clicked.connect(self.clear_drift)
        rms_row.addWidget(self.rms_l, 1)
        rms_row.addWidget(clear_b)
        col.addLayout(rms_row)
        col.addWidget(self._hline())

        # diagnostyka: dwie pary nazwa-wartosc w wierszu
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        self.diag = {}
        cells = [("acquired", "Acquired"), ("adu", "ADU"), ("fwhm", "FWHM"), ("phase", "Phase"),
                 ("exp", "Exp"), ("delta", "Last Δ"), ("anchor", "Anchor"), ("hole", "Hole"),
                 ("reticle", "Reticle"), ("focus", "Focus")]
        wide = ("reticle", "focus")         # dluzsze teksty: caly wiersz
        r = c = 0
        for key, name in cells:
            name_l = QLabel(name + ":")
            theme.paint(name_l, fg="dim_fg")
            self.diag[key] = QLabel("—")
            if key in wide:
                if c:
                    r, c = r + 1, 0
                grid.addWidget(name_l, r, 0)
                grid.addWidget(self.diag[key], r, 1, 1, 3)
                r += 1
                continue
            grid.addWidget(name_l, r, 2 * c)
            grid.addWidget(self.diag[key], r, 2 * c + 1)
            r, c = (r + 1, 0) if c else (r, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        col.addLayout(grid)
        col.addWidget(self._hline())

        # kamera: Exp + presety | Gain | Wide r | Apply
        self.exp_s = QDoubleSpinBox()
        self.exp_s.setRange(0.001, 30)
        self.exp_s.setDecimals(3)
        self.exp_s.setSuffix(" s")
        self.exp_p = QComboBox()
        self.exp_p.addItem("▾")
        for p in EXP_PRESETS:
            self.exp_p.addItem(f"{p:g} s", p)
        self.exp_p.setToolTip("exposure presets")
        self.exp_p.activated.connect(self._preset)
        self.gain_s = QSpinBox()
        self.gain_s.setRange(-1, 1000)
        self.gain_s.setSpecialValueText("default")
        self.wide_s = QSpinBox()
        self.wide_s.setRange(0, 2000)
        self.wide_s.setSuffix(" px")
        self.wide_s.setToolTip("search radius (wide search): stars can be selected and re-acquired only inside\n"
                               "this circle (the dashed circle around the reticle)")
        self.apply_b = QPushButton("Apply")
        self.apply_b.setToolTip("send the changed exposure / gain / search radius to the guider")
        self.apply_b.clicked.connect(self.apply_camera)
        cam = QGridLayout()
        cam.setHorizontalSpacing(4)
        cam.setVerticalSpacing(2)
        cam.addWidget(QLabel("Exp"), 0, 0)
        cam.addWidget(self.exp_s, 0, 1)
        cam.addWidget(self.exp_p, 0, 2)
        cam.addWidget(QLabel("Gain"), 0, 3)
        cam.addWidget(self.gain_s, 0, 4)
        cam.addWidget(QLabel("Search r"), 1, 0)
        cam.addWidget(self.wide_s, 1, 1)
        cam.addWidget(self.apply_b, 1, 3, 1, 2)
        col.addLayout(cam)
        col.addWidget(self._hline())

        # impulsy guidera (piksele obrazu) + kandydaci
        up_b, down_b, left_b, right_b = (QPushButton(t) for t in ("↑", "↓", "←", "→"))
        up_b.clicked.connect(lambda: self.pulse(0, -1))
        down_b.clicked.connect(lambda: self.pulse(0, 1))
        left_b.clicked.connect(lambda: self.pulse(-1, 0))
        right_b.clicked.connect(lambda: self.pulse(1, 0))
        self.pad = (up_b, down_b, left_b, right_b)
        for b in self.pad:
            b.setFixedWidth(32)
            b.setToolTip("guider pulse: moves the star in the guider image by the step (arrow keys on the frame);\n"
                         "the guider converts pixels to pulses and keeps the lock - unlike the Mount pulse window")
        self.step_s = QComboBox()
        for s in PULSE_STEPS:
            self.step_s.addItem(f"{s} px")
        self.step_s.setToolTip("pulse step (keys 1-4 on the frame)")
        pad = QGridLayout()
        pad.setSpacing(2)
        pad.addWidget(up_b, 0, 1, Qt.AlignmentFlag.AlignHCenter)
        pad.addWidget(left_b, 1, 0)
        pad.addWidget(self.step_s, 1, 1)
        pad.addWidget(right_b, 1, 2)
        pad.addWidget(down_b, 2, 1, Qt.AlignmentFlag.AlignHCenter)
        self.candidates_b = QPushButton("Candidates")
        self.candidates_b.setCheckable(True)
        self.candidates_b.setToolTip("show all stars the detector found in this frame (D)")
        self.candidates_b.toggled.connect(self._candidates)
        pad_row = QHBoxLayout()
        pad_row.addWidget(QLabel("Pulse"))
        pad_row.addLayout(pad)
        pad_row.addStretch(1)
        pad_row.addWidget(self.candidates_b, 0, Qt.AlignmentFlag.AlignBottom)
        col.addLayout(pad_row)
        col.addStretch(1)
        col_w = QWidget()
        col_w.setLayout(col)
        col_w.setFixedWidth(self.COLUMN)

        top = QHBoxLayout()
        top.addWidget(self.frame_v, 1)
        top.addWidget(col_w)

        # dziennik: niski pasek na dole
        self.journal_e = QTextEdit()
        self.journal_e.setReadOnly(True)
        self.journal_e.setFixedHeight(3 * self.journal_e.fontMetrics().lineSpacing() + 12)
        self.journal_e.setToolTip("guider events and journal, and replies to commands")

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.addLayout(bar)
        layout.addLayout(top, 1)
        layout.addWidget(self.journal_e)
        self.setLayout(layout)

    @staticmethod
    def _hline():
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _preset(self, index):
        value = self.exp_p.itemData(index)
        if value is not None:
            self.exp_s.setValue(value)
        self.exp_p.setCurrentIndex(0)

    def _candidates(self, on):
        self.scene.show_candidates = on
        self.scene.draw_state(self.state)
