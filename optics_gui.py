"""Optical path panel of an instrument tab: what the detector sees, and switching its light path.

The ``optics`` service (ocabox-tcs) owns the optical path of a telescope; TOI reaches it through TIC
like any device (``ocaboxapi`` ``Telescope.get_optical_detector`` / ``get_optics``), so the access
control is the operator's reservation, as for M3. The panel only shows the service's verdicts — it
never decides itself whether a function can be set:

    active      the detector already does it                   (green)
    settable    the listed selector moves make it so           (SET PATH)
    collision   a selector on the way is held elsewhere        (orange, reason)
    impossible  no source can provide it now                   (grey, reason)

``SET PATH`` returns as soon as the service accepts; the switch runs like a slew and is followed in
the ``Operation`` line (moving → done | failed).

What is unknown on the detector's path is listed with its cause ("dome — shutter reports Error
(ShutterState 4)"); ``Declare…`` lets the operator vouch for it when they know better than the
sensor (the shutter opened by hand) — visible as declared by whom until a reading proves it again.
Names are the ones people use ("mirror covers", "M3"), from ``obcom.optics.label`` over the
published graph — the same words the service's reasons use.

On top, the path ribbon (:class:`optics_view.RibbonView`): the way to the detector from the emitter
that feeds it now; with the selected function settable, its moves choose the way drawn past a
blocker. The panel reads the shared :class:`optics_model.OpticsModel`, it subscribes nothing itself.
"""
import logging

import qasync as qs
from datamodels.optics import UNDEFINED, SeesRecord, VerdictKind, split_state_key
from obcom.optics import OpticalGraph, label
from ocaboxapi.exceptions import OcaboxError
from PyQtX.QtCore import Qt
from PyQtX.QtGui import QBrush, QColor
from PyQtX.QtGui import QFontMetrics
from PyQtX.QtWidgets import QComboBox, QGridLayout, QGroupBox, QInputDialog, QLabel, QPushButton, QSizePolicy

from optics_model import OpticsModel
from optics_view import RibbonView, info_html

logger = logging.getLogger(__name__.rsplit('.')[-1])

_VERDICT_COLOR = {
    VerdictKind.ACTIVE: QColor(0, 150, 0),
    VerdictKind.SETTABLE: QColor(0, 0, 0),
    VerdictKind.COLLISION: QColor(220, 120, 0),
    VerdictKind.IMPOSSIBLE: QColor(140, 140, 140),
    VerdictKind.INVALID: QColor(200, 0, 0),
}
_OPERATION_STYLE = {
    'moving': "background-color: rgb(136, 142, 228); color: black;",  # blue, as M3 moving
    'failed': "background-color: rgb(255, 120, 120); color: black;",
}
_FOREGROUND_ROLE = Qt.ItemDataRole.ForegroundRole
_TOOLTIP_ROLE = Qt.ItemDataRole.ToolTipRole
_IDLE_STYLE = "background-color: rgb(233, 233, 233); color: black;"
_UNKNOWN_STYLE = "color: rgb(220, 120, 0);"
_WITHDRAW = "withdraw"

#: what each row of the panel is, for the operator who points at it
HINTS = {
    "ribbon": "The path to this detector: from the light that feeds it now (sky, lamp, flat screen) to the detector.\n"
              "When it sees dark or unknown, the part beyond what blocks it is drawn dimmed.\n"
              "Point at a component for its positions and causes; the legend is in the sky window's Optical path tab.",
    "sees": "What reaches the detector now, as the optics service proves it from readings:\n"
            "a light class (sky.science, lamp.thar …), dark — and what blocks it, or unknown — and what is unproven.",
    "unknown": "Components on this path no reading proves, with the reason.\n"
               "Declare… lets you vouch for one you know (e.g. the shutter opened by hand):\n"
               "shown with your name until a reading returns, at most 12 h.",
    "declare": "Vouch for a position no reading proves, or withdraw your declaration. Needs Take Control.",
    "function": "What this detector can be set up for. Colour is the optics service's verdict:\n"
                "green active — already so;  black settable — SET PATH moves what is listed;\n"
                "orange collision — something on the way is held (an exposure, an operator);  grey impossible — and why.",
    "set": "Make the selected function so: the optics service moves the listed components (needs Take Control).\n"
           "It runs like a slew — follow it in Operation.",
    "operation": "The switch the optics service runs or ran last: moving → done | failed, with what moved.",
}


def light_name(light_class: str) -> str:
    """The model's ``undefined`` is what an operator calls unknown."""
    return "unknown" if light_class == UNDEFINED else light_class


def describe_sees(graph: OpticalGraph, records: list[SeesRecord]) -> str:
    """``sky.science``, ``dark — mirror covers``, ``unknown — dome``; several records joined."""
    if not records:
        return "nothing"
    return "; ".join(r.light_class if r.light_class.startswith(r.terminal) else f"{light_name(r.light_class)} — {label(graph, r.terminal)}"
                     for r in records)


def describe_moves(graph: OpticalGraph, moves: dict) -> str:
    return ", ".join(f"{label(graph, key)} → {position}" for key, position in (moves or {}).items())


def describe_verdict(graph: OpticalGraph, verdict) -> str:
    """One line for the operator: what is, what would move, or why not."""
    if verdict.kind == VerdictKind.ACTIVE:
        return "active"
    if verdict.kind == VerdictKind.SETTABLE:
        return "settable: " + describe_moves(graph, verdict.moves)
    if verdict.kind == VerdictKind.INVALID:
        return "invalid configuration: " + "; ".join(e.message for e in verdict.errors)
    return f"{verdict.kind.value}: {verdict.reason}"


def describe_operation(graph: OpticalGraph, operation: dict) -> str:
    state = operation.get('state', 'idle')
    if state == 'idle':
        return "idle"
    moves = describe_moves(graph, operation.get('moves'))
    text = f"{state}: {operation.get('detector')} {operation.get('function')}"
    text += f" ({moves})" if moves else ""
    return text + (f" — {operation['message']}" if operation.get('message') else "")


def _hinted(text: str, hint: str) -> QLabel:
    """A row title with the small "i" saying there is a hint on it."""
    label = QLabel(f"{text}&nbsp;{info_html()}")
    label.setToolTip(hint)
    return label


class ElidedLabel(QLabel):
    """One line whatever the text: cut to the width with an ellipsis, the whole text in the tooltip —
    the panel keeps its height when a reason gets long."""

    def __init__(self):
        super().__init__()
        self._text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_text(self, text: str, tooltip: str | None = None):
        self._text = text
        self.setToolTip(tooltip if tooltip is not None else text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(QFontMetrics(self.font()).elidedText(self._text, Qt.TextElideMode.ElideRight, max(self.width(), 20)))


class OpticsPanel(QGroupBox):
    """Optical path of one ``detector`` (a component with ``paths:`` in the telescope config).

    :param toi: the TOI main object (operator access, log, warnings)
    :param model: the active telescope's optics, as the service publishes them
    :param detector: detector component name, e.g. ``camera`` or ``beso``
    """

    def __init__(self, toi, model: OpticsModel, detector: str):
        super().__init__("Optical path")
        self.toi = toi
        self.model = model
        self.detector = detector

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # never grows: rows are single lines
        self.ribbon = RibbonView(model, detector)
        self.sees_l = ElidedLabel()
        self.unknown_l = ElidedLabel()
        self.declare_p = QPushButton("Declare…")
        self.declare_p.clicked.connect(self.declare)
        self.function_s = QComboBox()
        self.function_s.currentIndexChanged.connect(self._show_selected)
        self.set_p = QPushButton("SET PATH")
        self.set_p.clicked.connect(self.set_path)
        self.verdict_l = ElidedLabel()
        self.operation_l = ElidedLabel()

        grid = QGridLayout()
        grid.setContentsMargins(8, 4, 8, 6)
        grid.setVerticalSpacing(2)
        grid.addWidget(self.ribbon, 0, 0, 1, 3)
        self.ribbon.setToolTip(HINTS["ribbon"])
        self.declare_p.setToolTip(HINTS["declare"])
        self.function_s.setToolTip(HINTS["function"])
        self.set_p.setToolTip(HINTS["set"])
        grid.addWidget(_hinted("Sees:", HINTS["sees"]), 1, 0)
        grid.addWidget(self.sees_l, 1, 1, 1, 2)
        grid.addWidget(_hinted("Unknown:", HINTS["unknown"]), 2, 0)
        grid.addWidget(self.unknown_l, 2, 1)
        grid.addWidget(self.declare_p, 2, 2)
        grid.addWidget(_hinted("Function:", HINTS["function"]), 3, 0)
        grid.addWidget(self.function_s, 3, 1)
        grid.addWidget(self.set_p, 3, 2)
        grid.addWidget(self.verdict_l, 4, 1, 1, 2)
        grid.addWidget(_hinted("Operation:", HINTS["operation"]), 5, 0)
        grid.addWidget(self.operation_l, 5, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        self.setLayout(grid)

        model.graph_changed.connect(self._show_all)
        model.sees_changed.connect(self._sees_update)
        model.functions_changed.connect(self._functions_update)
        model.selectors_changed.connect(self._selectors_update)
        model.operation_changed.connect(self._operation_update)
        self._show_all()

    @property
    def graph(self) -> OpticalGraph | None:
        return self.model.graph

    @property
    def records(self) -> list[SeesRecord]:
        return self.model.sees.get(self.detector, [])

    @property
    def functions(self) -> dict:
        return self.model.functions.get(self.detector, {})

    # ------------------------------------------------------------------ updates

    def _show_all(self):
        """Another telescope: shown only for a detector with an optical path."""
        self.setVisible(self.model.has_paths(self.detector))
        self._sees_update(self.detector)
        self._functions_update(self.detector)
        self._operation_update()

    def _sees_update(self, detector: str):
        if detector != self.detector:
            return
        if not self.records:
            self.sees_l.set_text("--")
        else:
            self.sees_l.set_text(describe_sees(self.graph, self.records), "\n".join(
                f"{light_name(r.light_class)} ← {label(self.graph, r.terminal)}"
                + (f" via {' → '.join(label(self.graph, c) for c in r.via)}" if r.via else "") for r in self.records))
        self._show_unknown()
        self.ribbon.update()

    def _functions_update(self, detector: str):
        if detector != self.detector:
            return
        selected = self.function_s.currentText()
        self.function_s.blockSignals(True)
        self.function_s.clear()
        for row, (function, verdict) in enumerate(self.functions.items()):
            self.function_s.addItem(function)
            self.function_s.setItemData(row, QBrush(_VERDICT_COLOR[verdict.kind]), _FOREGROUND_ROLE)
            self.function_s.setItemData(row, describe_verdict(self.graph, verdict), _TOOLTIP_ROLE)
        if selected in self.functions:
            self.function_s.setCurrentText(selected)
        self.function_s.blockSignals(False)
        self._show_selected()

    def _selectors_update(self):
        self._show_unknown()
        self.ribbon.update()

    def _operation_update(self):
        operation = self.model.operation
        self.operation_l.set_text(describe_operation(self.graph, operation) if self.graph is not None else "")
        self.operation_l.setStyleSheet(_OPERATION_STYLE.get(operation.get('state'), _IDLE_STYLE))

    def _show_selected(self):
        verdict = self.functions.get(self.function_s.currentText())
        if verdict is None:
            self.verdict_l.set_text("" if self.functions else "no optical path from the optics service")
            self.set_p.setEnabled(False)
            self.ribbon.set_target({})
            return
        self.verdict_l.set_text(f"↳ {describe_verdict(self.graph, verdict)}")
        self.verdict_l.setStyleSheet(f"color: {_VERDICT_COLOR[verdict.kind].name()};")
        self.set_p.setEnabled(verdict.kind == VerdictKind.SETTABLE)
        self.ribbon.set_target(verdict.moves if verdict.kind == VerdictKind.SETTABLE else {})

    def _path_axes(self) -> dict[str, dict]:
        """The state axes on what the detector sees now, as the service reports them."""
        on_path = {c for r in self.records for c in (r.terminal, *r.via)}
        return {key: entry for key, entry in self.model.selectors.items() if split_state_key(key)[0] in on_path}

    def _show_unknown(self):
        """Unknown axes on the path with their causes, and declared ones with who vouched; Declare…
        only when there is something to vouch for (or withdraw)."""
        items = []
        for key, entry in self._path_axes().items():
            name = entry.get('label') or key
            if entry.get('position') is None:
                items.append(f"{name} — {entry.get('cause') or 'no reading'}")
            elif entry.get('origin') == 'declared':
                items.append(f"{name} declared {entry['position']} by {entry.get('by')} — {entry.get('cause') or 'no reading'}")
        self.unknown_l.set_text("; ".join(items) or "—", "\n".join(items))
        self.unknown_l.setStyleSheet(_UNKNOWN_STYLE if items else "")
        self.declare_p.setEnabled(bool(items))

    # ------------------------------------------------------------------ commands

    async def _allowed(self, action: str) -> bool:
        tel = self.toi.active_tel
        await self.toi.update_log(f'{action} {self.detector}', "OPERATOR", tel)
        if not self.toi.tel_acces[tel]:
            self.toi.WarningWindow("WARNING: U don't have control")
            return False
        return True

    @qs.asyncSlot()
    async def set_path(self):
        function = self.function_s.currentText()
        tel = self.toi.active_tel
        if not await self._allowed(f'SET PATH {function}'):
            return
        try:
            accepted = await self.model.telescope.get_optical_detector(self.detector).aput_setpath(function)
        except OcaboxError as e:
            await self.toi.update_log(f'optics refused {self.detector} {function}: {e}', "TOI RESPONDER", tel)
            self.toi.WarningWindow(f"Optical path {self.detector} → {function} refused:\n{e}")
            return
        moves = describe_moves(self.graph, (accepted or {}).get('moves'))
        await self.toi.update_log(f'setting {self.detector} path to {function} ({moves or "no moves"})',
                                  "TOI RESPONDER", tel)

    def declaration_choices(self) -> dict[str, tuple[str, str | None]]:
        """Dialog item → (state key, position): every position of an unknown axis on the path, and
        withdrawing a declared one."""
        choices = {}
        for key, entry in self._path_axes().items():
            name = entry.get('label') or key
            component, aspect = split_state_key(key)
            if entry.get('origin') == 'declared':
                choices[f"{name}: {_WITHDRAW} the declaration ({entry['position']} by {entry.get('by')})"] = (key, None)
            elif entry.get('position') is None:
                axis = next(a for a in self.graph.node(component).axes if a.name == aspect)
                for position in axis.vocabulary:
                    choices[f"{name} is {position}"] = (key, position)
        return choices

    @qs.asyncSlot()
    async def declare(self):
        choices = self.declaration_choices()
        if not choices:
            return
        item, ok = QInputDialog.getItem(self, "Declare", "Vouch for what no reading proves:", list(choices), 0, False)
        if not ok:
            return
        key, position = choices[item]
        tel = self.toi.active_tel
        if not await self._allowed(f'DECLARE {item}'):
            return
        try:
            await self.model.telescope.get_optics().aput_declare(key, position)
        except OcaboxError as e:
            await self.toi.update_log(f'optics refused the declaration {item}: {e}', "TOI RESPONDER", tel)
            self.toi.WarningWindow(f"Declaration refused:\n{e}")
            return
        await self.toi.update_log(f'declared: {item}', "TOI RESPONDER", tel)
