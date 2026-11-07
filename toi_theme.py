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
ok_beat_fg - mrugniecie zielonej lampki serwisu (w dzien ciemniejsza zielen, w nocy jasniejsza).
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
        "ok_bg": "rgb(150, 220, 150)", "ok_fg": "rgb(0, 150, 0)", "ok_beat_fg": "rgb(0, 80, 0)",
        "bad_bg": "red", "bad_fg": "rgb(190, 0, 0)",
        "warn_bg": "rgb(255, 220, 0)", "warn_fg": "rgb(170, 140, 0)",
        "warn2_bg": "rgb(255, 140, 0)", "warn2_fg": "rgb(255, 140, 0)",
        "change_bg": "rgb(190, 220, 255)", "change_fg": "rgb(0, 90, 200)",
        "idle_fg": "black",
        # tabela teleskopow: dawne kolory (inny kod niz reszta - ruch pomaranczowy, nie niebieski), patrz tab_* nizej
        "tab_ok": "rgb(0, 150, 0)", "tab_moving": "rgb(255, 160, 0)", "tab_error": "rgb(150, 0, 0)",
        # okno Mount: pola do wpisywania, tlo w ruchu, napis w ruchu (SLEWING - dawny pomaranczowy, zostaje)
        "input_bg": "white", "input_edit_bg": "rgb(234, 245, 249)", "moving_bg": "rgb(136, 142, 228)",
        "moving_fg": "rgb(204, 82, 0)", "warn_soft_bg": "rgb(240, 232, 151)",
        # okno Plan: wiersz zaznaczony / poprzednio zaznaczony, przygaszony tekst logu (cudze, planrunner)
        "row_sel_bg": "rgb(125, 195, 227)", "row_prev_bg": "rgb(230, 236, 240)", "dim_fg": "rgb(128, 128, 128)",
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
        "ok_bg": "rgb(30, 90, 30)", "ok_fg": "rgb(70, 150, 70)", "ok_beat_fg": "rgb(140, 220, 140)",
        "bad_bg": "rgb(120, 25, 25)", "bad_fg": "rgb(190, 60, 60)",
        "warn_bg": "rgb(110, 95, 20)", "warn_fg": "rgb(190, 165, 50)",
        "warn2_bg": "rgb(120, 65, 15)", "warn2_fg": "rgb(200, 120, 40)",
        "change_bg": "rgb(35, 60, 105)", "change_fg": "rgb(100, 140, 210)",
        "idle_fg": "rgb(170, 170, 160)",
        "tab_ok": "rgb(70, 150, 70)", "tab_moving": "rgb(200, 130, 40)", "tab_error": "rgb(190, 60, 60)",
        "input_bg": "rgb(62, 62, 66)", "input_edit_bg": "rgb(50, 62, 72)", "moving_bg": "rgb(50, 55, 110)",
        "moving_fg": "rgb(200, 120, 50)", "warn_soft_bg": "rgb(95, 88, 35)",
        "row_sel_bg": "rgb(55, 75, 105)", "row_prev_bg": "rgb(42, 46, 54)", "dim_fg": "rgb(110, 110, 105)",
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
        "ok_bg": "rgb(0, 200, 120)", "ok_fg": "rgb(60, 255, 160)", "ok_beat_fg": "rgb(190, 255, 220)",
        "bad_bg": "rgb(255, 40, 90)", "bad_fg": "rgb(255, 80, 120)",
        "warn_bg": "rgb(255, 230, 0)", "warn_fg": "rgb(255, 235, 60)",
        "warn2_bg": "rgb(255, 130, 0)", "warn2_fg": "rgb(255, 160, 40)",
        "change_bg": "rgb(0, 190, 255)", "change_fg": "rgb(80, 210, 255)",
        "idle_fg": "rgb(240, 230, 255)",
        "tab_ok": "rgb(60, 255, 160)", "tab_moving": "rgb(255, 170, 40)", "tab_error": "rgb(255, 80, 120)",
        "input_bg": "rgb(95, 55, 135)", "input_edit_bg": "rgb(110, 70, 160)", "moving_bg": "rgb(60, 120, 255)",
        "moving_fg": "rgb(255, 150, 40)", "warn_soft_bg": "rgb(230, 215, 90)",
        "row_sel_bg": "rgb(200, 60, 160)", "row_prev_bg": "rgb(90, 55, 125)", "dim_fg": "rgb(170, 150, 200)",
        "tab_icon_ok": "rgb(60, 255, 160)", "tab_icon_bad": "rgb(255, 80, 120)", "tab_icon_warn": "rgb(255, 140, 0)",
        "tab_icon_warn2": "rgb(255, 180, 60)",
    },
    # cosmic: granat i fiolet mglawicy, tekst jak swiatlo gwiazd; zorza / czerwony olbrzym / Slonce / goraca gwiazda
    "cosmic": {
        "window": "rgb(11, 14, 31)",
        "text": "rgb(200, 208, 255)",
        "field_bg": "rgb(24, 29, 58)",
        "field_fg": "rgb(200, 208, 255)",
        "muted_fg": "rgb(80, 88, 140)",
        "selection_bg": "rgb(91, 58, 140)",
        "ok_bg": "rgb(18, 92, 74)", "ok_fg": "rgb(61, 220, 151)", "ok_beat_fg": "rgb(160, 255, 210)",
        "bad_bg": "rgb(122, 24, 56)", "bad_fg": "rgb(255, 77, 109)",
        "warn_bg": "rgb(120, 96, 30)", "warn_fg": "rgb(255, 209, 102)",
        "warn2_bg": "rgb(128, 70, 26)", "warn2_fg": "rgb(255, 159, 67)",
        "change_bg": "rgb(28, 70, 120)", "change_fg": "rgb(76, 201, 240)",
        "idle_fg": "rgb(200, 208, 255)",
        "tab_ok": "rgb(61, 220, 151)", "tab_moving": "rgb(255, 159, 67)", "tab_error": "rgb(255, 77, 109)",
        "input_bg": "rgb(34, 38, 74)", "input_edit_bg": "rgb(34, 38, 74)", "moving_bg": "rgb(52, 40, 110)",
        "moving_fg": "rgb(255, 159, 67)", "warn_soft_bg": "rgb(120, 96, 30)",
        "row_sel_bg": "rgb(91, 58, 140)", "row_prev_bg": "rgb(30, 26, 60)", "dim_fg": "rgb(110, 118, 170)",
        "tab_icon_ok": "rgb(61, 220, 151)", "tab_icon_bad": "rgb(255, 77, 109)", "tab_icon_warn": "rgb(255, 159, 67)",
        "tab_icon_warn2": "rgb(255, 209, 102)",
    },
    # nord: spokojny, chlodny, arktyczny (paleta Nord)
    "nord": {
        "window": "rgb(46, 52, 64)",
        "text": "rgb(216, 222, 233)",
        "field_bg": "rgb(59, 66, 82)",
        "field_fg": "rgb(216, 222, 233)",
        "muted_fg": "rgb(97, 110, 136)",
        "selection_bg": "rgb(94, 129, 172)",
        "ok_bg": "rgb(84, 110, 74)", "ok_fg": "rgb(163, 190, 140)", "ok_beat_fg": "rgb(200, 230, 180)",
        "bad_bg": "rgb(130, 60, 68)", "bad_fg": "rgb(191, 97, 106)",
        "warn_bg": "rgb(140, 118, 72)", "warn_fg": "rgb(235, 203, 139)",
        "warn2_bg": "rgb(138, 86, 70)", "warn2_fg": "rgb(208, 135, 112)",
        "change_bg": "rgb(70, 96, 126)", "change_fg": "rgb(129, 161, 193)",
        "idle_fg": "rgb(216, 222, 233)",
        "tab_ok": "rgb(163, 190, 140)", "tab_moving": "rgb(208, 135, 112)", "tab_error": "rgb(191, 97, 106)",
        "input_bg": "rgb(67, 76, 94)", "input_edit_bg": "rgb(67, 76, 94)", "moving_bg": "rgb(76, 86, 140)",
        "moving_fg": "rgb(208, 135, 112)", "warn_soft_bg": "rgb(140, 118, 72)",
        "row_sel_bg": "rgb(94, 129, 172)", "row_prev_bg": "rgb(52, 58, 72)", "dim_fg": "rgb(140, 150, 170)",
        "tab_icon_ok": "rgb(163, 190, 140)", "tab_icon_bad": "rgb(191, 97, 106)", "tab_icon_warn": "rgb(208, 135, 112)",
        "tab_icon_warn2": "rgb(235, 203, 139)",
    },
    # dim: noc dla adaptacji wzroku - ciemniej niz night, wszystko przygaszone, kolory zostaja
    "dim": {
        "window": "rgb(10, 10, 11)",
        "text": "rgb(115, 112, 105)",
        "field_bg": "rgb(20, 20, 22)",
        "field_fg": "rgb(115, 112, 105)",
        "muted_fg": "rgb(55, 55, 55)",
        "selection_bg": "rgb(40, 44, 60)",
        "ok_bg": "rgb(22, 50, 22)", "ok_fg": "rgb(60, 120, 60)", "ok_beat_fg": "rgb(110, 170, 110)",
        "bad_bg": "rgb(70, 20, 20)", "bad_fg": "rgb(150, 50, 50)",
        "warn_bg": "rgb(65, 55, 18)", "warn_fg": "rgb(150, 130, 50)",
        "warn2_bg": "rgb(70, 40, 14)", "warn2_fg": "rgb(160, 95, 40)",
        "change_bg": "rgb(22, 36, 66)", "change_fg": "rgb(70, 100, 160)",
        "idle_fg": "rgb(115, 112, 105)",
        "tab_ok": "rgb(60, 120, 60)", "tab_moving": "rgb(160, 95, 40)", "tab_error": "rgb(150, 50, 50)",
        "input_bg": "rgb(26, 26, 28)", "input_edit_bg": "rgb(26, 26, 28)", "moving_bg": "rgb(30, 30, 70)",
        "moving_fg": "rgb(160, 95, 40)", "warn_soft_bg": "rgb(65, 55, 18)",
        "row_sel_bg": "rgb(40, 44, 60)", "row_prev_bg": "rgb(18, 18, 22)", "dim_fg": "rgb(80, 78, 74)",
        "tab_icon_ok": "rgb(60, 120, 60)", "tab_icon_bad": "rgb(150, 50, 50)", "tab_icon_warn": "rgb(160, 95, 40)",
        "tab_icon_warn2": "rgb(150, 130, 50)",
    },
    # paper: dzien - cieply kremowy papier, lagodniejszy dla oczu niz biel; kolory w stylu Material
    "paper": {
        "window": "rgb(244, 241, 234)",
        "text": "rgb(43, 43, 43)",
        "field_bg": "rgb(234, 229, 219)",
        "field_fg": "rgb(43, 43, 43)",
        "muted_fg": "rgb(160, 152, 140)",
        "selection_bg": "rgb(190, 210, 232)",
        "ok_bg": "rgb(200, 230, 201)", "ok_fg": "rgb(46, 125, 50)", "ok_beat_fg": "rgb(20, 80, 25)",
        "bad_bg": "rgb(255, 180, 185)", "bad_fg": "rgb(198, 40, 40)",
        "warn_bg": "rgb(255, 236, 150)", "warn_fg": "rgb(160, 120, 0)",
        "warn2_bg": "rgb(255, 205, 150)", "warn2_fg": "rgb(230, 119, 0)",
        "change_bg": "rgb(200, 222, 250)", "change_fg": "rgb(21, 101, 192)",
        "idle_fg": "rgb(43, 43, 43)",
        "tab_ok": "rgb(46, 125, 50)", "tab_moving": "rgb(230, 119, 0)", "tab_error": "rgb(198, 40, 40)",
        "input_bg": "rgb(253, 251, 246)", "input_edit_bg": "rgb(253, 251, 246)", "moving_bg": "rgb(170, 180, 240)",
        "moving_fg": "rgb(230, 119, 0)", "warn_soft_bg": "rgb(255, 236, 150)",
        "row_sel_bg": "rgb(190, 210, 232)", "row_prev_bg": "rgb(232, 226, 214)", "dim_fg": "rgb(120, 114, 104)",
        "tab_icon_ok": "rgb(46, 125, 50)", "tab_icon_bad": "rgb(198, 40, 40)", "tab_icon_warn": "rgb(230, 119, 0)",
        "tab_icon_warn2": "rgb(160, 120, 0)",
    },
    # clear sky: dzien - chlodna, czysta biel z niebieskawym odcieniem, wyrazne akcenty
    "clearsky": {
        "window": "rgb(245, 247, 250)",
        "text": "rgb(31, 41, 51)",
        "field_bg": "rgb(233, 237, 242)",
        "field_fg": "rgb(31, 41, 51)",
        "muted_fg": "rgb(150, 160, 175)",
        "selection_bg": "rgb(168, 199, 250)",
        "ok_bg": "rgb(190, 240, 200)", "ok_fg": "rgb(26, 127, 55)", "ok_beat_fg": "rgb(10, 80, 30)",
        "bad_bg": "rgb(255, 190, 190)", "bad_fg": "rgb(207, 34, 46)",
        "warn_bg": "rgb(255, 238, 150)", "warn_fg": "rgb(154, 103, 0)",
        "warn2_bg": "rgb(255, 210, 170)", "warn2_fg": "rgb(188, 76, 0)",
        "change_bg": "rgb(205, 232, 255)", "change_fg": "rgb(9, 105, 218)",
        "idle_fg": "rgb(31, 41, 51)",
        "tab_ok": "rgb(26, 127, 55)", "tab_moving": "rgb(188, 76, 0)", "tab_error": "rgb(207, 34, 46)",
        "input_bg": "white", "input_edit_bg": "white", "moving_bg": "rgb(160, 175, 245)",
        "moving_fg": "rgb(188, 76, 0)", "warn_soft_bg": "rgb(255, 238, 150)",
        "row_sel_bg": "rgb(168, 199, 250)", "row_prev_bg": "rgb(226, 232, 240)", "dim_fg": "rgb(110, 119, 129)",
        "tab_icon_ok": "rgb(26, 127, 55)", "tab_icon_bad": "rgb(207, 34, 46)", "tab_icon_warn": "rgb(188, 76, 0)",
        "tab_icon_warn2": "rgb(154, 103, 0)",
    },
}
TITLES = {"day": "Day", "paper": "Paper", "clearsky": "Clear sky", "night": "Night", "cosmic": "Cosmic", "nord": "Nord",
          "dim": "Dim", "funky": "Funky"}

# katalog obrazkow przelacznikow (w stylesheetach pisane jako ICONS/SwitchOn.png); nocne - Icons/make_night_icons.py
ICON_DIRS = {"day": "./Icons/", "night": "./Icons/night/", "funky": "./Icons/", "cosmic": "./Icons/night/",
             "nord": "./Icons/night/", "dim": "./Icons/night/", "paper": "./Icons/", "clearsky": "./Icons/"}

# tekst na tle *_bg: czarny na jasnych tlach dziennych, jasny na ciemnych nocnych
BG_TEXT = {"day": "black", "night": "rgb(210, 210, 200)", "funky": "black", "cosmic": "rgb(225, 230, 255)",
           "nord": "rgb(236, 239, 244)", "dim": "rgb(150, 145, 135)", "paper": "black", "clearsky": "black"}
# ciemne motywy w stylu nocy (paski paneli, panel optyki): wszystkie poza day i funky
DARK = {"night", "cosmic", "nord", "dim"}


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

    def css(self, fg=None, bg=None, extra=""):
        parts = []
        if fg is not None:
            parts.append(f"color: {self.c(fg)};")
        if bg is not None:
            if fg is None:      # tekst czytelny na tle
                parts.append(f"color: {self.c('field_fg')};")
            parts.append(f"background-color: {self.c(bg)};")
        if extra:
            parts.append(extra.replace("ICONS/", ICON_DIRS[self.name]))
        return " ".join(parts)

    def text_on(self, color):
        """czarny albo jasny tekst - czytelny na tle o kolorze color (QColor)"""
        luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        return "black" if luminance > 140 else "rgb(225, 225, 215)"

    def paint(self, widget, fg=None, bg=None, extra=""):
        """kolory widzetu wg kluczy motywu (fg - tekst, bg - tlo, extra - reszta stylesheetu). Klucze sa zapamietane
        na widzecie: zmiana motywu przemalowuje go sama, a powtorne malowanie tymi samymi kluczami nic nie kosztuje
        (petle odswiezajace co kilka sekund nie przeliczaja stylu)"""
        keys = (fg, bg, extra, self.name)
        css = self.css(fg, bg, extra)
        # porownujemy tez z biezacym stylesheetem - ktos mogl go zmienic zwyklym setStyleSheet
        if getattr(widget, "_theme_paint", None) == keys and widget.styleSheet() == css:
            return
        widget._theme_paint = keys
        widget.setStyleSheet(css)

    def repaint_all(self):
        for w in QApplication.allWidgets():
            keys = getattr(w, "_theme_paint", None)
            if keys is not None:
                self.paint(w, *keys[:3])

    @property
    def dark(self):
        return self.name in DARK

    @property
    def light(self):
        """jasne motywy w stylu dnia (day, paper, clear sky) - bez funky"""
        return self.name not in DARK and self.name != "funky"

    def hex(self, key):
        """kolor motywu jako #rrggbb (matplotlib, HTML)"""
        return self.qcolor(key).name()

    def style_figure(self, fig, axes=()):
        """wykres matplotlib w kolorach motywu: tlo, osie, opisy, ramka. Dzien - dawne biale tlo"""
        bg = self.hex("window") if self.c("window") else "white"
        text = self.hex("text")
        fig.set_facecolor(bg)
        fig.set_edgecolor(bg)
        for ax in axes:
            ax.set_facecolor(bg)
            ax.tick_params(colors=text, which="both")
            ax.xaxis.label.set_color(text)
            ax.yaxis.label.set_color(text)
            ax.title.set_color(text)
            for spine in ax.spines.values():
                spine.set_edgecolor(self.hex("muted_fg") if self.name != "day" else "black")

    def on_change(self, f):
        self._listeners.append(f)

    def set(self, name):
        if name not in THEMES:
            return
        self.name = name
        QSettings("OCA", "TOI").setValue("theme", name)
        self.apply_palette()
        self.repaint_all()
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
            # elementy wylaczone (np. SET przy M3 bez M3) - przygaszony tekst, inaczej wygladaja jak aktywne
            muted = self._css_to_qcolor(t["muted_fg"])
            for role in (QtGui.QPalette.ColorRole.Text, QtGui.QPalette.ColorRole.ButtonText,
                         QtGui.QPalette.ColorRole.WindowText):
                p.setColor(QtGui.QPalette.ColorGroup.Disabled, role, muted)
            # linie i ramki (QFrame HLine itd.) z tych rol - bez nich swieca na bialo
            for role, color in ((QtGui.QPalette.ColorRole.Light, window.lighter(170)),
                                (QtGui.QPalette.ColorRole.Midlight, window.lighter(140)),
                                (QtGui.QPalette.ColorRole.Mid, window.darker(120)),
                                (QtGui.QPalette.ColorRole.Dark, window.darker(150)),
                                (QtGui.QPalette.ColorRole.Shadow, window.darker(200))):
                p.setColor(role, color)
        # najpierw paleta, potem styl: zmiana stylu przemalowuje wszystkie okna (takze te z wlasnym stylesheetem,
        # ktore samej zmiany palety nie widza) - odwrotnie okna zostawaly o jeden motyw w tyle
        app.setPalette(p)
        app.setStyle(QStyleFactory.create(style))

theme = Theme()
