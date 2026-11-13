#!/usr/bin/env python3
"""The Guider tab of the Aux window: a TOI client of the guider service (ocabox-tcs ``guiding_svc.guider``).

The service runs on services01 and does all the work (camera, solver, pulses); TOI, like the guider web UI
(``http://192.168.7.45:8090/``), only shows its state and sends commands. Interface: knowledge base,
"Guider service - NATS interface". Today only jk15 has a guider (``guider_beso``, the BESO fibre).

How the operator works it (agreed with mgorski 2026-11-11):
- left click = the star to guide on (``lock_at``); GUIDE holds it where it is (its *hold point*);
- right click = only a mark (a position, no command);
- Move to fiber: the held star (or the mark) to the fibre - in GUIDE closed loop (``drop_to_reticle``, star only), in
  MONITOR open loop (manual pulses in chunks, ±few px; star or mark);
- Find star (MONITOR only): the guider picks a star near the fibre itself (``acquire``);
- the fibre position (the service's ``central_point``): Calibrate fiber = the mark, Fiber: measured (the guider's
  own measurement of the hole, ``refine_reticle``), Fiber: config (back to the configured calibration);
  "center" instead of "fiber" for a guider that measures no fibre hole.
The service words reticle / anchor are fiber / hold point here.

This module is the window only. What feeds it (:class:`guider_client.GuiderLink`, over NATS):
- :meth:`GuiderTab.set_guiders` — discovered guider services, ``{tel: info}``,
- :meth:`GuiderTab.show_state` — ``PipelineState`` of the pipeline,
- :meth:`GuiderTab.show_frame` — JPEG bytes of a thumbnail,
- :meth:`GuiderTab.add_journal` — events and journal lines.
Commands go through :meth:`GuiderTab.command`, which checks control of the telescope and calls
``self.rpc(cmd, data)``.

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
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QSlider, QSpinBox, QTextEdit,
                             QVBoxLayout, QWidget)

from toi_theme import theme

logger = logging.getLogger(__name__)

DEFAULT_DIMENSIONS = (1936, 1216)       # guider_beso; the thumbnail payload says the real size
DRIFT_WINDOW_S = 300                    # dryf na wykresie i RMS: ostatnie 5 min (jak web UI)
PULSE_STEPS = [1, 5, 10, 30, 60, 100, 200]  # px obrazu (klawisze 1-7 na obrazie); 200 px ~ limit impulsu serwisu 5 s
PULSE_MIN_PX, PULSE_MAX_PX = 0.5, 200.0     # wpisany krok: ponizej 1 px serwis moze impuls pominac, powyzej ~200 przytnie
PULSE_WAIT_MAX = 6.0    # s - impuls reczny bez odpowiedzi blokuje pad najwyzej tyle (limit impulsu serwisu 5 s)
PULSE_SETTLE_S = 0.3    # s po koncu impulsow, zanim pad znow dziala
MOVE_CHUNK_PX = 150     # Move to fiber w MONITOR: kroki po tyle px na os (pod limitem impulsu ~195 px)
MOVE_SETTLE_S = 1.0     # s miedzy krokami (montaz sie uspokaja, guider widzi nowa klatke)
EXP_RANGE = (0.05, 10.0)        # s, suwak logarytmiczny
GAIN_RANGE = (0, 500)
SEARCH_RANGE = (50, 1000)       # px
METHODS = [("single_star", "single star"), ("fiber", "fiber")]
MODES = ["off", "monitoring", "guiding"]
# ostrosc teleskopu dla instrumentu guidera (BESO: oca-manual beso.md "Focusing"; nadpisuje toi.guider_focus) i
# tolerancja - dalej i guider wlaczony = ostrzezenie (przy ostrosci Andora kamera BESO widzi sam szum, 2026-11-10)
GUIDER_FOCUS = {"jk15": 21950}
FOCUS_TOLERANCE = 300
FIBER_MOVED_PX = 1.0        # pozycja wlokna dalej od konfiguracji - pokazujemy o ile
PULL_WARN_PX = 20.0         # guiding ciagnie gwiazde dalej do hold pointu - ostrzezenie (2026-11-10: zjazd ~400 px)
MODE_COLORS = {"off": None, "monitoring": "change_bg", "guiding": "ok_bg"}
# przelacznik GUIDING w oknie Mount (automat): ile czekamy na kolejne kroki
AUTO_MODE_S = 10        # s na potwierdzenie zmiany trybu przez serwis
AUTO_FIND_S = 20        # s na znalezienie gwiazdy (kilka klatek przy dluzszej ekspozycji)
# guiding wylaczony to nie blad: szary, nie czerwony
SWITCH_ON = "QCheckBox::indicator:checked {image: url(ICONS/SwitchOn.png)}" \
            "::indicator:unchecked {image: url(ICONS/SwitchOffGrey.png)}"
SWITCH_GREY = "QCheckBox::indicator:checked {image: url(ICONS/SwitchOnGrey.png)}" \
              "::indicator:unchecked {image: url(ICONS/SwitchOffGrey.png)}"
# kolory bez znaczenia ok/zle (czerwony = zle w TOI): serie dryfu i znacznik operatora
DRIFT_X_COLOR = "#a070d0"
DRIFT_Y_COLOR = "#40b0c0"
MARK_COLOR = "#e040e0"
SEARCH_COLOR = "#d0d0d0"        # kolo szukania: jasne, zeby bylo widac na ciemnym kadrze
# nakladka na kadrze: kadr jest zawsze ciemny, wiec stale jasne kolory zamiast *_fg motywu (w jasnych motywach ciemne,
# na czarnym tle prawie niewidoczne); znaczenie jak w TOI: zielony gwiazda, niebieski wlokno, zolty hold point
STAR_COLOR = "#40ff70"
FIBER_COLOR = "#50b8ff"
HOLD_COLOR = "#ffd040"
CANDIDATE_COLOR = "#a0a0a0"
HELP = ("Left click: star to guide on · Right click: mark a point · Wheel: zoom at the cursor · Middle drag: pan · "
        "0: fit · Arrows: pulse (MONITOR) · F: find star · Esc: clear mark")


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


def _pt(xy):
    return f"{xy[0]:.1f}, {xy[1]:.1f}" if xy else "—"


# ############### FRAME VIEW ##########################

class GuiderScene(QGraphicsScene):
    """The guider frame in sensor pixels with the overlays; shown by the main view and the fibre close-up. The scene
    is three times the frame, so the view can zoom around any pixel (also at the edge)."""

    def __init__(self):
        super().__init__()
        self.dims = DEFAULT_DIMENSIONS
        self._set_rect()
        self.pixmap_item = self.addPixmap(QPixmap())
        self.pixmap_item.setZValue(0)
        self.overlay = []               # elementy nakladki, przerysowywane przy kazdym stanie
        self.state = None
        self.mark = None                # (x, y) znacznik operatora (prawy klik)
        self.show_candidates = False

    def _set_rect(self):
        w, h = self.dims
        self.setSceneRect(-w, -h, 3 * w, 3 * h)

    @property
    def frame_rect(self):
        return QRectF(0, 0, *self.dims)

    def set_dimensions(self, dims):
        dims = (int(dims[0]), int(dims[1]))
        if dims != self.dims and dims[0] > 0 and dims[1] > 0:
            self.dims = dims
            self._set_rect()
            self._fit_pixmap()
            return True
        return False

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
    def _pen(color, width=1.5, style=Qt.PenStyle.SolidLine, alpha=255):  # color: klucz motywu albo "#rrggbb"
        color = QColor(color) if color.startswith("#") else theme.qcolor(color)
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

    def _label(self, xy, text, color):
        item = self._add(self.addSimpleText(text))
        item.setBrush(QBrush(QColor(color) if color.startswith("#") else theme.qcolor(color)))
        item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)     # tekst zawsze tej samej wielkosci
        item.setPos(xy[0], xy[1])
        return item

    def _cross(self, xy, r_in, r_out, pen):
        x, y = xy
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self._line((x + dx * r_in, y + dy * r_in), (x + dx * r_out, y + dy * r_out), pen)

    def redraw(self):
        self.draw_state(self.state)

    def draw_state(self, state):
        """Overlays after the guider state ``state`` (``PipelineState`` dict, or None) and the operator's mark."""
        self.state = state
        for item in self.overlay:
            self.removeItem(item)
        self.overlay = []
        if self.mark:
            pen = self._pen(MARK_COLOR, 1.5)
            self._cross(self.mark, 3, 12, pen)
            self._label((self.mark[0] + 8, self.mark[1] + 8), "mark", MARK_COLOR)
        if not state:
            return
        method = state.get("method")
        mode = state.get("mode")
        fiber = _xy(state.get("central_point"))
        # promien otworu: z parametrow metody fiber, inaczej z detektora otworu (single star go nie ma)
        fiber_r = float((state.get("method_params") or {}).get("fiber_radius_px")
                        or (state.get("hole_detect") or {}).get("radius_px") or 5.0)

        # kolo szukania gwiazd: klikniecia i Find star tylko w nim
        search_r = state.get("wide_search_radius_px")
        if fiber and search_r and method != "fiber":
            self._circle(fiber, float(search_r), self._pen(SEARCH_COLOR, 1.5, Qt.PenStyle.DashLine, 220))

        # kandydaci z detekcji (klawisz D)
        if self.show_candidates and method != "fiber":
            pen = self._pen(CANDIDATE_COLOR, 1)
            for cand in state.get("candidates") or []:
                c = _xy(cand)
                if c:
                    self._add(self.addRect(QRectF(c[0] - 6, c[1] - 6, 12, 12), pen))

        # wlokno (centrum): krzyz z otwartym srodkiem i okrag promienia otworu
        if fiber:
            pen = self._pen(FIBER_COLOR, 1.5)
            self._cross(fiber, fiber_r * 2, fiber_r * 6, pen)
            self._circle(fiber, fiber_r, self._pen(FIBER_COLOR, 1, Qt.PenStyle.DotLine))
            if method == "fiber":
                win = float((state.get("method_params") or {}).get("analysis_radius_px") or 15.0)
                self._add(self.addRect(QRectF(fiber[0] - win, fiber[1] - win, 2 * win, 2 * win),
                                       self._pen(FIBER_COLOR, 1, Qt.PenStyle.DashLine, 160)))

        # zmierzone wejscie swiatlowodu (Fiber: measured)
        hole = state.get("hole_candidate") or {}
        hole_xy = _xy((hole.get("x"), hole.get("y"))) if hole else None
        if hole_xy:
            self._circle(hole_xy, fiber_r, self._pen(HOLD_COLOR, 1.5, Qt.PenStyle.DashLine))

        # hold point: gdzie guiding trzyma gwiazde (tylko w guiding i gdy rozny od wlokna)
        hold = _xy(state.get("guide_anchor"))
        if mode == "guiding" and hold and (not fiber or math.dist(hold, fiber) > 0.5):
            pen = self._pen(HOLD_COLOR, 1.5, Qt.PenStyle.DashLine)
            self._cross(hold, 4, 14, pen)
            self._label((hold[0] + 10, hold[1] + 10), "hold point", HOLD_COLOR)

        # gwiazda trzymana w tej klatce + linia do celu
        star = _xy(state.get("acquired_pos"))
        if star and state.get("acquired"):
            self._circle(star, 10, self._pen(STAR_COLOR, 2.5))      # ADU - w diagnostyce obok
            target = hold if hold else fiber
            if mode == "guiding" and target and math.dist(star, target) > 0.5:
                self._line(star, target, self._pen(STAR_COLOR, 1))

        # przewidywane polozenie po impulsie
        pred = _xy(state.get("predicted_pos"))
        if pred and star:
            self._line(star, pred, self._pen(FIBER_COLOR, 1, Qt.PenStyle.DotLine))
            self._circle(pred, 6, self._pen(FIBER_COLOR, 1, Qt.PenStyle.DotLine))


class FrameView(QGraphicsView):
    """Main view of the guider frame. Mouse: left - the star to guide on, right - mark, wheel - zoom keeping the pixel
    under the cursor, middle drag - pan. Keys when it has focus: arrows - pulse by the step (MONITOR), 1-7 step,
    F find star, D candidates, Esc clear mark, +/-/0 zoom."""

    def __init__(self, scene, tab):
        super().__init__(scene)
        self.tab = tab
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)     # zoom: wheelEvent sam trzyma punkt
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setMinimumSize(240, 150)
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
        self.fitInView(self.scene().frame_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.scene().frame_rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.zoomed:
            self.fit()

    def zoom(self, factor, at=None):
        """Zoom by ``factor`` keeping the scene point under the viewport position ``at`` (None - the middle) where it
        is; not further out than the whole frame."""
        if factor < 1 and self.transform().m11() * factor < self._fit_scale():
            self.fit()
            return
        at = self.viewport().rect().center() if at is None else at
        before = self.mapToScene(at)
        self.zoomed = True
        self.scale(factor, factor)
        after = self.mapToScene(at)
        # przesuwamy tak, zeby punkt sceny spod kursora wrocil pod kursor
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center - (after - before))

    def _fit_scale(self):
        r = self.scene().frame_rect
        vp = self.viewport().rect()
        return min(vp.width() / r.width(), vp.height() / r.height())

    def wheelEvent(self, event):
        self.zoom(1.25 if event.angleDelta().y() > 0 else 0.8, event.position().toPoint())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            return
        p = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton:
            self.tab.click_star(p.x(), p.y())
        elif event.button() == Qt.MouseButton.RightButton:
            self.tab.set_mark((p.x(), p.y()))

    def mouseMoveEvent(self, event):
        if self._pan is not None:
            d = event.position() - self._pan
            self._pan = event.position()
            self.zoomed = True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))

    def mouseReleaseEvent(self, event):
        self._pan = None

    def keyPressEvent(self, event):
        key = event.key()
        arrows = {Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1), Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0)}
        steps = {getattr(Qt.Key, f"Key_{i + 1}"): i for i in range(len(PULSE_STEPS))}
        if key in arrows:
            if not event.isAutoRepeat():    # przytrzymany klawisz nie sypie impulsami (2026-11-10: 5 w sekundzie)
                self.tab.pulse(*arrows[key])
        elif key in steps:
            self.tab.set_pulse_step(steps[key])
        elif key == Qt.Key.Key_F:
            self.tab.find_star()
        elif key == Qt.Key.Key_D:
            self.tab.candidates_b.toggle()
        elif key == Qt.Key.Key_Escape:
            self.tab.set_mark(None)
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom(1.25)
        elif key == Qt.Key.Key_Minus:
            self.zoom(0.8)
        elif key == Qt.Key.Key_0:
            self.fit()
        else:
            super().keyPressEvent(event)


class CloseUpView(QGraphicsView):
    """Close-up of the fibre region: the same scene, centred on the fibre position, fixed zoom."""

    HALF_SIZE = 25      # px sensora od wlokna

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
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


class SliderEntry(QWidget):
    """Name | slider | entry field, linked; ``to_value(i)`` / ``to_index(v)`` map slider steps to the value (log for
    exposure). ``send(value)`` when the operator settles: slider released, Enter or leaving the field - only if the
    value differs from the guider's (:meth:`dirty`). A value from the guider (:meth:`show`) does not overwrite what
    the operator is setting."""

    def __init__(self, name, steps, to_value, to_index, entry, send, tip=""):
        super().__init__()
        self.to_value, self.to_index = to_value, to_index
        self.guider = None              # wartosc z serwisu
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, steps)
        self.slider.setMinimumWidth(80)
        self.entry = entry
        self.entry.setKeyboardTracking(False)
        self.name_l = QLabel(name)
        self.slider.valueChanged.connect(self._from_slider)
        self.entry.valueChanged.connect(self._from_entry)
        self.send = send
        self.entry.editingFinished.connect(self._settled)
        self.slider.sliderReleased.connect(self._settled)
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.name_l)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.entry)
        self.setLayout(lay)
        for w in (self.name_l, self.slider, self.entry):
            w.setToolTip(tip)

    def value(self):
        return self.entry.value()

    def dirty(self):
        return self.guider is not None and abs(float(self.value()) - float(self.guider)) > 1e-9

    def _from_slider(self, i):
        self.entry.blockSignals(True)
        self.entry.setValue(self.to_value(i))
        self.entry.blockSignals(False)
        self.changed()

    def _from_entry(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(self.to_index(v))
        self.slider.blockSignals(False)
        self.changed()

    def changed(self):
        """the value in the widgets changed (operator or guider)"""
        theme.paint(self.entry, bg="input_edit_bg" if self.dirty() else None)

    def _settled(self):
        if self.dirty():
            self.send(self.value())

    def show(self, value):
        """value published by the guider; kept in the widgets unless the operator has changed them"""
        if value is None:
            return
        was_dirty = self.dirty()
        self.guider = value
        if was_dirty or self.slider.isSliderDown() or self.entry.hasFocus():
            self.changed()
            return
        for w in (self.slider, self.entry):
            w.blockSignals(True)
        self.entry.setValue(value)
        self.slider.setValue(self.to_index(value))
        for w in (self.slider, self.entry):
            w.blockSignals(False)
        self.changed()


def _log_slider(lo, hi, steps):
    k = math.log(hi / lo)

    def to_value(i):
        v = lo * math.exp(k * i / steps)
        return float(f"{v:.2g}")        # 2 cyfry znaczace: 0.05, 0.12, 1.5, 10

    def to_index(v):
        return round(steps * math.log(max(lo, min(hi, float(v))) / lo) / k)
    return to_value, to_index


def _lin_slider(lo, hi, step):
    def to_value(i):
        return lo + i * step

    def to_index(v):
        return round((max(lo, min(hi, float(v))) - lo) / step)
    return (hi - lo) // step, to_value, to_index


# ############### TAB ##########################

class GuiderTab(QWidget):
    """Guider of the active telescope: frame with overlays, drift, controls. See the module docstring."""

    STALE_S = 10        # s bez stanu przy wlaczonym guiderze = cos nie tak (serwis, NATS)
    SIDE = 170          # zblizenie wlokna i rozrzut dryfu: dwa kwadraty
    COLUMN = 2 * SIDE + 6   # prawa kolumna

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
        self.pulse_until = 0.0          # time.time(), do kiedy trwa ostatni impuls reczny - wtedy nie wysylamy nowego
        self.pulse_step = 10.0          # krok impulsu guidera [px obrazu] (okno Pulse - lista albo wpisany, klawisze 1-7)
        self.moving = False             # Move to fiber w MONITOR (seria impulsow) trwa
        self.auto_task = None           # automat przelacznika GUIDING z okna Mount
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
            self.scene.mark = None
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
        self.sync_mount_switch()

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
            txt += "  ADJ on"
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
        QTimer.singleShot(0, self._fit_frame_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_frame_height)

    def _fit_frame_height(self):
        """The frame gets the height of the image at the column width (no black bars above and below); the rest of
        the left column goes to the controls below it."""
        w, h = self.scene.dims
        width = self.frame_v.width()
        free = self.left_w.height() - self.controls_w.sizeHint().height() - self.help_l.sizeHint().height() \
            - 3 * self.left_lay.spacing() - (self.pull_l.sizeHint().height() if self.pull_l.isVisible() else 0)
        height = max(self.frame_v.minimumHeight(), min(round(width * h / w), free))
        if height != self.frame_v.height():
            self.frame_v.setFixedHeight(height)

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
        self._show_pull(state)
        self._enable()
        self.sync_mount_switch()

    def show_frame(self, data, dims=None):
        """JPEG (bytes) of the latest guider frame; ``dims`` = sensor size from the thumbnail message."""
        pm = QPixmap()
        if not pm.loadFromData(data):
            logger.warning("GuiderTab: thumbnail not decoded")
            return
        if dims and self.scene.set_dimensions(dims):
            self._fit_frame_height()
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

    # --- slowa: wlokno albo centrum ---

    def fiber_word(self):
        """"fiber" for a guider that measures a fibre hole (BESO), "center" otherwise"""
        return "fiber" if ((self.state or {}).get("hole_detect") or {}).get("enabled") else "center"

    # --- komendy ---

    def _may_command(self):
        if self.info is None:
            return False
        if not self.parent.tel_acces.get(self.tel):
            self.parent.WarningWindow("WARNING: U don't have control")
            return False
        if self.rpc is None:
            self.add_journal("not sent: guider NATS not connected", "warning")
            return False
        return True

    def command(self, cmd, done=None, **data):
        """Send command ``cmd`` to the guider of the shown telescope, if TOI has control of it; ``done(reply)``
        (reply None - no reply) is called when it comes. Returns True when sent."""
        if not self._may_command():
            return False
        self.add_journal(f"→ {cmd} {data or ''}", "sent")
        asyncio.ensure_future(self._send(cmd, data, done))
        return True

    async def _send(self, cmd, data, done=None):
        reply = await self._call(cmd, data)
        if done is not None:
            try:
                done(reply)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"GuiderTab: {cmd} reply handler: {e!r}")

    async def _call(self, cmd, data):
        """RPC + operator-readable errors / refusals in the journal; reply or None"""
        try:
            reply = await self.rpc(cmd, data)
        except Exception as e:      # noqa: BLE001 - odpowiedz operatorowi, nie wyjatek z Qt
            self.add_journal(f"{cmd}: no reply ({e})", "error")
            return None
        result = reply.get("result") if isinstance(reply, dict) else None
        if isinstance(reply, dict) and reply.get("status") != "ok":
            self.add_journal(f"{cmd}: {reply.get('error')} {reply.get('detail', '')}", "error")
        elif isinstance(result, dict) and result.get("status") not in (None, "ok"):
            why = result.get("reason") or result.get("error") or result.get("message") or result.get("status")
            self.add_journal(f"{cmd} refused: {why}", "warning")
        return reply

    # --- przelacznik GUIDING w oknie Mount ---

    def auto_running(self):
        return self.auto_task is not None and not self.auto_task.done()

    def sync_mount_switch(self):
        """GUIDING switch of the Mount window = the guider of the active telescope is in GUIDE (MONITOR / OFF = off);
        grey and disabled without a guider; on while the automat is starting it."""
        c = getattr(getattr(self.parent, "mntGui", None), "guiding_c", None)
        if c is None:
            return
        have = self.info is not None and self.state is not None
        guiding = bool(have and self.state.get("mode") == "guiding")
        c.blockSignals(True)
        c.setChecked(guiding or self.auto_running())
        c.blockSignals(False)
        c.setEnabled(have)
        c.setText("GUIDING (starting…): " if self.auto_running() else "GUIDING: ")
        theme.paint(c, extra=SWITCH_ON if have else SWITCH_GREY)
        c.setToolTip("guider is in GUIDE" if guiding else
                     "on: the guider starts, finds a star near the fiber and guides on it (Aux → Guider)" if have
                     else "no guider for this telescope")

    def mount_switch(self, on):
        """The operator clicked GUIDING in the Mount window."""
        if on:
            if not self.auto_running() and self._may_command():
                self.auto_task = asyncio.ensure_future(self._auto_guide())
        else:
            if self.auto_running():
                self.auto_task.cancel()
                self.add_journal("auto guide stopped by the operator", "warning")
            if (self.state or {}).get("mode") == "guiding":
                self.command("set_mode", mode="monitoring")
        self.sync_mount_switch()

    async def _wait_state(self, ok, timeout):
        """wait for a guider state with ``ok(state)``; True / False after ``timeout`` s"""
        end = time.time() + timeout
        while time.time() < end:
            if self.state and ok(self.state):
                return True
            await asyncio.sleep(0.2)
        return False

    async def _auto_guide(self):
        """Mount window GUIDING on: OFF -> MONITOR, find a star if none is held, GUIDE. Any failure: a warning with
        the reason, the guider stays where it got (MONITOR at most), the switch shows the real state."""
        def fail(why):
            self.add_journal(f"auto guide: {why}", "warning")
            self.parent.WarningWindow(f"GUIDING not started: {why}")
        try:
            self.add_journal("→ auto guide (Mount window GUIDING)", "sent")
            s = self.state or {}
            if s.get("mode") == "off":
                if await self._call("set_mode", {"mode": "monitoring"}) is None:
                    return fail("the guider did not answer")
                if not await self._wait_state(lambda st: st.get("mode") == "monitoring", AUTO_MODE_S):
                    return fail("the guider did not switch to MONITOR")
            s = self.state or {}
            if s.get("method") != "fiber" and not s.get("acquired"):
                if await self._call("acquire", {}) is None:
                    return fail("the guider did not answer")
                if not await self._wait_state(lambda st: st.get("acquired"), AUTO_FIND_S):
                    return fail(f"no star found near the {self.fiber_word()} in {AUTO_FIND_S} s "
                                f"(focus? exposure? search radius?)")
            if await self._call("set_mode", {"mode": "guiding"}) is None:
                return fail("the guider did not answer")
            if not await self._wait_state(lambda st: st.get("mode") == "guiding", AUTO_MODE_S):
                return fail("the guider did not switch to GUIDE")
            star = _xy((self.state or {}).get("acquired_pos"))
            self.add_journal("auto guide: guiding" + (f" on the star at {_pt(star)}" if star else ""))
        finally:
            self.auto_task = None
            self.sync_mount_switch()

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
        if s.get("mode") == "guiding":
            # serwis: lock_at w guiding ustawia hold point na nowej gwiezdzie, ale mierzy jeszcze stara i ciagnie ja
            # setki px (2026-11-10 02:55 i 2026-11-11 03:23) - wybor gwiazdy tylko w MONITOR
            self.add_journal("select a star in MONITOR (in GUIDE the guider would drag the old star to the new one)",
                             "warning")
            return
        fiber = _xy(s.get("central_point"))
        r = s.get("wide_search_radius_px")
        if fiber and r and math.dist((x, y), fiber) > float(r):
            self.add_journal("star outside the search circle - not selected (make the search radius larger)",
                             "warning")
            return
        self.command("lock_at", x=round(x, 1), y=round(y, 1))

    def set_mark(self, xy):
        """Right click: a mark only (no command); Move to fiber / Calibrate fiber use it; None - clear."""
        self.scene.mark = (round(xy[0], 1), round(xy[1], 1)) if xy else None
        self.scene.redraw()
        self._show_mark()
        self._enable()

    def find_star(self):
        s = self.state or {}
        if s.get("mode") != "monitoring" or s.get("method") == "fiber":
            self.add_journal("Find star only in MONITOR (in GUIDE the old hold point would stay)", "warning")
            return
        self.command("acquire")

    def move_to_fiber(self):
        s = self.state or {}
        mode = s.get("mode")
        fiber = _xy(s.get("central_point"))
        mark = self.scene.mark
        star = _xy(s.get("acquired_pos")) if s.get("acquired") else None
        if mode == "guiding":
            if mark:
                self.add_journal(f"a mark can be moved to the {self.fiber_word()} only in MONITOR "
                                 f"(clear the mark with Esc to move the guided star)", "warning")
                return
            self.command("drop_to_reticle")
            return
        if mode != "monitoring" or not fiber:
            return
        point = mark or star
        if point is None:
            self.add_journal("nothing to move: select a star (left click) or mark a point (right click)", "warning")
            return
        if self.moving or not self._may_command():
            return
        asyncio.ensure_future(self._move_open_loop(point, fiber, "mark" if mark else "star"))

    async def _move_open_loop(self, point, fiber, what):
        """MONITOR: move ``point`` to ``fiber`` with manual pulses, in chunks under the service pulse limit, each after
        the previous one is done. Open loop (pulse model): within a few px; GUIDE + Move to fiber for the exact
        position. Stops when the mode changes."""
        dx, dy = fiber[0] - point[0], fiber[1] - point[1]
        n = max(1, math.ceil(max(abs(dx), abs(dy)) / MOVE_CHUNK_PX))
        self.moving = True
        self._enable()
        self.add_journal(f"→ moving the {what} {math.hypot(dx, dy):.0f} px to the {self.fiber_word()} "
                         f"({n} pulse{'s' if n > 1 else ''})", "sent")
        try:
            for i in range(n):
                if (self.state or {}).get("mode") != "monitoring":
                    self.add_journal("move stopped: the guider left MONITOR", "warning")
                    return
                reply = await self._call("pulse_pixels", {"dx_px": round(dx / n, 1), "dy_px": round(dy / n, 1)})
                if reply is None or reply.get("status") != "ok":
                    return
                await asyncio.sleep(self._pulses_s(reply) + MOVE_SETTLE_S)
            if what == "mark":
                self.set_mark(None)     # punkt jest teraz na wloknie
            self.add_journal(f"{what} moved to the {self.fiber_word()} (open loop, ±few px)")
        finally:
            self.moving = False
            self._enable()

    @staticmethod
    def _pulses_s(reply):
        total = 0.0
        result = reply.get("result") if isinstance(reply, dict) else None
        for p in (result or {}).get("pulses") or []:
            try:
                total += float(p.get("duration_ms") or 0) / 1000
            except (TypeError, ValueError, AttributeError):
                pass
        return total

    def calibrate_fiber(self):
        """The mark becomes the fibre position (``acquire_at``) - after a confirmation."""
        s = self.state or {}
        mark = self.scene.mark
        if not mark:
            return
        word = self.fiber_word()
        fiber = _xy(s.get("central_point"))
        config = _xy(s.get("central_point_default"))
        lines = [f"Set the {word} position to the mark ({mark[0]:.1f}, {mark[1]:.1f})?", ""]
        if fiber:
            lines.append(f"It is {math.dist(mark, fiber):.1f} px from the current {word} position.")
        if config:
            lines.append(f"It is {math.dist(mark, config):.1f} px from the configured one ({_pt(config)}).")
        lines += ["", f"Move to {word} will then put stars there. Valid until the guider service restarts;",
                  f"'{word.capitalize()}: config' brings back the configured position."]
        if s.get("mode") == "monitoring":
            lines.append("In MONITOR this also drops the held star.")
        answer = QMessageBox.question(self, f"Calibrate {word}", "\n".join(lines))
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.command("acquire_at", x=mark[0], y=mark[1]):
            self.set_mark(None)

    def fiber_measured(self):
        self.command("refine_reticle")

    def fiber_config(self):
        config = _xy((self.state or {}).get("central_point_default"))
        if config:
            self.command("acquire_at", x=config[0], y=config[1])

    def pulse(self, sx, sy):
        if (self.state or {}).get("mode") != "monitoring":
            # w guiding serwis po recznym impulsie kasuje kotwice i bierze nowa z pierwszej detekcji (zjazd 2026-11-10)
            self.add_journal("manual pulses only in MONITOR (in GUIDE the guider would pick a new hold point)",
                             "warning")
            return
        if time.time() < self.pulse_until or self.moving:
            return      # poprzedni impuls jeszcze trwa - pad jest wtedy wylaczony, to tylko klawisze
        step = self.pulse_step
        self.pulse_until = time.time() + PULSE_WAIT_MAX     # do odpowiedzi; odpowiedz poda prawdziwy czas
        if self.command("pulse_pixels", done=self._pulse_done, dx_px=sx * step, dy_px=sy * step):
            self._enable()
        else:
            self.pulse_until = 0.0

    def _pulse_done(self, reply):
        """Reply to a manual pulse: block the pad for the time of the pulses (sent one after another) + settle."""
        self.pulse_until = time.time() + self._pulses_s(reply) + PULSE_SETTLE_S if reply is not None else 0.0
        self._enable()
        QTimer.singleShot(int(max(0.0, self.pulse_until - time.time()) * 1000) + 50, self._enable)

    def _patch(self, key, value):
        self.command("set_state", patch={key: value})

    # --- impulsy reczne (okno Pulse z okna Mount, tryb guider) ---

    def set_pulse_step(self, i):
        """keys 1-7 on the frame: step from the list"""
        self.set_pulse_px(PULSE_STEPS[max(0, min(len(PULSE_STEPS) - 1, int(i)))])

    def set_pulse_px(self, px):
        """step in image pixels (the Pulse window: list or typed), PULSE_MIN_PX..PULSE_MAX_PX"""
        self.pulse_step = max(PULSE_MIN_PX, min(PULSE_MAX_PX, float(px)))
        self._sync_pulse_window()

    def pulse_ready(self):
        """(can a guider pulse go now, why not) - for the Pulse window"""
        s = self.state or {}
        if self.info is None or self.state is None:
            return False, "no guider"
        if s.get("mode") != "monitoring":
            return False, "guider not in MONITOR"
        if self.moving or time.time() < self.pulse_until:
            return False, "pulse running…"
        return True, "ready"

    def open_pulses(self):
        mnt = getattr(self.parent, "mntGui", None)
        if mnt is not None:
            mnt.pulse("guider")

    def _sync_pulse_window(self):
        window = getattr(getattr(self.parent, "mntGui", None), "pulse_window", None)
        if window is not None and window.isVisible():
            window.update_guider()

    # --- wyswietlanie ---

    def _enable(self):
        s = self.state or {}
        have = self.info is not None and self.state is not None
        mode = s.get("mode")
        single = have and s.get("method") != "fiber"
        for w in (self.off_b, self.mon_b, self.guide_b, self.method_s, self.exp_s, self.gain_s, self.search_s,
                  self.fiber_config_b):
            w.setEnabled(have)
        self._sync_pulse_window()   # strzalki okna Pulse w trybie guider: tylko MONITOR, jeden impuls naraz
        self.find_b.setEnabled(bool(single and mode == "monitoring"))
        mark = self.scene.mark
        star = s.get("acquired")
        if mode == "guiding":
            move = single and star and not mark
        else:
            move = have and mode == "monitoring" and (mark or star) and not self.moving
        self.move_b.setEnabled(bool(move))
        self.calibrate_b.setEnabled(bool(have and mark))
        self.clear_mark_b.setEnabled(bool(mark))
        hole = s.get("hole_candidate") or {}
        self.fiber_measured_b.setEnabled(bool(have and hole.get("refinable")))

    def _show_pull(self, s):
        """Guiding drags the star far to its hold point (wrong hold point after a pulse / find star): red banner
        over the frame and MONITOR highlighted - it stops the pulses."""
        star = _xy(s.get("acquired_pos")) if s.get("acquired") else None
        hold = _xy(s.get("guide_anchor"))
        pull = math.dist(star, hold) if s.get("mode") == "guiding" and star and hold else 0.0
        was = self.pull_l.isVisible()
        if pull > PULL_WARN_PX:
            fiber = _xy(s.get("central_point"))
            where = f" ({math.dist(hold, fiber):.0f} px from the {self.fiber_word()})" if fiber else ""
            self.pull_l.setText(f"Guider is pulling the star {pull:.0f} px to its hold point{where} "
                                f"- MONITOR stops it")
            theme.paint(self.pull_l, bg="bad_bg", extra="font-weight: bold; padding: 2px;")
            self.pull_l.show()
            theme.paint(self.mon_b, bg="warn_bg", extra="font-weight: bold;")
        else:
            self.pull_l.hide()
        if was != self.pull_l.isVisible():
            QTimer.singleShot(0, self._fit_frame_height)

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

        word = self.fiber_word()
        Word = word.capitalize()
        what = "mark" if self.scene.mark else "star"
        self.move_b.setText(f"Move {what} to {word}")
        self.move_b.setToolTip(
            f"GUIDE: the guided star to the {word}, closed loop (exact).\n"
            f"MONITOR: the mark, else the selected star, to the {word} with manual pulses (open loop, ±few px);\n"
            f"then GUIDE + Move to {word} for the exact position.")
        self.calibrate_b.setText(f"Calibrate {word} = mark")
        self.calibrate_b.setToolTip(f"the marked point becomes the {word} position (asks first)")
        hole = s.get("hole_candidate") or {}
        if hole.get("refinable") and hole.get("offset_px") is not None:
            self.fiber_measured_b.setText(f"{Word}: measured {float(hole['offset_px']):.1f} px")
        else:
            self.fiber_measured_b.setText(f"{Word}: measured")
        self.fiber_measured_b.setToolTip(
            f"move the {word} position onto the hole the guider measured in the image (dashed ring)\n"
            + (hole.get("reason") or "no measurement - put a bright star or the flat lamp on the fibre"))
        self.fiber_config_b.setText(f"{Word}: config")
        self.fiber_config_b.setToolTip(f"back to the configured {word} position "
                                       f"{_pt(_xy(s.get('central_point_default')))}")
        self.exp_s.show(s.get("exp_time"))
        self.gain_s.show(s.get("gain"))
        self.search_s.show(s.get("wide_search_radius_px"))

    def _show_diagnostics(self, s):
        acq = bool(s.get("acquired"))
        adu = s.get("acquired_adu")
        sat = float((s.get("method_params") or {}).get("saturation_adu") or 62000)
        self.diag["star"].setText(f"yes, {_num(adu, '{:.0f}')} ADU" if acq else "no")
        theme.paint(self.diag["star"], fg=("bad_fg" if adu is not None and float(adu) >= sat else "ok_fg")
                    if acq else "warn_fg")
        self.diag["star"].setToolTip("ADU at saturation - shorten the exposure" if acq and adu is not None
                                     and float(adu) >= sat else "is a star held, and its peak ADU")
        self.diag["fwhm"].setText(_num(s.get("fwhm_recent")))
        exp = s.get("current_exp_time") or s.get("exp_time")
        self.diag["exp"].setText(_num(exp, "{:g} s") + (" (auto)" if s.get("current_exp_time") else ""))
        ddx, ddy = s.get("last_correction_dx_px"), s.get("last_correction_dy_px")
        self.diag["delta"].setText(f"{_num(ddx)}, {_num(ddy)} px" if ddx is not None or ddy is not None else "—")
        self.diag["hold"].setText(_pt(_xy(s.get("guide_anchor"))))
        fiber = _xy(s.get("central_point"))
        config = _xy(s.get("central_point_default"))
        moved = math.dist(fiber, config) if fiber and config else 0.0
        self.diag["fiber"].setText(_pt(fiber) + (f"  ({moved:.1f} px)" if moved > FIBER_MOVED_PX else ""))
        self.diag["fiber"].setToolTip(f"{moved:.1f} px from the configured position {_pt(config)}"
                                      if moved > FIBER_MOVED_PX else "at the configured position")
        theme.paint(self.diag["fiber"], fg="warn_fg" if moved > FIBER_MOVED_PX else None)
        hole = s.get("hole_candidate") or {}
        self.diag["hole"].setText(f"{_num(hole.get('offset_px'))} px off" if hole else "—")
        self.diag["hole"].setToolTip(f"measured hole {_num(hole.get('offset_px'))} px from the {self.fiber_word()} "
                                     f"position, snr {_num(hole.get('snr'), '{:.0f}')}" if hole else
                                     "no measurement of the hole")
        word = self.fiber_word().capitalize()
        self.diag_names["fiber"].setText(f"{word}:")
        self._show_mark()

    def _show_mark(self):
        mark = self.scene.mark
        fiber = _xy((self.state or {}).get("central_point"))
        self.diag["mark"].setText(_pt(mark) + (f"  ({math.dist(mark, fiber):.0f} px)" if mark and fiber else ""))
        self.diag["mark"].setToolTip(f"right click on the frame; {math.dist(mark, fiber):.0f} px from the "
                                     f"{self.fiber_word()}" if mark and fiber else "right click on the frame")
        if self.state:
            self._show_controls_texts()

    def _show_controls_texts(self):
        word = self.fiber_word()
        self.move_b.setText(f"Move {'mark' if self.scene.mark else 'star'} to {word}")

    # --- dryf ---

    def clear_drift(self):
        self.drift.clear()
        self.drift_ref = None
        self.draw_drift()

    def _update_drift(self, s):
        """Drift = star position minus a fixed reference: the hold point, else the position at the lock; a new
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
        ax.set_ylabel("drift [px]", fontsize=7)
        ax.text(0.01, 0.97, "x", color=DRIFT_X_COLOR, transform=ax.transAxes, va="top", fontsize=8)
        ax.text(0.04, 0.97, "y", color=DRIFT_Y_COLOR, transform=ax.transAxes, va="top", fontsize=8)
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
            self.rms_l.setText(f"Drift RMS [px]:  x {rx:.2f}   y {ry:.2f}   total {math.hypot(rx, ry):.2f}")
        else:
            self.rms_l.setText("Drift RMS [px]:  —")

    # --- motyw i uklad ---

    def apply_theme(self):
        theme.paint(self.journal_e, bg="field_bg")
        theme.paint(self.help_l, fg="dim_fg")
        for name_l in self.diag_names.values():
            theme.paint(name_l, fg="dim_fg")
        self.scene.redraw()
        self.show_service()
        if self.state:
            self._show_controls(self.state)
            self._show_diagnostics(self.state)
        self.draw_drift()

    def mkUI(self):
        # --- pasek 1: teleskop/kamera, status serwisu, tryb, metoda ---
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
        self.mon_b.setToolTip("monitoring: frames and the star position, no corrections")
        self.guide_b.setToolTip("guiding: corrections keep the selected star at its hold point (where it was)")
        for b, m in ((self.off_b, "off"), (self.mon_b, "monitoring"), (self.guide_b, "guiding")):
            b.clicked.connect(lambda checked=False, m=m: self.set_mode(m))
        self.method_s = QComboBox()
        for value, name in METHODS:
            self.method_s.addItem(name, value)
        self.method_s.activated.connect(self.method_chosen)
        self.method_s.setToolTip("single star: guides on the star you selected;\n"
                                 "fiber: centres all the light around the fiber (no star selection)")
        bar.addWidget(self.title_l)
        bar.addWidget(self.service_l)
        bar.addSpacing(12)
        for w in (self.off_b, self.mon_b, self.guide_b):
            bar.addWidget(w)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Method:"))
        bar.addWidget(self.method_s)
        bar.addStretch(1)

        # --- pasek 2: gwiazda i wlokno ---
        bar2 = QHBoxLayout()
        self.find_b = QPushButton("Find star")
        self.find_b.setToolTip("MONITOR: the guider selects a star near the fiber itself, inside the search circle (F)")
        self.find_b.clicked.connect(self.find_star)
        self.move_b = QPushButton("Move star to fiber")
        self.move_b.clicked.connect(self.move_to_fiber)
        self.clear_mark_b = QPushButton("Clear mark")
        self.clear_mark_b.setToolTip("remove the mark (Esc on the frame)")
        self.clear_mark_b.clicked.connect(lambda: self.set_mark(None))
        self.calibrate_b = QPushButton("Calibrate fiber = mark")
        self.calibrate_b.clicked.connect(self.calibrate_fiber)
        self.fiber_measured_b = QPushButton("Fiber: measured")
        self.fiber_measured_b.clicked.connect(self.fiber_measured)
        self.fiber_config_b = QPushButton("Fiber: config")
        self.fiber_config_b.clicked.connect(self.fiber_config)
        for w in (self.find_b, self.move_b, self.clear_mark_b):
            bar2.addWidget(w)
        bar2.addStretch(1)
        for w in (self.calibrate_b, self.fiber_measured_b, self.fiber_config_b):
            bar2.addWidget(w)

        # --- lewa kolumna: obraz (wysokosc wg proporcji), pod nim pomoc i sterowanie ---
        self.scene = GuiderScene()
        self.frame_v = FrameView(self.scene, self)
        self.frame_v.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pull_l = QLabel("")
        self.pull_l.setWordWrap(True)
        self.pull_l.hide()
        self.help_l = QLabel(HELP)
        self.help_l.setWordWrap(True)
        font = self.help_l.font()
        font.setPointSizeF(font.pointSizeF() * 0.9)
        self.help_l.setFont(font)

        # kamera: suwak + pole (wysylane po puszczeniu suwaka / Enter / wyjsciu z pola)
        exp_n = 100
        exp_v, exp_i = _log_slider(*EXP_RANGE, exp_n)
        exp_e = QDoubleSpinBox()
        exp_e.setRange(0.001, 30)
        exp_e.setDecimals(3)
        exp_e.setSuffix(" s")
        self.exp_s = SliderEntry("Exp", exp_n, exp_v, exp_i, exp_e, lambda v: self._patch("exp_time", float(v)),
                                 "exposure of the guider camera (slider: log scale)")
        gain_n, gain_v, gain_i = _lin_slider(*GAIN_RANGE, 10)
        gain_e = QSpinBox()
        gain_e.setRange(0, 1000)
        self.gain_s = SliderEntry("Gain", gain_n, gain_v, gain_i, gain_e, lambda v: self._patch("gain", int(v)),
                                  "gain of the guider camera")
        search_n, search_v, search_i = _lin_slider(*SEARCH_RANGE, 10)
        search_e = QSpinBox()
        search_e.setRange(10, 3000)
        search_e.setSuffix(" px")
        self.search_s = SliderEntry("Search", search_n, search_v, search_i, search_e,
                                    lambda v: self._patch("wide_search_radius_px", int(v)),
                                    "search circle around the fiber (dashed): stars can be selected and found only\n"
                                    "inside it; smaller in a crowded field, larger to reach a star")
        names_w = max(w.name_l.sizeHint().width() for w in (self.exp_s, self.gain_s, self.search_s))
        entry_w = max(w.entry.sizeHint().width() for w in (self.exp_s, self.gain_s, self.search_s))
        cam = QVBoxLayout()
        cam.setSpacing(2)
        for w in (self.exp_s, self.gain_s, self.search_s):
            w.name_l.setFixedWidth(names_w)
            w.entry.setFixedWidth(entry_w)
            cam.addWidget(w)
        self.pulse_b = QPushButton("Pulse…")
        self.pulse_b.setToolTip("manual pulses: opens the Pulse window in guider mode (image pixels);\n"
                                "arrow keys on the frame do the same")
        self.pulse_b.clicked.connect(self.open_pulses)
        self.candidates_b = QPushButton("Candidates")
        self.candidates_b.setCheckable(True)
        self.candidates_b.setToolTip("small squares on every star the detector found in this frame - which stars "
                                     "it sees\n(to choose a guide star or check the detection) (D)")
        self.candidates_b.toggled.connect(self._candidates)
        buttons = QHBoxLayout()
        buttons.addWidget(self.pulse_b)
        buttons.addWidget(self.candidates_b)
        buttons.addStretch(1)
        cam.addLayout(buttons)

        # diagnostyka obok parametrow
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(1)
        self.diag = {}
        self.diag_names = {}
        cells = [("star", "Star held:"), ("fwhm", "FWHM:"), ("exp", "Exposure:"), ("delta", "Last Δ:"),
                 ("hold", "Hold point:"), ("hole", "Measured:"), ("fiber", "Fiber:"), ("mark", "Mark:"),
                 ("focus", "Focus:")]
        wide = ("fiber", "mark", "focus")     # dluzsze teksty: caly wiersz
        r = c = 0
        for key, name in cells:
            self.diag_names[key] = QLabel(name)
            self.diag[key] = QLabel("—")
            if key in wide:
                if c:
                    r, c = r + 1, 0
                grid.addWidget(self.diag_names[key], r, 0)
                grid.addWidget(self.diag[key], r, 1, 1, 3)
                r += 1
                continue
            grid.addWidget(self.diag_names[key], r, 2 * c)
            grid.addWidget(self.diag[key], r, 2 * c + 1)
            r, c = (r + 1, 0) if c else (r, 1)
        self.diag_names["hold"].setToolTip("where guiding keeps the star")
        self.diag_names["hole"].setToolTip("the fiber hole as the guider measures it in the image")
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        controls.addLayout(cam, 1)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        controls.addWidget(line)
        controls.addLayout(grid, 1)
        self.controls_w = QWidget()
        self.controls_w.setLayout(controls)
        self.controls_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.left_lay = QVBoxLayout()
        self.left_lay.setContentsMargins(0, 0, 0, 0)
        self.left_lay.setSpacing(3)
        self.left_lay.addWidget(self.pull_l)
        self.left_lay.addWidget(self.frame_v)
        self.left_lay.addWidget(self.help_l)
        self.left_lay.addWidget(self.controls_w)
        self.left_lay.addStretch(1)
        self.left_w = QWidget()
        self.left_w.setLayout(self.left_lay)

        # --- prawa kolumna: zblizenie | rozrzut, dryf w czasie, diagnostyka, dziennik ---
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self.closeup_v = CloseUpView(self.scene)
        self.closeup_v.setFixedSize(self.SIDE, self.SIDE)
        self.closeup_v.setToolTip("close-up of the fiber; dashed ring = the hole as the guider measures it")
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
        self.drift_fig = Figure(dpi=100)
        self.drift_canvas = FigureCanvas(self.drift_fig)
        self.drift_canvas.setFixedSize(self.COLUMN, 110)
        self.drift_ax = self.drift_fig.add_axes([0.1, 0.2, 0.88, 0.76])
        col.addWidget(self.drift_canvas)
        rms_row = QHBoxLayout()
        self.rms_l = QLabel("Drift RMS [px]:  —")
        clear_b = QPushButton("clear")
        clear_b.setToolTip("clear the drift plots")
        clear_b.clicked.connect(self.clear_drift)
        rms_row.addWidget(self.rms_l, 1)
        rms_row.addWidget(clear_b)
        col.addLayout(rms_row)
        col.addWidget(self._hline())

        self.journal_e = QTextEdit()
        self.journal_e.setReadOnly(True)
        self.journal_e.setToolTip("guider events and journal, and the commands sent from here")
        col.addWidget(self.journal_e, 1)
        col_w = QWidget()
        col_w.setLayout(col)
        col_w.setFixedWidth(self.COLUMN)

        main = QHBoxLayout()
        main.setSpacing(6)
        main.addWidget(self.left_w, 1)
        main.addWidget(col_w)

        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.addLayout(bar)
        layout.addLayout(bar2)
        layout.addLayout(main, 1)
        self.setLayout(layout)

    @staticmethod
    def _hline():
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _candidates(self, on):
        self.scene.show_candidates = on
        self.scene.redraw()
