"""Drawings of the optical path in TOI's palette (direction C, ``obcom.optics.look`` theme ``toi``).

- :class:`RibbonView` — the path *to one detector*, a line of components from the emitter that
  feeds it now (sky, lamp, flat screen) to the detector; when it sees dark or unknown the line goes
  on, dimmed, past the blocking component back to an emitter (``obcom.optics.ribbon``);
- :class:`SchematicView` — the whole telescope on the grid of ``obcom.optics.schematic``: authored
  places from the config, automatic elsewhere.

Both draw only what the service published (:class:`optics_model.OpticsModel`). The language: a
wire is coloured by what travels on it (light by class, dotted dark, dashed red unknown, thin grey
where nothing goes); light flows towards the detector; a ring says the component's state (moving,
unknown, declared, lit); a glyph from the shared sprite says what it is.
"""
import base64
from dataclasses import dataclass, replace

from datamodels.optics import DARK, UNDEFINED, Archetype
from obcom.optics import OpticalGraph, StopRole, component_label, emerging, published_values, schematic
from obcom.optics.look import glyph_of, glyph_svg, glyph_title, theme
from PyQtX.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPointF, QRectF, QSize, Qt, QTimer
from PyQtX.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
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
                        state=f"unknown · {cause}", state_color=THEME.unknown)
    declared = [a for a in axes.values() if a.get('origin') == 'declared']
    if declared:
        return NodeLook(THEME.declared, ring["accent_width"], False, THEME.glyph, "D", THEME.declared,
                        state=f"{position} · declared by {declared[0].get('by')}", state_color=THEME.warning)
    if node.archetype == Archetype.DETECTOR:
        seen = light or DARK
        return NodeLook(THEME.light_color(seen), ring["accent_width"], seen == UNDEFINED, THEME.glyph,
                        state=f"sees {light_word(seen)}", state_color=THEME.sees if seen not in (DARK, UNDEFINED) else THEME.light_color(seen))
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


def paint_info(painter: QPainter, center: QPointF, radius: float = 6.0):
    """The small "i": there is a hint here — on labels and drawings, never on component glyphs."""
    painter.save()
    painter.setPen(QPen(QColor(THEME.muted), 1.1))
    painter.setBrush(QColor(THEME.ground))
    painter.drawEllipse(center, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(THEME.muted))
    painter.drawEllipse(QPointF(center.x(), center.y() - radius * 0.45), radius * 0.13, radius * 0.13)
    painter.drawRoundedRect(QRectF(center.x() - radius * 0.11, center.y() - radius * 0.15, radius * 0.22, radius * 0.62), 0.6, 0.6)
    painter.restore()


def info_html(size: int = 12) -> str:
    """The small "i" for rich-text labels (``Sees: ⓘ``), drawn by :func:`paint_info`."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    paint_info(painter, QPointF(size / 2, size / 2), size / 2 - 1)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return f'<img src="data:image/png;base64,{base64.b64encode(bytes(data)).decode()}" width="{size}" height="{size}">'


def paint_text(painter: QPainter, rect: QRectF, text: str, color: str, pixels: int, bold: bool = False,
               backdrop: bool = False):
    """One centred line, cut to ``rect``; ``backdrop`` lifts it off the wires running under it."""
    font = QFont(painter.font())
    font.setPixelSize(pixels)
    font.setBold(bold)
    painter.setFont(font)
    metrics = QFontMetrics(font)
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
    if backdrop and elided:
        w = metrics.horizontalAdvance(elided) + 4
        painter.fillRect(QRectF(rect.center().x() - w / 2, rect.top(), w, metrics.height()), QColor(THEME.ground))
    painter.setPen(QColor(color))
    painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided)


class _Flowing(QWidget):
    """A view whose light flows: one timer moves the sparks while something is lit and visible; a
    tooltip tells everything about the component under the pointer."""

    FRAME_MS = 40
    RADIUS = 18
    LEGEND_BUBBLE = True  #: the big legend over the drawing's empty space

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

    INFO = 6.0  #: radius of the corner "i"

    def _info_center(self) -> QPointF:
        return QPointF(self.width() - self.INFO - 3, self.INFO + 3)

    def _paint_info_corner(self, painter: QPainter):
        paint_info(painter, self._info_center(), self.INFO)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            at = QPointF(event.pos())
            if _length(at - self._info_center()) <= self.INFO + 4:
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
    blocker, never what is lit."""

    RADIUS = 16
    LABEL_PX = 10
    LEGEND_BUBBLE = False  #: a small strip: the legend is the sky window's

    def __init__(self, model: OpticsModel, detector: str):
        super().__init__(model)
        self.detector = detector
        self.target: dict[str, str] = {}
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"optical path to {detector}")

    def sizeHint(self):
        return QSize(520, 68)

    def set_target(self, target: dict[str, str]):
        self.target = dict(target or {})
        self.update()

    def paintEvent(self, event):
        graph = self.model.graph
        if graph is None or not self.model.selectors or self.detector not in graph.nodes:
            self._flow(False)
            return
        stops = self.model.ribbon(self.detector, self.target).stops
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, step = self.RADIUS, (self.width() - 2 * self.INFO - 4) / len(stops)  # the corner "i" keeps its place
        y = r + 3
        centers = [QPointF((i + 0.5) * step, y) for i in range(len(stops))]
        self._drawn = [(c, s.name) for c, s in zip(centers, stops)]
        lit = False
        for stop, (start, end) in zip(stops, zip(centers, centers[1:])):
            light = dominant(stop.light)
            lit |= light not in (DARK, UNDEFINED) and stop.arrives
            paint_wire(painter, rounded_path([start, end], 0), light, self.phase, 1.0 if stop.arrives else 0.5)
        for stop, center in zip(stops, centers):
            look = node_look(self.model, stop.name, dominant(stop.light), stop.arrives)
            if stop.role == StopRole.BLOCKER and look.badge is None:
                look = replace(look, ring=THEME.blocker, ring_width=THEME.ring["accent_width"])
            paint_node(painter, center, r, glyph_of(graph, stop.name), look, 1.0 if stop.arrives else 0.6)
            color = {"?": THEME.unknown, "D": THEME.warning}.get(look.badge, THEME.text if stop.role == StopRole.BLOCKER else THEME.muted)
            box = QRectF(center.x() - step / 2, y + r + 4, step, 14)
            paint_text(painter, box, component_label(graph, stop.name), color, self.LABEL_PX,
                       bold=stop.role in (StopRole.DETECTOR, StopRole.BLOCKER))
            entry = self.model.selectors.get(stop.name)
            if entry is not None and graph.node(stop.name).archetype == Archetype.SELECTOR:
                paint_text(painter, box.translated(0, 12), entry.get('position') or "?", color, self.LABEL_PX)
        self._paint_info_corner(painter)
        painter.end()
        self._flow(lit)


def describe_node(model: OpticsModel, name: str) -> str:
    """Everything about one component in words: its name, every axis with position, origin, cause."""
    lines = [component_label(model.graph, name)]
    for key, entry in model.axes_of(name).items():
        position = entry.get('position')
        text = f"{entry.get('label') or key}: {position if position is not None else 'unknown'}"
        if entry.get('origin') == 'declared':
            text += f" (declared by {entry.get('by')})"
        if entry.get('cause'):
            text += f" — {entry['cause']}"
        lines.append(text)
    if name in model.sees:
        lines.append("sees " + ", ".join(sorted(light_word(r.light_class) for r in model.sees[name])))
    return "\n".join(lines)


# --- the schematic -----------------------------------------------------------------------------


class SchematicView(_Flowing):
    """The whole optical path of the telescope: light down the view (``vertical``, the narrow sky
    window) or across it. It fits the space it gets — no scrolling: rings, type and the state line
    follow the cell size; what does not fit (long names, causes, the key) is in the tooltips."""

    MIN_WIDE, MIN_HIGH = 64, 44  #: the smallest cell that still carries a glyph and its name
    MARGIN = 8
    LEGEND = 22  #: the key under the drawing, when there is room for it

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
        """Cells across and down the view."""
        layout = schematic(self.model.graph)
        return (layout.rows, layout.columns) if self.vertical else (layout.columns, layout.rows)

    def minimumSizeHint(self):
        if self.model.graph is None:
            return QSize(0, 0)
        across, down = self._cells()
        return QSize(int(across * self.MIN_WIDE) + 2 * self.MARGIN, int(down * self.MIN_HIGH) + 2 * self.MARGIN)

    def sizeHint(self):
        across, down = self._cells() if self.model.graph is not None else (0, 0)
        return QSize(int(across * 110) + 2 * self.MARGIN, int(down * 72) + 2 * self.MARGIN + self.LEGEND)

    def paintEvent(self, event):
        graph = self.model.graph
        if graph is None:
            self._flow(False)
            return
        layout = schematic(graph)
        values_of = published_values(self.model.positions)
        across, down = self._cells()
        width = self.width() - 2 * self.MARGIN
        legend = self.height() - 2 * self.MARGIN - self.LEGEND >= down * 64
        height = self.height() - 2 * self.MARGIN - (self.LEGEND if legend else 0)
        cell_x, cell_y = width / max(across, 1), height / max(down, 1)
        radius = max(9.0, min(18.0, cell_x * 0.2, cell_y * 0.28))
        name_px = 11 if cell_y >= 64 else 10 if cell_y >= 48 else 9
        state_line = cell_y >= 2 * radius + 2 * name_px + 12
        block = 2 * radius + 3 + (name_px + 2) * (2 if state_line else 1)  # glyph and its text, centred in the cell
        self._radius = radius

        def center(column: float, row: float) -> QPointF:
            x, y = (row, column) if self.vertical else (column, row)
            return QPointF(self.MARGIN + (x + 0.5) * cell_x, self.MARGIN + y * cell_y + (cell_y - block) / 2 + radius)

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
            paint_wire(painter, rounded_path([center(*p) for p in wire.points], min(10.0, radius * 0.6)), light, self.phase)
        self._drawn = []
        for name, place in layout.places.items():
            c = center(place.column, place.row)
            self._drawn.append((c, name))
            node = graph.node(name)
            if node.archetype == Archetype.DETECTOR:
                seen = self.model.sees.get(name)
                light = dominant({r.light_class for r in seen}) if seen else None
            else:
                light = lit_from.get(name)
            look = node_look(self.model, name, light, True)
            paint_node(painter, c, radius, glyph_of(graph, name), look)
            box = QRectF(c.x() - cell_x / 2 + 1, c.y() + radius + 3, cell_x - 2, name_px + 3)
            paint_text(painter, box, component_label(graph, name), THEME.text, name_px,
                       bold=node.archetype == Archetype.DETECTOR, backdrop=True)
            if state_line and look.state:
                paint_text(painter, box.translated(0, name_px + 2), look.state, look.state_color, name_px - 1, backdrop=True)
        if legend:
            self._paint_legend(painter, graph, values_of, self.height() - self.LEGEND)
        self._paint_info_corner(painter)
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
        LegendRow("dark", "proven darkness: a closed cover, M3 turned away", light=DARK),
        LegendRow("unknown", "nothing proves what travels here", light=UNDEFINED),
        LegendRow("a way nothing takes now", light=None),
        LegendRow("sparks flow towards the detector;", "dimmed: beyond what blocks it", sample=False),
    ]
    rings = [
        LegendRow("on a lit path", look=NodeLook(sky, width, False, THEME.glyph)),
        LegendRow("nothing passes now", look=NodeLook(THEME.idle, width, False, THEME.glyph_idle)),
        LegendRow("blocks what the detector sees", look=NodeLook(THEME.blocker, accent, False, THEME.glyph)),
        LegendRow("moving", "a switch is running", look=NodeLook(THEME.moving, accent, False, THEME.glyph)),
        LegendRow("position unknown", "why: point at it", look=NodeLook(THEME.unknown, accent, True, THEME.unknown, "?", THEME.unknown)),
        LegendRow("declared by an operator", "until a reading returns", look=NodeLook(THEME.declared, accent, False, THEME.glyph, "D", THEME.declared)),
        LegendRow("a detector", "the ring is what it sees", look=NodeLook(sky, accent, False, THEME.glyph), glyph="camera"),
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
                         "Point at a component for its positions, causes and declarations — all as the optics service publishes them.")
        painter.end()
