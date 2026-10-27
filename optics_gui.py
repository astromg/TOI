"""Optical path panel of an instrument tab: the way light takes to the detector, and switching it.

The ``optics`` service (ocabox-tcs) owns the optical path of a telescope; TOI reaches it through TIC
like any device (``ocaboxapi`` ``Telescope.get_optical_detector`` / ``get_optics``), so the access
control is the operator's reservation, as for M3. The panel only shows what the service says — it
never decides itself whether a function can be set.

Three lines under the ``OPTICAL PATH`` title:

- the ribbon (:class:`optics_view.RibbonView`): the way to the detector from what feeds it now (the
  sky, a lamp), each part with its position and what the detector sees; with the selected function
  settable, its moves choose the way drawn past a blocker;
- ``FUNCTION`` (object, dark, arc …, each with the dot of its verdict), ``SET PATH``, and
  ``Confirm by hand…`` while a part on the path has no reading or a confirmation to take back;
- the status (:class:`optics_view.StatusLine`) of the selected function — READY, SETTABLE (what
  SET PATH moves, and which moves ask a person first), WAITING (light still to come: the sky at
  dusk; SET PATH prepares the path), BLOCKED or NOT POSSIBLE (why), CONFIG ERROR — or of the switch:
  CONFIRM (it waits for a person), MOVING, FAILED (why). Colour is in the chip only; the words are
  always black.

A change that waits for a person (the telescope and the dome to the flat screen; the covers by
day) is shown on its instrument's panel to everyone, whoever asked — the operator's own SET PATH or
a planrunner. It is confirmed with a guarded switch, never a modal: the first click arms it (the
button says what will move), a second one within 5 s confirms, otherwise it disarms; Reject turns
it down. ``Confirm by hand…`` opens a non-modal table: one row per part no sensor reads, a button per
position it can be at, and taking back a confirmation.

``SET PATH`` returns as soon as the service accepts; the switch runs like a slew. ``Confirm by
hand…`` declares where a part is when no sensor can say (the shutter opened by hand) — shown with
who confirmed it until a reading proves it again. Names are the ones people use ("mirror covers",
"M3"), from ``obcom.optics.label`` over the published graph — the same words as the service's
reasons. The panel reads the shared :class:`optics_model.OpticsModel`; it subscribes nothing itself.
"""
import logging
import time
from dataclasses import dataclass

import qasync as qs
from datamodels.optics import Impossible, VerdictKind, split_state_key
from obcom.optics import OpticalGraph, label
from ocaboxapi.exceptions import OcaboxError
from PyQtX.QtCore import Qt, QTimer
from PyQtX.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

from optics_model import OpticsModel
from optics_view import THEME, RibbonView, Status, StatusLine, hint_html, status_icon

logger = logging.getLogger(__name__.rsplit('.')[-1])

_TOOLTIP_ROLE = Qt.ItemDataRole.ToolTipRole

#: the chip of each verdict: what it says to the operator
VERDICT_WORDS = {
    VerdictKind.ACTIVE: "READY",
    VerdictKind.SETTABLE: "SETTABLE",
    VerdictKind.COLLISION: "BLOCKED",
    VerdictKind.IMPOSSIBLE: "NOT POSSIBLE",
    VerdictKind.INVALID: "CONFIG ERROR",
}

#: what the panel and its parts are, in plain words, for the operator who points at them
HINTS = {
    "panel": "How light gets to this instrument, and switching it.\n\n"
             "Top: the parts light passes, from where it comes (the sky or a lamp) to the instrument.\n"
             "Coloured line: light.  Grey dots: no light.  Red dashes: not known.  Point at a part for details.\n\n"
             "FUNCTION: what you want the instrument to do; SET PATH moves mirrors and covers to make it ready.\n\n"
             "Below, whether it is ready:\n"
             "  READY — it is.\n"
             "  SETTABLE — SET PATH will make it ready; the moves are listed.\n"
             "  BLOCKED — something holds a part elsewhere (an exposure, a part only moved by hand).\n"
             "  NOT POSSIBLE — not now; the reason follows.\n"
             "  MOVING / FAILED — the switch SET PATH started.",
    "ribbon": "How light gets to this instrument, starting where it comes from (the sky or a lamp).\n"
              "Coloured line: light.  Grey dots: no light.  Red dashes: not known.\n"
              "Point at a part to see where it is set.",
    "function": "What you want this instrument to do. The dot says whether it is ready:\n"
                "green ready, grey SET PATH will do it, orange blocked, red not possible now.",
    "set": "Move mirrors and covers so the chosen function is ready. Needs Take Control.",
    "confirm_move": "This change moves something big — the telescope and the dome to the flat screen,\n"
                    "or the mirror covers by day — so it waits for a person to confirm it.\n"
                    "Click once: the button says what will move. Click again within 5 seconds to move.\n"
                    "Make sure nobody is in the way. Reject turns it down. Needs Take Control.",
    "confirm": "A part on this path, or one the chosen function needs, has no working sensor,\n"
               "so the system cannot tell where it is (or whether a lamp is on).\n"
               "If you have checked it yourself, tell the system here; your name is shown with it\n"
               "until the sensor works again (at most 12 hours). You can take it back here too.\n"
               "Needs Take Control.",
}


def describe_moves(graph: OpticalGraph, moves: dict) -> str:
    return ", ".join(f"{label(graph, key)} → {position}" for key, position in (moves or {}).items())


def describe_verdict(graph: OpticalGraph, verdict) -> str:
    """One line for the operator: what is, what would move, or why not."""
    if verdict.kind == VerdictKind.ACTIVE:
        return f"sees {verdict.see}"
    if verdict.kind == VerdictKind.SETTABLE:
        return f"SET PATH moves {describe_moves(graph, verdict.moves)}"
    if verdict.kind == VerdictKind.INVALID:
        return "; ".join(e.message for e in verdict.errors)
    return verdict.reason


def waits_for_a_person(operation: dict, detector: str) -> bool:
    return operation.get('state') == 'awaiting_confirmation' and operation.get('detector') == detector


def path_status(graph: OpticalGraph, detector: str, function: str, verdict, operation: dict,
                confirmed: list[str], unknown: str | None = None) -> Status:
    """The status of ``detector``: its switch while it waits for a person or runs (and how it failed,
    for the function that failed), else the verdict of the selected ``function``; ``confirmed`` are
    the parts on the path people vouch for, named wherever the path relies on them; ``unknown`` why
    the verdicts are not known now (TIC or the service silent)."""
    if operation.get('detector') == detector:
        state, switched = operation.get('state'), operation.get('function')
        if state == 'awaiting_confirmation':
            waiting = operation.get('confirm') or {}
            until = time.strftime('%H:%M:%S', time.localtime(waiting.get('expires_at', time.time())))
            return Status('collision', "CONFIRM", f"{switched}: {'; '.join(waiting.get('says') or [])} — waits for a person "
                                                  f"until {until}, asked by {operation.get('caller') or 'unknown'}")
        if state == 'moving':
            return Status('moving', "MOVING", f"{switched}: {describe_moves(graph, operation.get('moves'))}")
        if state == 'failed' and switched == function:
            return Status('failed', "FAILED", operation.get('message') or f"{switched}: the switch failed")
    if verdict is None:
        return Status('none', "NO DATA", unknown or "the optics service publishes nothing for this instrument")
    if isinstance(verdict, Impossible) and getattr(verdict, 'awaits', None) is not None:
        moves = getattr(verdict, 'prepare', None)
        prepare = f"SET PATH prepares it now: {describe_moves(graph, moves)}" if moves else "the path is ready"
        return Status('settable', "WAITING", f"{verdict.reason} · {prepare}")
    text = describe_verdict(graph, verdict)
    if verdict.kind == VerdictKind.SETTABLE and verdict.confirm:
        text += f" · asks you to confirm: {', '.join(label(graph, key) for key in verdict.confirm)}"
    if confirmed and verdict.kind in (VerdictKind.ACTIVE, VerdictKind.SETTABLE):
        text += " · " + "; ".join(confirmed)
    return Status(verdict.kind.value, VERDICT_WORDS[verdict.kind], text)


def settable_now(verdict) -> bool:
    """SET PATH has something to do: moves that make the function ready, or prepare for its light."""
    if verdict is None:
        return False
    # getattr: datamodels older than the waiting light (no awaits/prepare) aborted TOI here
    return verdict.kind == VerdictKind.SETTABLE or (isinstance(verdict, Impossible) and bool(getattr(verdict, 'prepare', None)))


@dataclass(frozen=True)
class HandRow:
    """One part to confirm by hand: what it is, what is known of it, and the answers a person can give
    (text, position; ``None`` takes a confirmation back)."""

    key: str
    name: str
    now: str
    answers: tuple[tuple[str, str | None], ...]


def _hinted(text: str, hint: str) -> QLabel:
    """A title with the small "?" saying there is a hint on it."""
    title = QLabel(f"{text}&nbsp;{hint_html()}")
    title.setToolTip(hint)
    return title


class OpticsPanel(QWidget):
    """Optical path of one ``detector`` (a component with ``paths:`` in the telescope config).

    :param toi: the TOI main object (operator access, log, warnings)
    :param model: the active telescope's optics, as the service publishes them
    :param detector: detector component name, e.g. ``camera`` or ``beso``
    """

    def __init__(self, toi, model: OpticsModel, detector: str):
        super().__init__()
        self.toi = toi
        self.model = model
        self.detector = detector
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # never grows: every line is one line

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Sunken)
        self.ribbon = RibbonView(model, detector)
        self.ribbon.setToolTip(HINTS["ribbon"])
        self.function_s = QComboBox()
        self.function_s.setToolTip(HINTS["function"])
        self.function_s.currentIndexChanged.connect(self._show_selected)
        self.set_p = QPushButton("SET PATH")
        self.set_p.setToolTip(HINTS["set"])
        self.set_p.clicked.connect(self.set_path)
        self.declare_p = QPushButton("Confirm by hand…")
        self.declare_p.setToolTip(HINTS["confirm"])
        self.declare_p.clicked.connect(self.declare)
        self.status = StatusLine()
        self.confirm_p = QPushButton("CONFIRM…")
        self.confirm_p.setToolTip(HINTS["confirm_move"])
        self.confirm_p.clicked.connect(self._confirm_clicked)
        self.reject_p = QPushButton("Reject")
        self.reject_p.setToolTip(HINTS["confirm_move"])
        self.reject_p.clicked.connect(self.reject_move)
        self.confirm_row = QWidget()
        row = QHBoxLayout(self.confirm_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.confirm_p, 1)
        row.addWidget(self.reject_p)
        self.confirm_row.setVisible(False)
        self._armed = QTimer(self)
        self._armed.setSingleShot(True)
        self._armed.setInterval(5000)
        self._armed.timeout.connect(self._disarm)
        self._hand: ConfirmByHandDialog | None = None

        title = QHBoxLayout()
        title.addWidget(_hinted("OPTICAL PATH", HINTS["panel"]))
        title.addWidget(rule, 1)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setVerticalSpacing(4)
        grid.addLayout(title, 0, 0, 1, 4)
        grid.addWidget(self.ribbon, 1, 0, 1, 4)
        grid.addWidget(QLabel("FUNCTION:"), 2, 0)
        grid.addWidget(self.function_s, 2, 1)
        grid.addWidget(self.set_p, 2, 2)
        grid.addWidget(self.declare_p, 2, 3)
        grid.addWidget(self.status, 3, 0, 1, 4)
        grid.addWidget(self.confirm_row, 4, 0, 1, 4)
        grid.setColumnStretch(1, 1)

        model.graph_changed.connect(self._show_all)
        model.sees_changed.connect(self._sees_update)
        model.functions_changed.connect(self._functions_update)
        model.selectors_changed.connect(self._path_update)
        model.operation_changed.connect(self._show_status)
        self._show_all()

    @property
    def graph(self) -> OpticalGraph | None:
        return self.model.graph

    @property
    def functions(self) -> dict:
        return self.model.functions.get(self.detector, {})

    # ------------------------------------------------------------------ updates

    def _show_all(self):
        """Another telescope: shown only for a detector with an optical path."""
        self.setVisible(self.model.has_paths(self.detector))
        self._functions_update(self.detector)
        self._path_update()

    def _sees_update(self, detector: str):
        if detector == self.detector:
            self._path_update()

    def _path_update(self):
        self.ribbon.update()
        self.declare_p.setVisible(bool(self.declaration_rows()))
        self._show_status()

    def _functions_update(self, detector: str):
        if detector != self.detector:
            return
        selected = self.function_s.currentText()
        self.function_s.blockSignals(True)
        self.function_s.clear()
        for row, (function, verdict) in enumerate(self.functions.items()):
            self.function_s.addItem(status_icon(verdict.kind.value), function)
            self.function_s.setItemData(row, f"{VERDICT_WORDS[verdict.kind]}: {describe_verdict(self.graph, verdict)}", _TOOLTIP_ROLE)
        if selected in self.functions:
            self.function_s.setCurrentText(selected)
        self.function_s.blockSignals(False)
        self._show_selected()

    def _show_selected(self):
        verdict = self.functions.get(self.function_s.currentText())
        settable = verdict is not None and verdict.kind == VerdictKind.SETTABLE
        self.ribbon.set_target(verdict.moves if settable else {})
        self.declare_p.setVisible(bool(self.declaration_rows()))
        self._show_status()

    def _show_status(self):
        if self.graph is None:
            self.set_p.setEnabled(False)
            self.status.set_status(Status('none', ""))
            return
        function = self.function_s.currentText()
        axes = self._path_axes()
        confirmed = [f"{entry.get('label') or key} {entry['position']}, confirmed by hand by {entry.get('by')}"
                     for key, entry in axes.items() if entry.get('origin') == 'declared']
        verdict = self.functions.get(function)
        operation = self.model.operation
        self.set_p.setEnabled(settable_now(verdict)  # one switch at a time, a waiting one included
                              and operation.get('state') not in ('moving', 'awaiting_confirmation'))
        waiting = waits_for_a_person(operation, self.detector)
        self.confirm_row.setVisible(waiting)
        if not waiting:
            self._disarm()
        status = path_status(self.graph, self.detector, function, verdict, self.model.operation, confirmed,
                             self.model.unknown.get(self.detector))
        unread = [f"{entry.get('label') or key}: not known — {entry.get('cause') or 'no reading'}"
                  for key, entry in axes.items() if entry.get('position') is None]
        self.status.set_status(Status(status.kind, status.word, status.text, "\n".join([status.text, *unread, *confirmed])))

    def _path_axes(self) -> dict[str, dict]:
        """The state axes on what the detector sees now, as the service reports them."""
        on_path = {c for r in self.model.sees.get(self.detector, []) for c in (r.terminal, *r.via)}
        return {key: entry for key, entry in self.model.selectors.items() if split_state_key(key)[0] in on_path}

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

    def declaration_rows(self) -> list[HandRow]:
        """What a person can confirm by hand: every unknown axis on the path or needed by the selected
        function (the flat screen's lamps before the telescope points at it), with each position it
        can be at, and every confirmation to take back."""
        rows = []
        if self.graph is None:
            return rows
        verdict = self.functions.get(self.function_s.currentText())
        needed = set(verdict.undefined_at) if isinstance(verdict, Impossible) else set()  # only Impossible has it
        axes = {**{key: self.model.selectors[key] for key in needed if key in self.model.selectors}, **self._path_axes()}
        for key, entry in axes.items():
            name = entry.get('label') or key
            component, aspect = split_state_key(key)
            if entry.get('origin') == 'declared':
                rows.append(HandRow(key, name, f"{entry['position']}, confirmed by {entry.get('by')}", (("Take back", None),)))
            elif entry.get('position') is None:
                node = self.graph.nodes.get(component)
                axis = next((a for a in node.axes if a.name == aspect), None) if node is not None else None
                if axis is None:
                    continue  # published by a newer service than this client's graph knows (a rollout)
                switched = set(axis.vocabulary) == {'off', 'on'}  # a lamp is on, a mirror is at a position
                answers = tuple((f"is {p}" if switched else f"at {p}", p) for p in axis.vocabulary)
                rows.append(HandRow(key, name, f"not known — {entry.get('cause') or 'no reading'}", answers))
        return rows

    def declare(self):
        """The "Confirm by hand" table, non-modal: a modal ``exec`` inside a qasync task stops every
        other task (TIC, NATS, all subscriptions) until it closes."""
        if self._hand is None:
            self._hand = ConfirmByHandDialog(self)
        self._hand.show()
        self._hand.refresh()
        self._hand.raise_()

    # ------------------------------------------------------------------ confirming a move

    def _confirm_clicked(self):
        """The guarded switch: the first click arms it and says what will move, the second within
        5 s confirms."""
        if not self._armed.isActive():
            keys = (self.model.operation.get('confirm') or {}).get('keys') or []
            self.confirm_p.setText(f"Click again to move {', '.join(self._what_moves(k) for k in keys) or 'now'}")
            fill = THEME.status['collision']
            self.confirm_p.setStyleSheet(f"background-color: {fill['fill']}; color: {fill['ink']}; font-weight: bold;")
            self._armed.start()
            return
        self._disarm()
        self.confirm_move()

    def _what_moves(self, key: str) -> str:
        """What a confirmed move sets in motion, in words: the dome going to the flat screen takes the
        telescope with it."""
        component, _ = split_state_key(key)
        node = self.graph.nodes.get(component) if self.graph is not None else None
        if node is not None and node.spec.kind == 'dome':
            return "the telescope and the dome"
        return label(self.graph, key)

    def _disarm(self):
        self._armed.stop()
        self.confirm_p.setText("CONFIRM…")
        self.confirm_p.setStyleSheet("")

    @qs.asyncSlot()
    async def confirm_move(self):
        operation = self.model.operation
        tel = self.toi.active_tel
        if not waits_for_a_person(operation, self.detector) or not await self._allowed(f'CONFIRM {operation.get("function")}'):
            return
        try:
            await self.model.telescope.get_optics().aput_confirm(operation['id'])
        except OcaboxError as e:
            await self.toi.update_log(f'optics refused the confirmation: {e}', "TOI RESPONDER", tel)
            self.toi.WarningWindow(f"Confirmation refused:\n{e}")
            return
        await self.toi.update_log(f'confirmed {self.detector} {operation.get("function")}: '
                                  f'{"; ".join((operation.get("confirm") or {}).get("says") or [])}', "TOI RESPONDER", tel)

    @qs.asyncSlot()
    async def reject_move(self):
        operation = self.model.operation
        tel = self.toi.active_tel
        if not waits_for_a_person(operation, self.detector) or not await self._allowed(f'REJECT {operation.get("function")}'):
            return
        try:
            await self.model.telescope.get_optics().aput_reject(operation['id'], reason='rejected in TOI')
        except OcaboxError as e:
            await self.toi.update_log(f'optics refused the rejection: {e}', "TOI RESPONDER", tel)
            return
        await self.toi.update_log(f'rejected {self.detector} {operation.get("function")}', "TOI RESPONDER", tel)

    @qs.asyncSlot()
    async def _declare(self, item: str, choice: tuple[str, str | None]):
        key, position = choice
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


class ConfirmByHandDialog(QDialog):
    """Confirm by hand, as a table: one row per part no sensor reads — its name, what is known, a button
    per position it can be at — and a row to take back each confirmation. Non-modal; it follows the
    panel's model while open."""

    def __init__(self, panel: OpticsPanel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle(f"Confirm by hand — {panel.detector}")
        self.setModal(False)
        intro = QLabel("No sensor reports where these parts are. If you have checked one yourself, say where it is.\n"
                       "Your name is shown with it until its sensor works again (at most 12 hours). Needs Take Control.")
        intro.setWordWrap(True)
        self.rows = QGridLayout()
        self.rows.setHorizontalSpacing(12)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(self.rows)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        panel.model.selectors_changed.connect(self.refresh)
        panel.model.functions_changed.connect(lambda detector: self.refresh())

    def refresh(self):
        if not self.isVisible() and self.rows.count():
            return  # updated when shown again
        while self.rows.count():
            widget = self.rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        rows = self.panel.declaration_rows()
        if not rows:
            self.rows.addWidget(QLabel("Nothing to confirm: every part on this path is read by its sensor."), 0, 0)
            return
        for i, row in enumerate(rows):
            name = QLabel(f"<b>{row.name}</b>")
            now = QLabel(row.now)
            self.rows.addWidget(name, i, 0)
            self.rows.addWidget(now, i, 1)
            answers = QWidget()
            buttons = QHBoxLayout(answers)
            buttons.setContentsMargins(0, 0, 0, 0)
            for text, position in row.answers:
                button = QPushButton(text)
                button.clicked.connect(lambda _=False, r=row, t=text, p=position:
                                       self.panel._declare(f"{r.name} {t}" if p is not None else f"{r.name}: take back", (r.key, p)))
                buttons.addWidget(button)
            self.rows.addWidget(answers, i, 2)
