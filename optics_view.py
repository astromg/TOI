"""Drawings of the optical path in TOI's palette (direction C, ``obcom.optics.look`` theme ``toi``).

- :class:`RibbonView` — the path *to one detector*, a line of components from the emitter that
  feeds it now (sky, lamp, flat screen) to the detector; when it sees dark or unknown the line goes
  on, dimmed, past the blocking component back to an emitter (``obcom.optics.ribbon``);
- :class:`SchematicView` — the whole telescope on the grid of ``obcom.optics.schematic``: authored
  places from the config, automatic elsewhere;
- :class:`StatusLine` — one status in TOI's read-only field: a chip saying what it is (READY,
  BLOCKED, MOVING …, theme tokens ``status``), the words beside it always in the text colour —
  colour says the state, never the prose.

Both draw only what the service published (:class:`optics_model.OpticsModel`). The language: a
wire is coloured by what travels on it (light by class, dotted dark, dashed red unknown, thin grey
where nothing goes); light flows towards the detector; a ring says the component's state (moving,
unknown, declared, lit); a glyph from the shared sprite says what it is.
"""
import base64
from dataclasses import dataclass, replace

from datamodels.optics import DARK, UNDEFINED, Archetype
from obcom.optics import OpticalGraph, StopRole, component_label, emerging, place_labels, published_values, schematic
from obcom.optics.look import glyph_of, glyph_svg, glyph_title, theme
from PyQtX.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPointF, QRectF, QSize, QSizeF, Qt, QTimer
from PyQtX.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQtX.QtSvg import QSvgRenderer
from PyQtX.QtWidgets import QSizePolicy, QToolTip, QWidget

from optics_model import OpticsModel

THEME = theme("toi")
_RENDERERS: dict[tuple[str, str, float], QSvgRenderer] = {}


def dominant(classes) -> str:
    """The one thing a line shows: light before unknown before dark."""
    light = sorted(c for c in classes if c not in (DARK, UNDEFINED))
    if light:
        return light[0]
    return UNDEFINED if UNDEFINED in classes else DARK


def light_word(light_class: str) -> str:
    return "unknown" if light_class == UNDEFINED else light_class


# --- the look of one component -----------------------------------------------------------------


@dataclass(frozen=True)
class NodeLook:
    ring: str
    ring_width: float
    dashed: bool
    glyph: str
    badge: str | None = None  #: one letter in a dot on the ring: ``?`` unknown, ``D`` declared
    badge_color: str | None = None
    state: str = ""  #: the second line: position, cause, what a detector sees
    state_color: str = THEME.muted


def node_look(model: OpticsModel, name: str, light: str | None, arrives: bool) -> NodeLook:
    """How component ``name`` looks: from its published axes, and ``light`` — what it puts on the way
    (a detector: what it sees; ``None``: nothing that goes anywhere) — ``arrives``: on a live path."""
    graph = model.graph
    node = graph.node(name)
    axes = model.axes_of(name)
    ring = THEME.ring
    primary = axes.get(name, {})
    position = primary.get('position')
    if any(a.get('moving') for a in axes.values()):
        return NodeLook(THEME.moving, ring["accent_width"], False, THEME.glyph, state="moving", state_color=THEME.text)
    unknown = [a for a in axes.values() if a.get('position') is None]
    if unknown:
        cause = unknown[0].get('cause') or "no reading"
        return NodeLook(THEME.unknown, ring["accent_width"], True, THEME.unknown, "?", THEME.unknown,
                        state=f"not known · {cause}", state_color=THEME.unknown)
    declared = [a for a in axes.values() if a.get('origin') == 'declared']
    if declared:
        return NodeLook(THEME.declared, ring["accent_width"], False, THEME.glyph, "D", THEME.declared,
                        state=f"{position} · by hand: {declared[0].get('by')}", state_color=THEME.warning)
    if node.archetype == Archetype.DETECTOR:
        seen = light or DARK
        return NodeLook(THEME.light_color(seen), ring["accent_width"], seen == UNDEFINED, THEME.glyph,
                        state=f"sees {light_word(seen)}", state_color=THEME.muted if seen == DARK else THEME.light_color(seen))
    state = position if node.archetype == Archetype.SELECTOR and position else ""
    if arrives and light is not None and light not in (DARK, UNDEFINED):
        return NodeLook(THEME.light_color(light), ring["width"], False, THEME.glyph, state=state)
    return NodeLook(THEME.idle, ring["width"], False, THEME.glyph if arrives else THEME.glyph_idle, state=state)


# --- painting ----------------------------------------------------------------------------------


def _renderer(glyph: str, color: str, stroke: float) -> QSvgRenderer:
    key = (glyph, color, stroke)
    if key not in _RENDERERS:
        _RENDERERS[key] = QSvgRenderer(glyph_svg(glyph, color, stroke))
    return _RENDERERS[key]


def rounded_path(points: list[QPointF], radius: float) -> QPainterPath:
    """An orthogonal polyline with rounded corners."""
    path = QPainterPath(points[0])
    for before, corner, after in zip(points, points[1:], points[2:]):
        r = min(radius, _length(corner - before) / 2, _length(after - corner) / 2)
        path.lineTo(corner - _unit(corner - before) * r)
        path.quadTo(corner, corner + _unit(after - corner) * r)
    path.lineTo(points[-1])
    return path


def _length(v: QPointF) -> float:
    return (v.x() ** 2 + v.y() ** 2) ** 0.5


def _unit(v: QPointF) -> QPointF:
    n = _length(v)
    return v / n if n else v


def paint_wire(painter: QPainter, path: QPainterPath, light: str | None, phase: float, opacity: float = 1.0):
    """A wire carrying ``light`` (``None``: a possible way nothing takes); ``phase`` in px moves the
    sparks of light towards the path's end (the detector)."""
    stroke = THEME.stroke(light)
    painter.save()
    painter.setOpacity(opacity)
    color = QColor(THEME.idle if light is None else THEME.light_color(light))
    width = stroke["width"]
    if light is not None and light not in (DARK, UNDEFINED):
        halo = QColor(color)
        halo.setAlphaF(stroke["halo_opacity"])
        painter.setPen(_pen(halo, stroke["halo"]))
        painter.drawPath(path)
        painter.setPen(_pen(color, width))
        painter.drawPath(path)
        sparks = _pen(QColor(stroke["spark"]), width)
        sparks.setDashPattern([d / width for d in stroke["sparks"]])
        sparks.setDashOffset(-phase / width)
        painter.setPen(sparks)
        painter.drawPath(path)
    else:
        pen = _pen(color, width)
        if "dash" in stroke:
            pen.setDashPattern([d / width for d in stroke["dash"]])
        painter.setPen(pen)
        painter.drawPath(path)
    painter.restore()


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def paint_node(painter: QPainter, center: QPointF, radius: float, glyph: str, look: NodeLook, opacity: float = 1.0):
    painter.save()
    painter.setOpacity(opacity)
    pen = QPen(QColor(look.ring), look.ring_width)
    if look.dashed:
        pen.setDashPattern([d / look.ring_width for d in THEME.ring["dash"]])
    painter.setPen(pen)
    painter.setBrush(QColor(THEME.ground))
    painter.drawEllipse(center, radius, radius)
    size = radius * 2.2
    _renderer(glyph, look.glyph, THEME.glyph_stroke).render(painter, QRectF(center.x() - size / 2, center.y() - size / 2, size, size))
    if look.badge:
        dot, b = QPointF(center.x() + radius * 0.8, center.y() - radius * 0.8), max(5.0, radius * 0.4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(look.badge_color))
        painter.drawEllipse(dot, b, b)
        painter.setPen(QColor(THEME.ground if look.badge_color != THEME.declared else THEME.text))
        font = QFont(painter.font())
        font.setPixelSize(int(b * 1.3))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(dot.x() - b, dot.y() - b, 2 * b, 2 * b), Qt.AlignmentFlag.AlignCenter, look.badge)
    painter.restore()


def paint_hint(painter: QPainter, center: QPointF, radius: float = 6.0):
    """The small "?": point here for a hint — on labels and drawings, never on component glyphs."""
    painter.save()
    painter.setPen(QPen(QColor(THEME.muted), 1.1))
    painter.setBrush(QColor(THEME.ground))
    painter.drawEllipse(center, radius, radius)
    font = QFont(painter.font())
    font.setPixelSize(max(7, int(radius * 1.45)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(THEME.muted))
    painter.drawText(QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius), Qt.AlignmentFlag.AlignCenter, "?")
    painter.restore()


def hint_html(size: int = 12) -> str:
    """The small "?" for rich-text labels (``Sees: (?)``), drawn by :func:`paint_hint`."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    paint_hint(painter, QPointF(size / 2, size / 2), size / 2 - 1)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return f'<img src="data:image/png;base64,{base64.b64encode(bytes(data)).decode()}" width="{size}" height="{size}">'


def paint_text(painter: QPainter, rect: QRectF, text: str, color: str, pixels: int, bold: bool = False,
               backdrop: bool = False, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignHCenter):
    """One line in ``rect`` (centred, or ``align``-ed left or right), cut to its width; ``backdrop``
    lifts it off the wires running under it."""
    font = QFont(painter.font())
    font.setPixelSize(pixels)
    font.setBold(bold)
    painter.setFont(font)
    metrics = QFontMetrics(font)
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
    if backdrop and elided:
        w = metrics.horizontalAdvance(elided) + 4
        x = {Qt.AlignmentFlag.AlignLeft: rect.left() - 2, Qt.AlignmentFlag.AlignRight: rect.right() - w + 2}.get(align, rect.center().x() - w / 2)
        painter.fillRect(QRectF(x, rect.top(), w, metrics.height()), QColor(THEME.ground))
    painter.setPen(QColor(color))
    painter.drawText(rect, align | Qt.AlignmentFlag.AlignTop, elided)


class _Flowing(QWidget):
    """A view whose light flows: one timer moves the sparks while something is lit and visible; a
    tooltip tells everything about the component under the pointer."""

    FRAME_MS = 40
    RADIUS = 18
    LEGEND_BUBBLE = True  #: the big legend over the drawing's empty space
    CORNER_HINT = True  #: the "?" in the top right corner

    def __init__(self, model: OpticsModel):
        super().__init__()
        self.model = model
        self._drawn: list[tuple[QPointF, str]] = []  #: centre and component of every glyph drawn
        self._radius = float(self.RADIUS)  #: of the glyphs as last drawn
        self._legend: LegendBubble | None = None
        self._bubble_at = QPointF()
        self.setMouseTracking(True)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(self.FRAME_MS)
        self.timer.timeout.connect(self._advance)


    def _advance(self):
        stroke = THEME.line["light"]
        self.phase = (self.phase + sum(stroke["sparks"]) * self.FRAME_MS / 1000 / stroke["period_s"]) % sum(stroke["sparks"])
        self.update()

    def _flow(self, lit: bool):
        if lit and not self.timer.isActive():
            self.timer.start()
        elif not lit and self.timer.isActive():
            self.timer.stop()

    HINT = 6.0  #: radius of the corner "?"

    def _hint_center(self) -> QPointF:
        return QPointF(self.width() - self.HINT - 3, self.HINT + 3)

    def _paint_hint_corner(self, painter: QPainter):
        if self.CORNER_HINT:
            paint_hint(painter, self._hint_center(), self.HINT)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            at = QPointF(event.pos())
            if self.CORNER_HINT and _length(at - self._hint_center()) <= self.HINT + 4:
                if self.model.graph is not None and self.LEGEND_BUBBLE:
                    QToolTip.hideText()
                    self._bubble().show_for(self.model, event.globalPos())
                    self._bubble_at = at
                    return True
                return super().event(event)  # the widget's own hint
            drawn = min(self._drawn, key=lambda d: _length(d[0] - at), default=None)
            if drawn is not None and _length(drawn[0] - at) <= self._radius * 2:
                self._bubble().hide()
                QToolTip.showText(event.globalPos(), describe_node(self.model, drawn[1]), self)
            elif self.model.graph is not None and self.LEGEND_BUBBLE:
                QToolTip.hideText()
                self._bubble().show_for(self.model, event.globalPos())
                self._bubble_at = at
            else:
                return super().event(event)  # the widget's own hint
            return True
        if event.type() == QEvent.Type.Leave and self._legend is not None:
            self._legend.hide()
        return super().event(event)

    def mouseMoveEvent(self, event):
        if self._legend is not None and self._legend.isVisible() and _length(event.position() - self._bubble_at) > 24:
            self._legend.hide()
        super().mouseMoveEvent(event)

    def _bubble(self) -> "LegendBubble":
        if self._legend is None:
            self._legend = LegendBubble()
        return self._legend

    def hideEvent(self, event):
        self.timer.stop()
        if self._legend is not None:
            self._legend.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.update()


# --- the ribbon --------------------------------------------------------------------------------


class RibbonView(_Flowing):
    """The path to ``detector``; ``target`` (the selected function's moves) chooses the way past a
    blocker, never what is lit. Under every glyph its name (on two lines when it must) and its
    state: a selector's position, what the detector sees."""

    RADIUS = 16
    LABEL_PX = 10
    LINE_PX = 12
    LEGEND_BUBBLE = False  #: a small strip: the legend is the sky window's
    CORNER_HINT = False  #: the panel's title carries the hint

    def __init__(self, model: OpticsModel, detector: str):
        super().__init__(model)
        self.detector = detector
        self.target: dict[str, str] = {}
        self.setFixedHeight(2 * self.RADIUS + 3 + 4 + 3 * self.LINE_PX + 3)  # glyph, name (≤ 2 lines), state
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"optical path to {detector}")

    def sizeHint(self):
        return QSize(520, self.height())

    def set_target(self, target: dict[str, str]):
        self.target = dict(target or {})
        self.update()

    def _state(self, name: str, light: str) -> str | None:
        """The line under the name: a selector's position, what the detector sees."""
        node = self.model.graph.node(name)
        if node.archetype == Archetype.DETECTOR:
            return light_word(light)
        entry = self.model.selectors.get(name)
        if entry is not None and node.archetype == Archetype.SELECTOR:
            return entry.get('position') or "?"
        return None

    def paintEvent(self, event):
        graph = self.model.graph
        if graph is None or not self.model.selectors or self.detector not in graph.nodes:
            self._flow(False)
            return
        stops = self.model.ribbon(self.detector, self.target).stops
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, step = self.RADIUS, self.width() / len(stops)
        y = r + 3
        centers = [QPointF((i + 0.5) * step, y) for i in range(len(stops))]
        self._drawn = [(c, s.name) for c, s in zip(centers, stops)]
        lit = False
        for stop, (start, end) in zip(stops, zip(centers, centers[1:])):
            light = dominant(stop.light)
            lit |= light not in (DARK, UNDEFINED) and stop.arrives
            paint_wire(painter, rounded_path([start, end], 0), light, self.phase, 1.0 if stop.arrives else 0.5)
        font = QFont(painter.font())
        font.setPixelSize(self.LABEL_PX)
        for stop, center in zip(stops, centers):
            light = dominant(stop.light)
            look = node_look(self.model, stop.name, light, stop.arrives)
            if stop.role == StopRole.BLOCKER and look.badge is None:
                look = replace(look, ring=THEME.blocker, ring_width=THEME.ring["accent_width"])
            paint_node(painter, center, r, glyph_of(graph, stop.name), look, 1.0 if stop.arrives else 0.6)
            color = {"?": THEME.unknown, "D": THEME.warning}.get(look.badge, THEME.text if stop.role == StopRole.BLOCKER else THEME.muted)
            bold = stop.role in (StopRole.DETECTOR, StopRole.BLOCKER)
            box = QRectF(center.x() - step / 2 + 1, y + r + 4, step - 2, self.LINE_PX + 2)
            font.setBold(bold)
            lines = wrapped(component_label(graph, stop.name), font, int(box.width()), 2)
            for line in lines:
                paint_text(painter, box, line, color, self.LABEL_PX, bold=bold)
                box.translate(0, self.LINE_PX)
            state = self._state(stop.name, light)
            if state is not None:
                if stop.role == StopRole.DETECTOR and look.badge is None:
                    color = look.state_color
                paint_text(painter, box, state, color, self.LABEL_PX)
        painter.end()
        self._flow(lit)


def wrapped(text: str, font: QFont, width: int, lines: int) -> list[str]:
    """``text`` broken between words into at most ``lines`` lines of ``width`` px, the last one cut
    with an ellipsis when it still does not fit."""
    metrics = QFontMetrics(font)
    out: list[str] = []
    words = text.split()
    while words and len(out) < lines - 1:
        taken = 1
        while taken < len(words) and metrics.horizontalAdvance(" ".join(words[:taken + 1])) <= width:
            taken += 1
        if taken == len(words):
            break
        out.append(" ".join(words[:taken]))
        words = words[taken:]
    if words:
        out.append(metrics.elidedText(" ".join(words), Qt.TextElideMode.ElideRight, width))
    return out


# --- the status line ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Status:
    """What :class:`StatusLine` shows: ``kind`` names a chip of the theme's ``status`` tokens
    (active, settable, collision, impossible, invalid, moving, failed, none), ``word`` is written on
    it, ``text`` beside it; ``details`` is the tooltip (``text`` when ``None``)."""

    kind: str
    word: str
    text: str = ""
    details: str | None = None


def _scaled(font: QFont, factor: float) -> QFont:
    """``font`` ``factor`` times as large, whether it was sized in points or in pixels."""
    scaled = QFont(font)
    if font.pointSizeF() > 0:
        scaled.setPointSizeF(font.pointSizeF() * factor)
    else:
        scaled.setPixelSize(max(7, round(font.pixelSize() * factor)))
    return scaled


def status_icon(kind: str, size: int = 12) -> QIcon:
    """A dot in the chip colour of ``kind`` — for a list of functions, whose words stay black."""
    pixmap = QPixmap(2 * size, 2 * size)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(THEME.status[kind]["fill"]))
    painter.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    painter.end()
    return QIcon(pixmap)


class StatusLine(QWidget):
    """One status in TOI's read-only field: the chip, then the words in the text colour, cut to the
    width — the whole of it in the tooltip. One line, always the same height."""

    PAD = 5

    def __init__(self):
        super().__init__()
        self.status = Status("none", "")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(320, self.fontMetrics().height() + 10)

    def minimumSizeHint(self):
        return QSize(80, self.sizeHint().height())

    def set_status(self, status: Status):
        self.status = status
        self.setToolTip(status.details if status.details is not None else status.text)
        self.setAccessibleDescription(f"{status.word}: {status.text}" if status.word else status.text)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        field = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(THEME.status["field"]))
        painter.drawRoundedRect(field, 3, 3)
        x = field.left() + self.PAD
        if self.status.word:
            chip_font = _scaled(self.font(), 0.8)
            chip_font.setBold(True)
            metrics = QFontMetrics(chip_font)
            h = min(field.height() - 2 * 3, metrics.height() + 4)
            chip = QRectF(x, field.center().y() - h / 2, metrics.horizontalAdvance(self.status.word) + h, h)
            colors = THEME.status[self.status.kind]
            painter.setBrush(QColor(colors["fill"]))
            painter.drawRoundedRect(chip, h / 2, h / 2)
            painter.setFont(chip_font)
            painter.setPen(QColor(colors["ink"]))
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, self.status.word)
            x = chip.right() + 8
        painter.setFont(self.font())
        painter.setPen(QColor(THEME.text))
        room = QRectF(x, field.top(), field.right() - self.PAD - x, field.height())
        painter.drawText(room, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.fontMetrics().elidedText(self.status.text, Qt.TextElideMode.ElideRight, int(room.width())))
        painter.end()


def describe_node(model: OpticsModel, name: str) -> str:
    """Everything about one component in words: its name, every axis with position, origin, cause."""
    lines = [component_label(model.graph, name)]
    for key, entry in model.axes_of(name).items():
        position = entry.get('position')
        text = f"{entry.get('label') or key}: {position if position is not None else 'unknown'}"
        if entry.get('origin') == 'declared':
            text += f" (confirmed by hand by {entry.get('by')})"
        if entry.get('cause'):
            text += f" — {entry['cause']}"
        lines.append(text)
    if name in model.sees:
        lines.append("sees " + ", ".join(sorted(light_word(r.light_class) for r in model.sees[name])))
    return "\n".join(lines)


# --- the schematic -----------------------------------------------------------------------------


class SchematicView(_Flowing):
    """The whole optical path of the telescope: light down the view (``vertical``, the narrow sky
    window) or across it, laid out by ``obcom.optics.schematic`` — the trunk in the middle, equal
    branches on both sides — every label where it hits no wire nor another label
    (``obcom.optics.place_labels``). It fits the space it gets, no scrolling: rings and type follow
    the cell size; what does not fit (long causes, the key) is in the tooltips."""

    MIN_LANE, MIN_LAYER = 40, 44  #: the smallest spacing that still carries a glyph and its name
    MARGIN = 8
    LEGEND = 22  #: the key under the drawing, when there is room for it
    _LEFT, _RIGHT = Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight

    def __init__(self, model: OpticsModel, vertical: bool = True):
        super().__init__(model)
        self.vertical = vertical
        self.setAccessibleName("optical path of the telescope")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for signal in (model.graph_changed, model.selectors_changed, model.operation_changed):
            signal.connect(self._changed)
        model.sees_changed.connect(self._seen)

    def _seen(self, detector: str):
        self.update()

    def _changed(self):
        self.updateGeometry()
        self.update()

    def _cells(self) -> tuple[float, float]:
        """Lanes across and layers down the view (the other way round across the light)."""
        layout = schematic(self.model.graph)
        return (layout.rows, layout.columns) if self.vertical else (layout.columns, layout.rows)

    def minimumSizeHint(self):
        if self.model.graph is None:
            return QSize(0, 0)
        across, down = self._cells()
        return QSize(int(across * self.MIN_LANE) + 2 * self.MARGIN, int(down * self.MIN_LAYER) + 2 * self.MARGIN)

    def sizeHint(self):
        across, down = self._cells() if self.model.graph is not None else (0, 0)
        return QSize(int(across * 64) + 2 * self.MARGIN, int(down * 72) + 2 * self.MARGIN + self.LEGEND)

    def paintEvent(self, event):
        graph = self.model.graph
        if graph is None:
            self._flow(False)
            return
        layout = schematic(graph)
        values_of = published_values(self.model.positions)
        across, down = self._cells()
        legend = self.height() - 2 * self.MARGIN - self.LEGEND >= down * 60
        width = self.width() - 2 * self.MARGIN
        height = self.height() - 2 * self.MARGIN - (self.LEGEND if legend else 0)
        cell_x, cell_y = width / max(across, 1), height / max(down, 1)
        cell_x, cell_y = min(cell_x, 1.3 * cell_y), min(cell_y, 1.3 * cell_x)  # never stretched: centred in the room left
        left = self.MARGIN + (width - across * cell_x) / 2
        top = self.MARGIN + (height - down * cell_y) / 2
        radius = max(9.0, min(18.0, cell_x * 0.3, cell_y * 0.26))
        name_px = 11 if cell_y >= 60 else 10 if cell_y >= 48 else 9
        self._radius = radius

        def center(point) -> QPointF:
            column, row = point
            x, y = (row, column) if self.vertical else (column, row)
            return QPointF(left + (x + 0.5) * cell_x, top + (y + 0.5) * cell_y)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(THEME.ground))
        lit_from: dict[str, str] = {}
        flowing = False
        for wire, classes in layout.light(graph, values_of).items():
            light = dominant(classes) if wire.taken(graph, values_of) else None
            if light is not None and light not in (DARK, UNDEFINED):
                lit_from[wire.upstream] = light
                flowing = True
            paint_wire(painter, rounded_path([center(p) for p in wire.points], min(10.0, radius * 0.6)), light, self.phase)

        looks, texts = {}, {}
        name_font, state_font = QFont(painter.font()), QFont(painter.font())
        name_font.setPixelSize(name_px)
        state_font.setPixelSize(name_px - 1)
        self._drawn = []
        for name, place in layout.places.items():
            c = center((place.column, place.row))
            self._drawn.append((c, name))
            node = graph.node(name)
            if node.archetype == Archetype.DETECTOR:
                seen = self.model.sees.get(name)
                light = dominant({r.light_class for r in seen}) if seen else None
            else:
                light = lit_from.get(name)
            looks[name] = node_look(self.model, name, light, True)
            paint_node(painter, c, radius, glyph_of(graph, name), looks[name])
            name_font.setBold(node.archetype == Archetype.DETECTOR)
            label, state = component_label(graph, name), looks[name].state
            w = max(QFontMetrics(name_font).horizontalAdvance(label), QFontMetrics(state_font).horizontalAdvance(state) if state else 0)
            w = min(w + 2, max(64.0, 2.2 * cell_x))  # at most about two lanes: the rest is in the tooltip
            texts[name] = (label, state, QSizeF(w, name_px + 3 + (name_px + 2 if state else 0)))

        bounds = (0.0, 0.0, float(self.width()), float(self.height() - (self.LEGEND if legend else 0)))
        labels = place_labels(layout, {n: (t[2].width(), t[2].height()) for n, t in texts.items()},
                              lambda p: (center(p).x(), center(p).y()), radius, bounds, gap=3.0,
                              narrow=max(48.0, 1.15 * cell_x))  # under or over a component: about one lane
        for name, box in labels.items():
            label, state, _ = texts[name]
            align = {"right": self._LEFT, "left": self._RIGHT}.get(box.side, Qt.AlignmentFlag.AlignHCenter)
            rect = QRectF(box.x, box.y, box.width, name_px + 3)
            paint_text(painter, rect, label, THEME.text, name_px, bold=graph.node(name).archetype == Archetype.DETECTOR,
                       backdrop=True, align=align)
            if state:
                paint_text(painter, rect.translated(0, name_px + 2), state, looks[name].state_color, name_px - 1,
                           backdrop=True, align=align)
        if legend:
            self._paint_legend(painter, graph, values_of, self.height() - self.LEGEND)
        self._paint_hint_corner(painter)
        painter.end()
        self._flow(flowing)

    def _paint_legend(self, painter: QPainter, graph: OpticalGraph, values_of, y: float):
        """What the colours mean here: the light of every source (what it puts out now, else what it
        can), dark, unknown; the rings. Items that do not fit the width are left to the tooltip."""
        lines = source_lights(graph, values_of)
        lines += [("dark", DARK), ("unknown", UNDEFINED)]
        font = QFont(painter.font())
        font.setPixelSize(10)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        x = float(self.MARGIN)
        items = [(text, light, None) for text, light in lines] + [("moving", None, THEME.moving), ("declared", None, THEME.declared)]
        for text, light, ring in items:
            if x + 26 + metrics.horizontalAdvance(text) > self.width() - self.MARGIN:
                break
            if ring is None:
                stroke = THEME.stroke(light)
                pen = _pen(QColor(THEME.light_color(light)), 2.4)
                if "dash" in stroke:
                    pen.setDashPattern([d / 2.4 for d in stroke["dash"]])
                painter.setPen(pen)
                painter.drawLine(QPointF(x, y + 7), QPointF(x + 18, y + 7))
                x += 22
            else:
                painter.setPen(QPen(QColor(ring), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x + 5, y + 7), 4.5, 4.5)
                x += 14
            painter.setPen(QColor(THEME.muted))
            painter.drawText(QPointF(x, y + 11), text)
            x += metrics.horizontalAdvance(text) + 12


# --- the legend ---------------------------------------------------------------------------------


def source_lights(graph: OpticalGraph, values_of) -> list[tuple[str, str]]:
    """(label, light class) of every source: what it puts out now, else the first it can."""
    lights = []
    for source in graph.sources:
        now = dominant({r.light_class for r in emerging(graph, values_of, source)})
        possible = sorted(graph.emitted_classes(source))
        if now not in (DARK, UNDEFINED) or possible:
            lights.append((component_label(graph, source), now if now not in (DARK, UNDEFINED) else possible[0]))
    return lights


@dataclass(frozen=True)
class LegendRow:
    text: str
    note: str = ""  #: a second, muted line
    light: str | None = None  #: a line sample of what travels…
    look: NodeLook | None = None  #: …or a ring sample
    glyph: str = "part"
    sample: bool = True  #: ``False``: text only


def legend_sections(model: OpticsModel) -> list[tuple[str, list[LegendRow]]]:
    """The legend of one telescope's drawing: what the lines, the rings and its symbols mean."""
    graph = model.graph
    accent, width = THEME.ring["accent_width"], THEME.ring["width"]
    sky = THEME.light_color("sky.science")
    lines = [LegendRow(f"light from the {label}", light, light=light)
             for label, light in source_lights(graph, published_values(model.positions))]
    lines += [
        LegendRow("no light", "e.g. covers closed, M3 turned away", light=DARK),
        LegendRow("not known", "no sensor tells whether light gets here", light=UNDEFINED),
        LegendRow("a way not used now", light=None),
        LegendRow("moving dots show the light going to the camera;", "pale: past the part that blocks it", sample=False),
    ]
    rings = [
        LegendRow("light passes", look=NodeLook(sky, width, False, THEME.glyph)),
        LegendRow("no light passes", look=NodeLook(THEME.idle, width, False, THEME.glyph_idle)),
        LegendRow("blocks the light to the camera", look=NodeLook(THEME.blocker, accent, False, THEME.glyph)),
        LegendRow("moving", "SET PATH is moving it", look=NodeLook(THEME.moving, accent, False, THEME.glyph)),
        LegendRow("not known where it is", "point at it to see why", look=NodeLook(THEME.unknown, accent, True, THEME.unknown, "?", THEME.unknown)),
        LegendRow("confirmed by hand", "until its sensor works again", look=NodeLook(THEME.declared, accent, False, THEME.glyph, "D", THEME.declared)),
        LegendRow("a camera", "ring colour: what it gets", look=NodeLook(sky, accent, False, THEME.glyph), glyph="camera"),
    ]
    by_glyph: dict[str, list[str]] = {}
    for name in graph.nodes:
        by_glyph.setdefault(glyph_of(graph, name), []).append(component_label(graph, name))
    symbols = []
    for glyph, labels in by_glyph.items():
        title, here = glyph_title(glyph), ", ".join(labels)
        symbols.append(LegendRow(title, "" if here.lower() == title.lower() else here,
                                 look=NodeLook(THEME.idle, width, False, THEME.glyph), glyph=glyph))
    half = (len(symbols) + 1) // 2
    return [("Lines — what travels", lines), ("Rings — state", rings), ("Symbols", symbols[:half]), ("", symbols[half:])]


class LegendBubble(QWidget):
    """The big legend, a tooltip-like window drawn with the very painters of the views. Shown over
    the drawing's empty space, gone when the pointer moves on."""

    PAD, GAP, SAMPLE, ROW, LINE = 14, 22, 46, 34, 14

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.sections: list[tuple[str, list[LegendRow]]] = []
        self.font_text = QFont(self.font())
        self.font_text.setPixelSize(11)
        self.font_title = QFont(self.font_text)
        self.font_title.setBold(True)

    def show_for(self, model: OpticsModel, at):
        self.sections = legend_sections(model)
        self.resize(self._size())
        screen = self.screen().availableGeometry() if self.screen() else None
        x, y = at.x() + 16, at.y() + 16
        if screen is not None:
            x = max(screen.left(), min(x, screen.right() - self.width()))
            y = y if y + self.height() <= screen.bottom() else at.y() - self.height() - 8
        self.move(x, y)
        self.show()
        self.update()

    def _column_width(self, rows: list[LegendRow]) -> int:
        metrics = QFontMetrics(self.font_text)
        return self.SAMPLE + 8 + max((max(metrics.horizontalAdvance(r.text), metrics.horizontalAdvance(r.note)) for r in rows), default=0)

    def _size(self) -> QSize:
        width = sum(self._column_width(rows) for _, rows in self.sections) + self.GAP * (len(self.sections) - 1)
        tallest = max(len(rows) for _, rows in self.sections)
        return QSize(width + 2 * self.PAD, 2 * self.PAD + 20 + tallest * self.ROW + 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(THEME.idle), 1))
        painter.setBrush(QColor(THEME.ground))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        x = float(self.PAD)
        for title, rows in self.sections:
            painter.setFont(self.font_title)
            painter.setPen(QColor(THEME.text))
            painter.drawText(QPointF(x, self.PAD + 11), title)
            y = self.PAD + 20.0
            for row in rows:
                middle = y + self.ROW / 2
                if row.look is not None:
                    paint_node(painter, QPointF(x + self.SAMPLE / 2, middle), 12, row.glyph, row.look)
                elif row.sample:
                    paint_wire(painter, rounded_path([QPointF(x + 4, middle), QPointF(x + self.SAMPLE - 4, middle)], 0), row.light, 0.0)
                painter.setFont(self.font_text)
                text_x = x + (self.SAMPLE + 8 if row.sample else 0)
                painter.setPen(QColor(THEME.text))
                painter.drawText(QPointF(text_x, middle + (-1 if row.note else 4)), row.text)
                if row.note:
                    painter.setPen(QColor(THEME.muted))
                    painter.drawText(QPointF(text_x, middle + self.LINE - 1), row.note)
                y += self.ROW
            x += self._column_width(rows) + self.GAP
        painter.setFont(self.font_text)
        painter.setPen(QColor(THEME.muted))
        painter.drawText(QPointF(self.PAD, self.height() - self.PAD + 2),
                         "Point at a part to see where it is set, and why something is not known.")
        painter.end()
