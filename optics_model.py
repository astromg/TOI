"""The optical path of the active telescope, as the ``optics`` service (ocabox-tcs) publishes it.

One model per TOI, subscribed once per telescope; the instrument panels and the Aux window's
"Optical path" tab draw from it. It holds only what the service says — the graph from the
published telescope config, the state axes (``self.selectors``: selectors and sources, with
causes and declarations), what every detector sees, the verdicts of the detectors' functions and
the running operation — and derives nothing the service decides.

Its subscriptions get what TIC delivered, the obcom ``Value`` (``ocabox`` ≥ 2.11). A ``None`` is
the Staleness Contract saying TIC has no truthful value — then nothing is shown as known, never an
old path as the current one — and its ``reason`` says why (:func:`why_none`): the panel tells the
operator whether TIC or the optics service is silent.
"""
import logging
from functools import partial

from datamodels.optics import SeesRecord, Verdict
from obcom.data_colection.value import Value
from obcom.optics import GraphInvalid, OpticalGraph, Ribbon, parse_graph, published_values, ribbon
from pydantic import TypeAdapter, ValidationError
from PyQtX.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__.rsplit('.')[-1])

_SEES = TypeAdapter(list[SeesRecord])
_FUNCTIONS = TypeAdapter(dict[str, Verdict])
#: what the reason of a delivered ``None`` means to an operator (obcom / TIC codes)
_REASONS = {2003: "out of date", 4002: "TIC does not answer", 4005: "the optics service does not answer"}


def why_none(value: Value) -> str:
    """Why a delivered ``Value`` has no truthful value, in words, the code in brackets."""
    reason = value.tags.get('reason')
    words = _REASONS.get(reason) or value.tags.get('message') or "no current data"
    return f"{words} ({reason})" if reason is not None else words


class OpticsModel(QObject):
    """What the optics service publishes for the active telescope; signals say what changed."""

    graph_changed = pyqtSignal()  #: another telescope (or none with optics)
    sees_changed = pyqtSignal(str)  #: detector
    functions_changed = pyqtSignal(str)  #: detector
    selectors_changed = pyqtSignal()
    operation_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.telescope_name: str | None = None
        self.graph: OpticalGraph | None = None
        self.telescope = None  #: ocaboxapi Telescope, for commands
        self.selectors: dict[str, dict] = {}  #: state key → {position, origin, moving, cause, by, label}
        self.sees: dict[str, list[SeesRecord]] = {}
        self.functions: dict[str, dict[str, Verdict]] = {}
        self.unknown: dict[str, str] = {}  #: detector → why its functions are not known now
        self.operation: dict = {}

    def load(self, telescope_name: str | None, components: dict) -> None:
        """The graph of ``telescope_name`` from its published ``components:``; none without optics."""
        self.telescope_name, self.graph, self.telescope = telescope_name, None, None
        self.selectors, self.sees, self.functions, self.unknown, self.operation = {}, {}, {}, {}, {}
        if any((spec or {}).get("paths") for spec in components.values()):
            try:
                self.graph = parse_graph(components, telescope=telescope_name)
            except GraphInvalid as e:
                logger.error(f'{telescope_name}: optical graph invalid, no optical path shown: '
                             f'{"; ".join(err.message for err in e.errors)}')
        self.graph_changed.emit()

    def has_paths(self, detector: str) -> bool:
        return self.graph is not None and detector in self.graph.nodes and self.graph.node(detector).paths is not None

    @property
    def positions(self) -> dict[str, str | None]:
        """Every state axis as published (optics >= 1.5 publishes them all: sources, the derived dome)."""
        return {key: entry.get('position') for key, entry in self.selectors.items()}

    def ribbon(self, detector: str, target: dict[str, str] | None = None) -> Ribbon:
        return ribbon(self.graph, published_values(self.positions), detector, target)

    def axes_of(self, component: str) -> dict[str, dict]:
        """The state axes of one component (its position and aspects), as published."""
        return {key: entry for key, entry in self.selectors.items() if key.partition('.')[0] == component}

    async def asubscribe(self, telescope):
        """Follow the service for ``telescope`` (ends with its ``unsubscribe_all_component``)."""
        if self.graph is None:
            return
        self.telescope = telescope
        for detector in self.graph.detectors:
            optical_detector = telescope.get_optical_detector(detector)
            await optical_detector.asubscribe_sees(partial(self._sees_update, detector))
            if self.has_paths(detector):
                await optical_detector.asubscribe_functions(partial(self._functions_update, detector))
        optics = telescope.get_optics()
        await optics.asubscribe_selectors(self._selectors_update)
        await optics.asubscribe_operation(self._operation_update)

    # ------------------------------------------------------------------ updates

    def _sees_update(self, detector: str, value: Value):
        try:
            self.sees[detector] = _SEES.validate_python(value.v or [])
        except ValidationError as e:
            logger.warning(f'optics {detector}: malformed sees: {e}')
            return
        self.sees_changed.emit(detector)

    def _functions_update(self, detector: str, value: Value):
        if value.v is None:
            if detector not in self.unknown:
                logger.warning(f'optics {detector}: functions not known: {why_none(value)}')
            self.unknown[detector] = why_none(value)
        else:
            self.unknown.pop(detector, None)
        try:
            self.functions[detector] = _FUNCTIONS.validate_python(value.v or {})
        except ValidationError as e:
            logger.warning(f'optics {detector}: malformed functions: {e}')
            return
        self.functions_changed.emit(detector)

    def _selectors_update(self, value: Value):
        self.selectors = value.v or {}
        self.selectors_changed.emit()

    def _operation_update(self, value: Value):
        self.operation = value.v or {}
        self.operation_changed.emit()
