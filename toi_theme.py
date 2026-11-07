"""Motywy wygladu TOI: dzienny (dotychczasowy), nocny i funky.

Kolory maja znaczenie i jest ono wspolne dla wszystkich motywow - zmienia sie tylko odcien:
    ok      - zielony:   obserwacje OK
    bad     - czerwony:  obserwacje nie OK
    warn    - zolty:     uwazac z obserwacjami
    warn2   - pomaranczowy: posredni stopien (kilka teleskopow / gorzej niz zolty, jeszcze nie czerwony)
    change  - niebieski: cos sie zmienia (ruch, zmierzch)
Kazdy kolor jest w dwoch wersjach: *_bg - tlo pola, *_fg - tekst lub ikonka na zwyklym tle.
WYJATEK (rozbieznosc swiadomie zostawiona na razie, 2026-11-06): tabela teleskopow w oknie obserwacji ma dawne kolory
(klucze tab_*): ruch (MOVING, SLEWING, OPENING...) pomaranczowy zamiast niebieskiego, ikonki darkgreen/red/darkorange.
Pozostale klucze to neutralne elementy okna (tla pol, tekst, wylaczone lampki).

Uzycie: `from toi_theme import theme` i `theme.c("bad_bg")`; `theme.set(name)` przelacza motyw i wola funkcje
zarejestrowane przez `theme.on_change(f)` (okna przemalowuja to, czego nie odswieza nic innego). Wybor jest
zapamietany w QSettings("OCA", "TOI") / "theme". Okna sa przerabiane po kolei - na razie okno obserwacji.
"""

from PyQtX import QtGui
from PyQtX.QtCore import QSettings
from PyQtX.QtWidgets import QApplication, QStyleFactory

THEMES = {
    # dotychczasowe kolory TOI
    "day": {
        "window": None,                 # None: paleta systemowa
        "text": "black",
        "field_bg": "rgb(235,235,235)",
        "field_fg": "black",
        "muted_fg": "rgb(190,190,190)",
        "selection_bg": "rgb(138,176,219)",
        "ok_bg": "rgb(150, 220, 150)", "ok_fg": "rgb(0, 150, 0)",
        "bad_bg": "red", "bad_fg": "rgb(190, 0, 0)",
        "warn_bg": "rgb(255, 220, 0)", "warn_fg": "rgb(170, 140, 0)",
        "warn2_bg": "rgb(255, 140, 0)", "warn2_fg": "rgb(255, 140, 0)",
        "change_bg": "rgb(190, 220, 255)", "change_fg": "rgb(0, 90, 200)",
        "idle_fg": "black",
        # tabela teleskopow: dawne kolory (inny kod niz reszta - ruch pomaranczowy, nie niebieski), patrz tab_* nizej
        "tab_ok": "rgb(0, 150, 0)", "tab_moving": "rgb(255, 160, 0)", "tab_error": "rgb(150, 0, 0)",
        "tab_icon_ok": "darkgreen", "tab_icon_bad": "red", "tab_icon_warn": "darkorange", "tab_icon_warn2": "orange",
    },
    # ciemny i przygaszony, zeby nie oslepiac w nocy; znaczenie kolorow bez zmian (czerwony = zle)
    "night": {
        "window": "rgb(30, 30, 32)",
        "text": "rgb(170, 170, 160)",
        "field_bg": "rgb(48, 48, 50)",
        "field_fg": "rgb(170, 170, 160)",
        "muted_fg": "rgb(80, 80, 80)",
        "selection_bg": "rgb(60, 70, 95)",
        "ok_bg": "rgb(30, 90, 30)", "ok_fg": "rgb(70, 150, 70)",
        "bad_bg": "rgb(120, 25, 25)", "bad_fg": "rgb(190, 60, 60)",
        "warn_bg": "rgb(110, 95, 20)", "warn_fg": "rgb(190, 165, 50)",
        "warn2_bg": "rgb(120, 65, 15)", "warn2_fg": "rgb(200, 120, 40)",
        "change_bg": "rgb(35, 60, 105)", "change_fg": "rgb(100, 140, 210)",
        "idle_fg": "rgb(170, 170, 160)",
        "tab_ok": "rgb(70, 150, 70)", "tab_moving": "rgb(200, 130, 40)", "tab_error": "rgb(190, 60, 60)",
        "tab_icon_ok": "rgb(70, 150, 70)", "tab_icon_bad": "rgb(190, 60, 60)", "tab_icon_warn": "rgb(190, 110, 30)",
        "tab_icon_warn2": "rgb(200, 140, 50)",
    },
    "funky": {
        "window": "rgb(40, 20, 60)",
        "text": "rgb(240, 230, 255)",
        "field_bg": "rgb(70, 40, 100)",
        "field_fg": "rgb(255, 240, 255)",
        "muted_fg": "rgb(120, 90, 150)",
        "selection_bg": "rgb(200, 60, 160)",
        "ok_bg": "rgb(0, 200, 120)", "ok_fg": "rgb(60, 255, 160)",
        "bad_bg": "rgb(255, 40, 90)", "bad_fg": "rgb(255, 80, 120)",
        "warn_bg": "rgb(255, 230, 0)", "warn_fg": "rgb(255, 235, 60)",
        "warn2_bg": "rgb(255, 130, 0)", "warn2_fg": "rgb(255, 160, 40)",
        "change_bg": "rgb(0, 190, 255)", "change_fg": "rgb(80, 210, 255)",
        "idle_fg": "rgb(240, 230, 255)",
        "tab_ok": "rgb(60, 255, 160)", "tab_moving": "rgb(255, 170, 40)", "tab_error": "rgb(255, 80, 120)",
        "tab_icon_ok": "rgb(60, 255, 160)", "tab_icon_bad": "rgb(255, 80, 120)", "tab_icon_warn": "rgb(255, 140, 0)",
        "tab_icon_warn2": "rgb(255, 180, 60)",
    },
}
TITLES = {"day": "Day", "night": "Night", "funky": "Funky"}

# tekst na tle *_bg: czarny na jasnych tlach dziennych, jasny na ciemnych nocnych
BG_TEXT = {"day": "black", "night": "rgb(210, 210, 200)", "funky": "black"}


class Theme:
    def __init__(self):
        self.name = str(QSettings("OCA", "TOI").value("theme", "day"))
        if self.name not in THEMES:
            self.name = "day"
        self._listeners = []
        self._system_palette = None
        self._system_style = None

    def c(self, key):
        return THEMES[self.name][key]

    def qcolor(self, key):
        return QtGui.QColor(self._css_to_qcolor(self.c(key)))

    @staticmethod
    def _css_to_qcolor(css):
        css = css.strip()
        if css.startswith("rgb("):
            r, g, b = (int(x) for x in css[4:-1].split(","))
            return QtGui.QColor(r, g, b)
        return QtGui.QColor(css)

    def bg_text(self):
        return BG_TEXT[self.name]

    def field_style(self, bg_key="field_bg"):
        """stylesheet pola tylko do odczytu: tlo wg znaczenia, tekst czytelny na nim"""
        fg = self.c("field_fg") if bg_key == "field_bg" else self.bg_text()
        return f"color: {fg}; background-color: {self.c(bg_key)};"

    def on_change(self, f):
        self._listeners.append(f)

    def set(self, name):
        if name not in THEMES:
            return
        self.name = name
        QSettings("OCA", "TOI").setValue("theme", name)
        self.apply_palette()
        for f in self._listeners:
            f()

    def apply_palette(self):
        """paleta calej aplikacji: okna jeszcze nieprzerobione dostaja przynajmniej tlo i tekst motywu"""
        app = QApplication.instance()
        if app is None:
            return
        if self._system_palette is None:
            self._system_palette = QtGui.QPalette(app.palette())
            self._system_style = app.style().name()
        t = THEMES[self.name]
        if t["window"] is None:
            p, style = self._system_palette, self._system_style
        else:
            # styl systemowy potrafi ignorowac palete aplikacji - okna zostaja szare; Fusion ja respektuje
            p, style = QtGui.QPalette(self._system_palette), "Fusion"
            window, text = self._css_to_qcolor(t["window"]), self._css_to_qcolor(t["text"])
            field = self._css_to_qcolor(t["field_bg"])
            for role, color in ((QtGui.QPalette.ColorRole.Window, window), (QtGui.QPalette.ColorRole.Base, field),
                                (QtGui.QPalette.ColorRole.AlternateBase, window), (QtGui.QPalette.ColorRole.Button, field),
                                (QtGui.QPalette.ColorRole.WindowText, text), (QtGui.QPalette.ColorRole.Text, text),
                                (QtGui.QPalette.ColorRole.ButtonText, text), (QtGui.QPalette.ColorRole.ToolTipBase, window),
                                (QtGui.QPalette.ColorRole.ToolTipText, text),
                                (QtGui.QPalette.ColorRole.Highlight, self._css_to_qcolor(t["selection_bg"]))):
                p.setColor(role, color)
        # najpierw paleta, potem styl: zmiana stylu przemalowuje wszystkie okna (takze te z wlasnym stylesheetem,
        # ktore samej zmiany palety nie widza) - odwrotnie okna zostawaly o jeden motyw w tyle
        app.setPalette(p)
        app.setStyle(QStyleFactory.create(style))

theme = Theme()
