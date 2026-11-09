#!/usr/bin/env python3

import numpy as np

from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import QTextEdit, QGridLayout

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import logging
import numpy
from astropy.io import fits
from astropy.stats import mad_std
from astropy.visualization import ZScaleInterval
from pyaraucaria.ffs import FFS
from toi_lib import *
from base_window import BaseWindow
from toi_theme import theme

logger = logging.getLogger(__name__)

# wyswietlanie obrazu (menu ⚙ "FITS display", QSettings): "full" - pelna rozdzielczosc (jak dawniej), "binned" - do
# rysowania usrednione bloki do ~DISPLAY_TARGET pikseli (jk15 4096 -> 2048: 170 -> ~50 ms); FFS i nakladki zawsze na
# pelnym obrazie, wspolrzedne bez zmian
FITS_DISPLAY_MODES = {"full": "Full resolution", "binned": "Binned for display (faster)"}
FITS_DISPLAY_DEFAULT = "full"
DISPLAY_TARGET = 2048


# mapy kolorow obrazu (menu ⚙ "FITS colormap", QSettings): wielobarwne z rownomiernie rosnaca jasnoscia jak viridis -
# gradienty tla i slabe struktury widac wyrazniej niz na dwubarwnych; overlay - kolor nakladek (pointing, promienie
# dyfrakcyjne), czytelny na danej mapie; soft - stonowany kolor (kolka obiektow OFP, kreseczki wzoru katow gwiazd), szary
# na podstawowej mapie, na innych dobrany tak, by byl widoczny, ale nie dominowal
FITS_CMAPS = {
    "viridis": ("Viridis (default)", "black", "lightgray"),
    "cividis": ("Cividis (colour-blind safe)", "black", "white"),
    "plasma": ("Plasma", "black", "lightgray"),
    "inferno": ("Inferno", "white", "silver"),
    "magma": ("Magma", "white", "silver"),
    "cubehelix": ("Cubehelix", "white", "silver"),
    "turbo": ("Turbo (strong contrast)", "black", "dimgray"),      # jasne tlo nieba - ciemny
    "gray": ("Gray", "yellow", "cyan"),       # nie czerwony - czerwone sa gwiazdy nasycone; nie szary - tlo szare
}
FITS_CMAP_DEFAULT = "viridis"

# kontrast obrazu (menu ⚙ "FITS scale", QSettings fits_scale), liniowo vmin-vmax z co 4. piksela. mad: mediana i mad_std
# to samo tlo (odporne na gwiazdy), zakres niesymetryczny, bo gwiazdy sa tylko powyzej tla; std (dawne): jasne gwiazdy
# podbijaja std - obraz plaski, slabe gwiazdy niewidoczne; zscale - jak DS9 / IRAF. Porownanie 2026-11-09: mad i zscale
# podobne, mad z ciemniejszym tlem; median +- 1 mad za waskie (sam szum)
FITS_SCALES = {
    "mad": "Median -2 / +10 MAD (default)",
    "zscale": "ZScale",
    "std": "Mean +- std (old)",
}
FITS_SCALE_DEFAULT = "mad"


def fits_scale():
    name = str(QtCore.QSettings("OCA", "TOI").value("fits_scale", FITS_SCALE_DEFAULT))
    return name if name in FITS_SCALES else FITS_SCALE_DEFAULT


def image_limits(sample, mode):
    """vmin, vmax obrazu dla trybu z FITS_SCALES (sample - np. co 4. piksel)."""
    sample = numpy.asarray(sample, dtype=float)
    sample = sample[numpy.isfinite(sample)]
    if sample.size == 0:
        return 0.0, 1.0
    if mode == "zscale":
        return tuple(float(v) for v in ZScaleInterval().get_limits(sample))
    if mode == "mad":
        med, sig = float(numpy.median(sample)), float(mad_std(sample))
        if sig > 0:
            return med - 2 * sig, med + 10 * sig
    mean, std = float(numpy.mean(sample)), float(numpy.std(sample))     # std, a dla mad przy zerowym MAD
    return mean - std, mean + std


def fits_soft_color():
    # stonowany kolor nakladek dla biezacej mapy kolorow (kolka OFP, kreseczki wzoru katow)
    return FITS_CMAPS[fits_cmap()][2]


def fits_cmap():
    name = str(QtCore.QSettings("OCA", "TOI").value("fits_cmap", FITS_CMAP_DEFAULT))
    return name if name in FITS_CMAPS else FITS_CMAP_DEFAULT


def fits_display_mode():
    mode = str(QtCore.QSettings("OCA", "TOI").value("fits_display", FITS_DISPLAY_DEFAULT))
    return mode if mode in FITS_DISPLAY_MODES else FITS_DISPLAY_DEFAULT


# typy zdjec (IMAGETYP, downloader param image_type), dla ktorych liczymy FFS: OBJECT, SNAP, FOCUS
FFS_IMAGE_TYPES = ("science", "snap", "focusing")

# oznaczenia gwiazd zmierzonych przez FFS: czerwony pusty kwadrat - gwiazda odrzucona z FWHM klatki (shape poza oknem FFS
# calc_star_stats 0.55-0.95: < 0.55 paczki, slabe detekcje; > 0.95 kosmik w gwiezdzie); pozostale bez znacznika (pomaranczowe
# "podejrzane" - shape 0.82-0.95, e > 0.25 - zarzucone 2026-11-09). Nasycone - male czerwone kolka.
STAR_SHAPE_WINDOW = (0.55, 0.95)
STAR_REJECTED_COLOR = "red"
SATURATED_STAR_COLOR = "red"
OFP_TARGET_ALPHA = 0.85       # kolka obiektow OFP (targets); 0.45 bylo slabo widac na ciemnym tle (mediana/MAD)
# wzor katow wydluzen gwiazd (FFS calc_star_field_stats, psf_pattern; kolor - fits_soft_color()): kreseczki przez gwiazdy wzdluz osi dluzszej,
# dlugosc ramion = eliptycznosc x PATTERN_WHISKER_SCALE x dluzszy bok obrazu (e = 0.1 -> 2 % boku). Kreseczki tylko
# dla wzoru o sile >= PATTERN_MIN_STRENGTH (jak prog czerwonej eliptycznosci): test FFS mowi tylko, ze wzor nie jest
# przypadkowy - przy 30-50 jasnych gwiazdach istotne jest juz wspolne wydluzenie ~0.05 (na prawie kazdej klatce)
PATTERN_WHISKER_SCALE = 0.2
PATTERN_MIN_STRENGTH = 0.15
# ostrzezenie o rozmazanych gwiazdach (slady: prowadzenie, skok montazu) - mediana eliptycznosci zmierzonych gwiazd
# >= TRAILED_E_MIN. Dlugie slady (dluzsze niz wycinek pomiaru FFS, +-15 px) sa mierzone w kawalkach i wzor katow czesto
# nie wychodzi (zb08 snap 2026-11-09: e 0.51, slady ~60-70 px, psf_pattern none) - to ostrzezenie i tak sie pojawi
TRAILED_E_MIN = 0.4
# przerwa na gwiazde w srodku kreseczki: promien = PATTERN_GAP_FWHM x FWHM gwiazdy, co najmniej PATTERN_GAP_MIN boku
PATTERN_GAP_FWHM = 3.0
PATTERN_GAP_MIN = 0.008


def fits_show_trails(default=True):
    # linie satelitow z FFS na obrazie (menu ⚙ "FITS display", QSettings); default - toi.show_trails z configu
    return bool(QtCore.QSettings("OCA", "TOI").value("fits_show_trails", default, type=bool))


def fits_show_saturated(default=True):
    # czerwone kolka gwiazd nasyconych (menu ⚙ "FITS display", QSettings); default - toi.show_sat_stars z configu
    return bool(QtCore.QSettings("OCA", "TOI").value("fits_show_saturated", default, type=bool))


def fits_show_pattern():
    # kreseczki wzoru katow gwiazd i jego srodek (menu ⚙ "FITS display", QSettings); linia w panelu zostaje
    return bool(QtCore.QSettings("OCA", "TOI").value("fits_show_pattern", True, type=bool))


def fits_show_star_shapes():
    # markery shape gwiazd (za duzy / za maly) na obrazie (menu ⚙ "FITS display", QSettings); licznik w panelu zostaje
    return bool(QtCore.QSettings("OCA", "TOI").value("fits_show_star_shapes", True, type=bool))


def display_binning(shape, mode):
    if mode != "binned" or len(shape) != 2:
        return 1
    return max(1, max(shape) // DISPLAY_TARGET)     # jk15 4108 -> 2 (2054 px), 2048 -> 1 (bez zmian)


def bin_image(image, factor):
    """srednia z blokow factor x factor (ostatnie niepelne wiersze / kolumny odpadaja); gwiazdy nie znikaja jak przy
    braniu co n-tego piksela"""
    if factor <= 1:
        return image
    h, w = (image.shape[0] // factor) * factor, (image.shape[1] // factor) * factor
    return image[:h, :w].reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3), dtype=numpy.float32)


def read_fits_image(path, mode):
    """w watku (asyncio.to_thread): czytanie z NFS trwa (jk15 67 MB - ok. 3 s po wifi) - GUI nie moze na nie czekac.
    Zwraca (obraz, obraz do wyswietlenia, binning); plik zamkniety"""
    with fits.open(path, memmap=False) as hdul:
        image = numpy.array(hdul[0].data)
    factor = display_binning(image.shape, mode)
    return image, bin_image(image, factor), factor


  # ######### Fits GUI #############

class FitsWindow(BaseWindow):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle('Fits')
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 1910, self.parent.obs_window_geometry[1], 1000, 700)
        self.mkUI()
        self.image=[]
        self.coo = []
        self.sat_coo = []
        self.fwhm_x = None
        self.fwhm_y = None
        self.ffs = None
        # FFS liczy w watku; nie czekamy na niego (wait() stawial GUI przy nowym obrazie i przy zmianie
        # teleskopu). Kazde zlecenie ma numer, wynik starszego niz biezacy jest wyrzucany
        self._ffs_token = 0
        self._ffs_jobs = []         # (QThread, worker) - referencje, dopoki watek nie skonczy
        self.load_token = 0         # odczyt pliku w watku (TOI.new_fits): nowszy obraz / zmiana teleskopu - wynik do kosza
        self.image_name = None      # nazwa pliku pokazywanego obrazu
        self.display = None         # obraz do rysowania (pelny albo zbinowany) i jego binning
        self.display_factor = 1
        self._overlays = []         # nakladki na obrazie (pointing, obiekty OFP, gwiazdy nasycone) - usuwane przed nowymi
        self._dirty = False         # schowany panel - rysujemy przy pokazaniu
        theme.on_change(self.apply_theme)

    def redraw(self):
        if not self.isVisible():
            self._dirty = True
            return
        self._dirty = False
        self.canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_dirty", False):     # mkUI pokazuje okno, zanim __init__ ustawi _dirty
            self.redraw()

    def set_scale(self, name):
        # zwykly slot (menu) - wyjatek nie moze wyjsc
        try:
            QtCore.QSettings("OCA", "TOI").setValue("fits_scale", name)
            if self.image is not None and numpy.ndim(self.image) == 2:
                self.plot_image()
                self.update_fits_data()     # plot_image czysci osie - nakladki od nowa
        except Exception as e:
            logger.warning(f'TOI FITS: scale: {e!r}')

    def set_cmap(self, name):
        QtCore.QSettings("OCA", "TOI").setValue("fits_cmap", name)
        if self.image is not None and numpy.ndim(self.image) == 2:
            self.plot_image()
            self.update_fits_data()     # nakladki w kolorze dla nowej mapy

    def set_show_trails(self, on):
        # zwykly slot (menu) - wyjatek nie moze wyjsc
        try:
            QtCore.QSettings("OCA", "TOI").setValue("fits_show_trails", bool(on))
            if self.image is not None and numpy.ndim(self.image) == 2:
                self.update_fits_data()     # nakladki od nowa: z liniami albo bez
        except Exception as e:
            logger.warning(f'TOI FITS: show trails: {e!r}')

    def set_show_saturated(self, on):
        # zwykly slot (menu) - wyjatek nie moze wyjsc
        try:
            QtCore.QSettings("OCA", "TOI").setValue("fits_show_saturated", bool(on))
            if self.image is not None and numpy.ndim(self.image) == 2:
                self.update_fits_data()     # nakladki od nowa: z nasyconymi albo bez
        except Exception as e:
            logger.warning(f'TOI FITS: show saturated: {e!r}')

    def set_show_pattern(self, on):
        # zwykly slot (menu) - wyjatek nie moze wyjsc
        try:
            QtCore.QSettings("OCA", "TOI").setValue("fits_show_pattern", bool(on))
            if self.image is not None and numpy.ndim(self.image) == 2:
                self.update_fits_data()     # nakladki od nowa: z kreseczkami albo bez
        except Exception as e:
            logger.warning(f'TOI FITS: show pattern: {e!r}')

    def set_show_star_shapes(self, on):
        # zwykly slot (menu) - wyjatek nie moze wyjsc
        try:
            QtCore.QSettings("OCA", "TOI").setValue("fits_show_star_shapes", bool(on))
            if self.image is not None and numpy.ndim(self.image) == 2:
                self.update_fits_data()     # nakladki od nowa: z kolkami albo bez
        except Exception as e:
            logger.warning(f'TOI FITS: show star shapes: {e!r}')

    def set_display_mode(self, mode):
        QtCore.QSettings("OCA", "TOI").setValue("fits_display", mode)
        if self.image is not None and numpy.ndim(self.image) == 2:
            self.display_factor = display_binning(numpy.shape(self.image), mode)
            self.display = bin_image(numpy.asarray(self.image), self.display_factor)
            self.plot_image()
            self.update_fits_data()

    def apply_theme(self):
        theme.style_figure(self.fig, [self.axes])
        theme.paint(self.stat_e, bg="field_bg")
        self.redraw()

    def cancel_ffs(self):
        """wynik liczonego FFS i wczytywany plik (np. poprzedniego teleskopu) nie zostana pokazane"""
        self._ffs_token += 1
        self.load_token += 1

    def clear(self):
        self.axes.clear()
        self.axes.axis("off")
        theme.style_figure(self.fig, [self.axes])     # tlo wokol obrazu wg motywu (clear() je zeruje)
        self._overlays = []
        self.redraw()
        self.stat_e.setText("")


    def plot_image(self):
        self.axes.clear()
        self.axes.axis("off")
        theme.style_figure(self.fig, [self.axes])     # tlo wokol obrazu wg motywu (clear() je zeruje)
        if self.image is not None and len(self.image)>0:

            # skala z co 4. piksela, mean i std raz (wczesniej po 2x z calego obrazu - kazde przelaczenie teleskopu
            # wczytuje ostatni obraz, py-spy 2026-11-05)
            sample = numpy.asarray(self.image)[::4, ::4] if numpy.ndim(self.image) == 2 else self.image
            vmin, vmax = image_limits(sample, fits_scale())       # kontrast wg ⚙ "FITS scale"

            display, f = self.display, self.display_factor
            if display is None or f <= 1:
                display, f = self.image, 1
            h, w = numpy.shape(display)[0] * f, numpy.shape(display)[1] * f
            # extent w pikselach pelnego obrazu - nakladki (OFP, FFS) trafiaja w to samo miejsce przy binningu
            self.axes.imshow(display, vmin=vmin, vmax=vmax, interpolation='none', resample=False, cmap=fits_cmap(),
                             extent=(-0.5, w - 0.5, h - 0.5, -0.5))
            # granice osi = obraz; nakladki (obiekty, pointing, gwiazdy) nie moga ich rozszerzyc - punkt z WCS
            # w milionach pikseli (snap bez rozwiazania) zmniejszal obraz do niewidocznej kropki
            self.axes.set_autoscale_on(False)

            self.redraw()

    def in_image(self, x, y):
        """Czy punkt (piksele) lezy na wyswietlanym obrazie."""
        try:
            h, w = numpy.shape(self.image)[:2]
            return 0 <= float(x) < w and 0 <= float(y) < h
        except (TypeError, ValueError):
            return False

    def updateImage(self, image, display=None, factor=1, name=None):
        self.image = image
        self.image_name = name      # plik pokazywanego obrazu - nakladki OFP tylko dla niego
        self.display, self.display_factor = display, factor
        self._overlays = []         # plot_image czysci osie

        self.ffs = None
        self.coo = []
        self.adu = []
        self.sat_coo = []
        self.fwhm_x = None
        self.fwhm_y = None

        self.plot_image()
        self.update_fits_data()
        self.calc_ffs()


    def calc_ffs(self):
        self.ffs = None
        self._ffs_token += 1        # poprzednie zlecenie (jesli jeszcze liczy) - wynik do kosza

        # statystyki gwiazd tylko dla OBJECT / SNAP / FOCUS (downloader image_type: science / snap / focusing);
        # flat / zero / dark bez FFS; brak danych downloadera -> liczymy jak dotad
        image_type = get_dic(self.parent.fits_downloader_data, "param", "image_type")
        if image_type and str(image_type).strip().lower() not in FFS_IMAGE_TYPES:
            return

        self.saturation = 45000
        if self.parent.active_tel == "jk15":
            self.saturation = 180000

        thread = QtCore.QThread()
        worker = FFS_Worker(self.image, saturation=self.saturation, token=self._ffs_token)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # obsluga zatrzymania
        worker.close_signal.connect(thread.quit)
        worker.close_signal.connect(worker.deleteLater)
        thread.finished.connect(self._ffs_finished)

        # robota
        worker.done_signal.connect(self.ffs_done)
        self._ffs_jobs.append((thread, worker))
        self.thread, self.ffs_worker = thread, worker
        thread.start()

    def _ffs_finished(self):
        # zwalniamy referencje skonczonych watkow (zniszczenie dzialajacego QThread zamyka proces)
        self._ffs_jobs = [(t, w) for t, w in self._ffs_jobs if not t.isFinished()]

    def ffs_done(self, val, token):
        # zwykly slot Qt (z watku FFS) - wyjatek stad zamknalby cale TOI
        if token != self._ffs_token:
            return      # wynik dla starszego obrazu albo poprzedniego teleskopu
        try:
            if val is None:
                return
            self.ffs = val
            if len(self.ffs.coo) > 1:
                self.coo = self.ffs.coo
                self.adu = self.ffs.adu
                maska1 = numpy.array(self.adu) > self.saturation
                self.sat_coo = self.coo[maska1]
            self.update_fits_data()
        except Exception as e:
            logger.exception(f'TOI FITS: ffs result: {e}')


    def _draw_star_shapes(self, draw=True):
        """Czerwone puste kwadraty gwiazd zmierzonych przez FFS, ale odrzuconych z FWHM klatki (shape poza
        STAR_SHAPE_WINDOW); draw=False - tylko policz. Zwraca (uzyte, odrzucone) albo None (brak pomiaru)."""
        shape = getattr(self.ffs, "shape", None)
        coo = getattr(self.ffs, "coo", None)
        if shape is None or coo is None or len(shape) == 0:
            return None
        n = min(len(shape), len(coo))
        shape = numpy.asarray(shape, dtype=float)[:n]
        coo = numpy.asarray(coo).reshape(-1, 2)[:n]
        with numpy.errstate(invalid="ignore"):          # NaN - niezmierzone (nasycone, zle piksele) - bez znacznika
            measured = numpy.isfinite(shape)
            rejected = measured & ((shape <= STAR_SHAPE_WINDOW[0]) | (shape >= STAR_SHAPE_WINDOW[1]))
        if draw and rejected.any():
            # FFS liczy na obrazie transponowanym (FFS_Worker): coo (wiersz, kolumna) = (x, y) obrazu
            self._overlays += self.axes.plot(coo[rejected, 0], coo[rejected, 1], color=STAR_REJECTED_COLOR, marker="s",
                                             markersize=9, markerfacecolor="none", markeredgewidth=1.0, linestyle="")
        return int((measured & ~rejected).sum()), int(rejected.sum())

    def _trailed_text(self):
        """Ostrzezenie o rozmazanych gwiazdach (mediana e zmierzonych gwiazd >= TRAILED_E_MIN) albo None."""
        e = numpy.asarray(getattr(self.ffs, "ellipticity", []), dtype=float)
        t = numpy.asarray(getattr(self.ffs, "theta", []), dtype=float)
        n = min(len(e), len(t))
        m = numpy.isfinite(e[:n]) & numpy.isfinite(t[:n])
        if m.sum() < 3 or numpy.median(e[:n][m]) < TRAILED_E_MIN:
            return None
        e, t = e[:n][m], t[:n][m]
        z = numpy.sum(e * numpy.exp(2j * t)) / numpy.sum(e)        # wspolny kierunek (okres pi), |z| - zgodnosc katow
        red = theme.hex("bad_fg")
        txt = (f'<span style="color:{red};">WARNING</span>: trailed stars: e <span style="color:{red};"><b>'
               f'{numpy.median(e):.2f}</b></span>')
        if abs(z) >= 0.7:       # kierunek tylko przy zgodnych katach - dlugie slady mierzone w kawalkach daja rozrzut
            txt += f' @ {(90 - numpy.degrees(0.5 * numpy.angle(z))) % 180:.0f}&deg;'     # obraz transponowany (FFS_Worker)
        return txt

    def _pattern_mask(self, n):
        """Gwiazdy wzoru katow: maska z FFS (pattern_stars, calc_star_field_stats); bez niej (starszy FFS) jak tam:
        shape > 0.2 i e > 0.05 (okno FWHM 0.55-0.95 odrzucaloby gwiazdy rozmazane, o ktore tu chodzi)."""
        mask = getattr(self.ffs, "pattern_stars", None)
        if mask is not None and len(mask) >= n:
            return numpy.asarray(mask[:n], dtype=bool)
        e = numpy.asarray(self.ffs.ellipticity, dtype=float)[:n]
        sh = numpy.asarray(self.ffs.shape, dtype=float)[:n]
        with numpy.errstate(invalid="ignore"):
            return numpy.isfinite(e) & (e > 0.05) & (sh > 0.2)

    def _pattern_strength(self):
        """Sila wzoru katow (eliptycznosc wzoru): linear - wspolne wydluzenie psf_e_mean; radial / tangential -
        S x srednia e gwiazd wzoru (_pattern_mask). NaN - brak wzoru."""
        st = self.ffs.stats["frame"]
        pattern = st.get("psf_pattern")
        if pattern == "linear":
            return float(st.get("psf_e_mean", numpy.nan))
        if pattern in ("radial", "tangential"):
            e = numpy.asarray(getattr(self.ffs, "ellipticity", []), dtype=float)
            m = self._pattern_mask(len(e))
            return float(st["psf_pattern_s"] * numpy.mean(e[m])) if m.any() else numpy.nan
        return numpy.nan

    def _pattern_text(self):
        """Linia panelu o wzorze katow gwiazd (FFS psf_pattern) albo None (brak statystyk pola). Wzor slabszy niz
        PATTERN_MIN_STRENGTH (bez kreseczek) - szary z dopiskiem weak."""
        st = self.ffs.stats["frame"]
        pattern = st.get("psf_pattern")
        if pattern is None:
            return None
        if pattern == "linear":
            # kat z obrazu transponowanego (FFS_Worker): w obrazie 90 - theta, od osi x
            ang = (90 - numpy.degrees(st["psf_theta_mean"])) % 180
            txt = f'<b>linear</b> e {st["psf_e_mean"]:.2f} @ {ang:.0f}&deg;'
        elif pattern in ("radial", "tangential"):
            txt = (f'<b>{pattern}</b> e {self._pattern_strength():.2f} '
                   f'(centre {st["psf_centre_y"]:.0f}, {st["psf_centre_x"]:.0f})')       # x <-> y: transpozycja
            if pattern == "tangential" and numpy.isfinite(st.get("psf_rot_deg", numpy.nan)):
                txt += f' rot {st["psf_rot_deg"]:.3f}&deg;'
        else:
            return "PSF pattern:  <i>none</i>"
        if not self._pattern_strength() >= PATTERN_MIN_STRENGTH:
            return f'PSF pattern:  <span style="color:{theme.hex("dim_fg")};">{txt} (weak)</span>'
        return "PSF pattern:  " + txt

    def _draw_pattern(self):
        """Kreseczki wzoru katow przez gwiazdy wzoru (_pattern_mask) i znacznik srodka wzoru."""
        st = self.ffs.stats["frame"]
        pattern = st.get("psf_pattern")
        if pattern not in ("linear", "radial", "tangential") or not self._pattern_strength() >= PATTERN_MIN_STRENGTH:
            return
        e = numpy.asarray(getattr(self.ffs, "ellipticity", []), dtype=float)
        t = numpy.asarray(getattr(self.ffs, "theta", []), dtype=float)
        sh = numpy.asarray(getattr(self.ffs, "shape", []), dtype=float)
        n = min(len(e), len(t), len(sh), len(self.ffs.coo))
        if n == 0:
            return
        coo = numpy.asarray(self.ffs.coo).reshape(-1, 2)[:n].astype(float)
        e, t, sh = e[:n], t[:n], sh[:n]
        m = self._pattern_mask(n) & numpy.isfinite(e) & numpy.isfinite(t)
        if not m.any():
            return
        h, w = numpy.shape(self.image)[:2]
        arm = 0.5 * e[m] * PATTERN_WHISKER_SCALE * max(h, w)          # dlugosc ramienia ~ eliptycznosc
        # przerwa na gwiazde: PATTERN_GAP_FWHM x FWHM gwiazdy, nie mniej niz PATTERN_GAP_MIN boku obrazu
        fw = numpy.asarray(getattr(self.ffs, "fwhm", numpy.full(n, numpy.nan)), dtype=float)[:n][m]
        gap = numpy.maximum(numpy.nan_to_num(PATTERN_GAP_FWHM * fw), PATTERN_GAP_MIN * max(h, w))
        # theta z obrazu transponowanego: kierunek (cos t, sin t) w (kolumna, wiersz) transpozycji = (sin t, cos t) w (x, y)
        ux, uy = numpy.sin(t[m]), numpy.cos(t[m])
        X, Y = coo[m, 0], coo[m, 1]
        nan = numpy.full_like(X, numpy.nan)
        a, b = gap, gap + arm                                       # dwa ramiona od przerwy na zewnatrz
        xs = numpy.column_stack([X - b * ux, X - a * ux, nan, X + a * ux, X + b * ux, nan]).ravel()
        ys = numpy.column_stack([Y - b * uy, Y - a * uy, nan, Y + a * uy, Y + b * uy, nan]).ravel()
        color = fits_soft_color()
        self._overlays += self.axes.plot(xs, ys, color=color, lw=1.2, alpha=0.9)
        if pattern in ("radial", "tangential"):
            cx, cy = st["psf_centre_y"], st["psf_centre_x"]          # x <-> y: transpozycja
            if not (numpy.isfinite(cx) and numpy.isfinite(cy)):
                return
            if self.in_image(cx, cy):
                self._overlays += self.axes.plot([cx], [cy], color=color, marker="x", markersize=18,
                                                 markeredgewidth=2, linestyle="")
            else:   # srodek poza kadrem - strzalka przy brzegu w jego strone
                x0, y0 = (w - 1) / 2, (h - 1) / 2
                vx, vy = cx - x0, cy - y0
                k = min(abs((w / 2 - 1) / vx) if vx else numpy.inf, abs((h / 2 - 1) / vy) if vy else numpy.inf)
                ex, ey = x0 + k * vx, y0 + k * vy                    # przeciecie z brzegiem kadru
                L = 0.08 * max(h, w) / numpy.hypot(vx, vy)
                self._overlays.append(self.axes.annotate(
                    "", xy=(ex, ey), xytext=(ex - L * vx, ey - L * vy),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2)))

    def update_fits_data(self):
        # wolane tez z ffs_done (zwykly slot) - wyjatek nie moze wyjsc
        try:
            self._update_fits_data()
        except Exception as e:
            logger.exception(f'TOI FITS: update_fits_data: {e}')

    def _update_fits_data(self):
        if self.parent.active_tel:
            ok = False
            fname = None
            self.ob_x = []
            self.ob_y = []
            self.pointing_x = None
            self.pointing_y = None
            exptime = "??"

            txt = ""
            txt2 = ""
            # nakladki z poprzedniego wywolania (kazda wiadomosc OFP i wynik FFS rysowaly je od nowa - dublowaly sie)
            for artist in self._overlays:
                try:
                    artist.remove()
                except (ValueError, AttributeError):
                    pass
            self._overlays = []
            tel = self.parent.active_tel      # gdy brak danych downloadera
            red = theme.hex("bad_fg")
            try:
                tel =  self.parent.fits_downloader_data["telescope_id"]
                date = type = self.parent.fits_downloader_data["param"]["date_obs"]
                obs_type = self.parent.fits_downloader_data["param"]["obs_type"]
                type = self.parent.fits_downloader_data["param"]["image_type"]
                name = self.parent.fits_downloader_data["param"]["target_name"]
                fname = self.parent.fits_downloader_data["param"]["raw_file_name"]
                filter = self.parent.fits_downloader_data["param"]["filter"]
                n = self.parent.fits_downloader_data["param"]["loop"]
                ndit = self.parent.fits_downloader_data["param"]["nloops"]
            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 1: {e}")


            try:
                if self.parent.fits_ofp_data:
                    ofp_name = self.parent.fits_ofp_data["raw"]["file_name"]
                    if fname:
                        if ofp_name == fname:
                            ok = True
                            alt = get_dic(self.parent.fits_ofp_data,"raw","header","ALT_TEL",default = None)
                            if alt:
                                alt = f'{float(alt):.0f}'
                            airmass = get_dic(self.parent.fits_ofp_data,"raw","header","AIRMASS",default = None)
                            if airmass:
                                airmass = f'{float(airmass):.1f}'
                            exptime = self.parent.fits_ofp_data["raw"]["header"]["EXPTIME"]
                            ccd_temp = get_dic(self.parent.fits_ofp_data,"raw","header","CCD-TEMP",default = None)
                            if ccd_temp:
                                ccd_temp = f'{float(ccd_temp):.0f}'
                            gain = get_dic(self.parent.fits_ofp_data,"raw","header","GAIN",default = None)
                            rm = get_dic(self.parent.fits_ofp_data,"raw","header","READ-MOD",default = None)
                            xbin = get_dic(self.parent.fits_ofp_data,"raw","header","XBINNING",default = None)
                            ybin = get_dic(self.parent.fits_ofp_data,"raw","header","YBINNING",default = None)
                            focus = get_dic(self.parent.fits_ofp_data,"raw","header","FOCUS",default = None)

            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 2: {e}")

            try:
                txt = txt + f" {date.split('T')[0]} <br>"
                txt = txt + f" {date.split('T')[1].split('.')[0]} <br>"
                txt = txt + f" {fname} <br>"
                txt = txt + f" <hr> <br>"
                txt = txt + f" OBJECT: <b>{name}</b> <br>"
                txt = txt + f" TYPE: <i>{type}</i> <i>{obs_type}</i> <br>"
                txt = txt + f" FILTER: <b>{filter}</b> {n}/{ndit} <br>"
                txt = txt + f" EXP: <b>{exptime}</b> s. <br>"
                txt = txt + f" <hr> <br>"
            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 3: {e}")

            try:

                # OFP opisuje konkretny plik; obraz czytany w tle moze byc jeszcze poprzedni (wiadomosc OFP o nowym
                # zdjeciu przychodzi przed koncem odczytu) - nakladki tylko na obrazie, ktorego dotycza
                ofp_file = self.parent.fits_ofp_data["raw"].get("file_name")
                if self.image_name is not None and ofp_file != self.image_name:
                    raise LookupError(f"OFP data for {ofp_file}, image shown {self.image_name} - overlays skipped")
                if "pointing_error" in self.parent.fits_ofp_data["raw"].keys():
                    self.pointing_x = self.parent.fits_ofp_data["raw"]["pointing_error"]["new_px_ra"]
                    self.pointing_y = self.parent.fits_ofp_data["raw"]["pointing_error"]["new_px_dec"]

                if "objects" in self.parent.fits_ofp_data["raw"].keys():
                    for k in self.parent.fits_ofp_data["raw"]["objects"].keys():
                        if "x_pix" not in self.parent.fits_ofp_data["raw"]["objects"][k].keys():
                            pass
                        elif self.in_image(self.parent.fits_ofp_data["raw"]["objects"][k]["x_pix"],
                                           self.parent.fits_ofp_data["raw"]["objects"][k]["y_pix"]):
                            # obiekty spoza kadru (in_frame: 0, czesto bzdurne x/y bez WCS) nie sa rysowane
                            self.ob_x.append(self.parent.fits_ofp_data["raw"]["objects"][k]["x_pix"])
                            self.ob_y.append(self.parent.fits_ofp_data["raw"]["objects"][k]["y_pix"])
                        if "saturation_max" in self.parent.fits_ofp_data['raw']['objects'][k].keys():
                            txt2 = txt2 + f"<i>{k}</i> max ADU: <b>{self.parent.fits_ofp_data['raw']['objects'][k]['saturation_max']:.0f}</b> <br>"
                if self.pointing_x and self.in_image(self.pointing_x, self.pointing_y):
                    overlay = FITS_CMAPS[fits_cmap()][1]
                    self._overlays += self.axes.plot(self.pointing_x, self.pointing_y, "+", color=overlay, markersize=20)
                if len(self.ob_x)>0:
                    # polprzezroczyste kolka - nie dominuja obrazka (bez podpisow - przy polach standardow sie zlewaly)
                    self.objects = self.axes.plot(self.ob_x, self.ob_y, color=fits_soft_color(), marker="o",
                                                  markersize=14, markerfacecolor="none", markeredgewidth=1.5,
                                                  alpha=OFP_TARGET_ALPHA, linestyle="")
                    self._overlays += self.objects

            except LookupError as e:
                logger.debug(f"TOI FITS: {e}")
            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 3a: {e}")


            if self.ffs:
                fwhm_arcsec = None

                fwhm = self.ffs.stats["frame"]["fwhm"]

                if (self.parent.nats_cfg.get(tel) or {}).get("pixel_scale"):
                    px = self.parent.nats_cfg[tel]["pixel_scale"]
                    fwhm_arcsec = fwhm * px

                ell = self.ffs.stats["frame"]["ellipticity"]
                shape = self.ffs.stats["frame"]["shape"]
                used = self.ffs.stats["frame"].get("used_stars")

                frame_min = self.ffs.stats["frame"]["min"]
                frame_max = self.ffs.stats["frame"]["max"]
                frame_mean = self.ffs.stats["frame"]["mean"]
                frame_median = self.ffs.stats["frame"]["median"]
                frame_rms = self.ffs.stats["frame"]["rms"]
                frame_q_sigma = self.ffs.stats["frame"]["q_sigma"]

                bkg_ampl = self.ffs.stats["frame"]["bkg_max_amplitude"]
                frame_ampl = self.ffs.stats["frame"]["bkg_frame_gradient"]

                # mediana 0 (pusta / dziwna klatka) - bez dzielenia
                if frame_median and abs(bkg_ampl/frame_median) > 0.1:
                    txt = txt + f'<span style="color:{red};">WARNING</span>: bkg amplitude: <span style="color:{red};"><b>{bkg_ampl:.0f}</b></span> <br>'
                if frame_median and abs(frame_ampl/frame_median) > 0.1:
                    txt = txt + f'<span style="color:{red};">WARNING</span>: frame gradient: <span style="color:{red};"><b>{frame_ampl:.0f}</b></span><br>'

                # linie z FFS (pyaraucaria mgorski_dev; z mastera brak): slady (satelity) na czerwono
                # z ostrzezeniem, promienie dyfrakcyjne nasyconych gwiazd cienko, bez ostrzezenia
                lines = getattr(self.ffs, "lines", None)
                n_trails = n_spikes = 0
                if lines is not None and len(lines):
                    spike = numpy.asarray(lines["spike"], dtype=bool) if "spike" in lines.colnames \
                        else numpy.zeros(len(lines), dtype=bool)
                    n_trails, n_spikes = int((~spike).sum()), int(spike.sum())
                    if fits_show_trails(self.parent.local_cfg["toi"].get("show_trails", True)):
                        overlay = FITS_CMAPS[fits_cmap()][1]
                        for row, is_spike in zip(lines, spike):
                            # FFS liczy na obrazie transponowanym (FFS_Worker): x linii = wiersz obrazu
                            xs, ys = [row["y0"], row["y1"]], [row["x0"], row["x1"]]
                            if is_spike:
                                self._overlays += self.axes.plot(xs, ys, color=overlay, lw=0.6, alpha=0.5)
                            else:
                                self._overlays += self.axes.plot(xs, ys, color="red", lw=1.0, alpha=0.8)
                if n_trails:
                    txt = txt + f'<span style="color:{red};">WARNING</span>: satellite trail(s): <span style="color:{red};"><b>{n_trails}</b></span><br>'
                trailed = self._trailed_text()
                if trailed:
                    txt = txt + trailed + "<br>"

                if fwhm is None or not numpy.isfinite(fwhm):      # za malo gwiazd z dobrym shape
                    txt = txt + f'FWHM:  <span style="color:{red};"><b>--</b></span> (too few good stars)'
                elif fwhm_arcsec:
                    if fwhm_arcsec > 2.3:
                        txt = txt + f'FWHM:  <span style="color:{red};"><b>{fwhm:.1f}</b></span> px'
                        if fwhm_arcsec:
                            txt = txt + f'&nbsp; &nbsp; (<span style="color:{red};"><b>{fwhm_arcsec:.1f}</b></span> arcsec) '
                    else:
                        txt = txt + f'FWHM:  <b>{fwhm:.1f}</b> px'
                        if fwhm_arcsec:
                            txt = txt + f'&nbsp; &nbsp; <b>({fwhm_arcsec:.1f})</b> arcsec '
                else:
                    txt = txt + f'FWHM:  <b>{fwhm:.1f}</b> px'



                txt = txt + "<br>"

                num = lambda v: "--" if v is None or not numpy.isfinite(v) else f"{v:.2f}"   # None/NaN przy malej liczbie gwiazd
                if ell is not None and ell > 0.15:     # mediany 0.08-0.14; > 0.15 - wydluzenie ze wspolnym kierunkiem
                    txt = txt + f'ellipse:  <span style="color:{red};"><b>{ell:.2f}</b></span> <br>'
                else:
                    txt = txt + f'ellipse:  <b>{num(ell)}</b> <br>'

                txt = txt + f'shape:  <b>{num(shape)}</b> <br>'
                if used is not None:        # z ilu gwiazd jest FWHM (worker mierzy najwyzej 50)
                    if used < 5:
                        txt = txt + f'stars used:  <span style="color:{red};"><b>{used}</b></span>/50 <br>'
                    else:
                        txt = txt + f'stars used:  <b>{used}</b>/50 <br>'
                star_classes = self._draw_star_shapes(draw=fits_show_star_shapes())
                pattern_txt = self._pattern_text()
                if pattern_txt:
                    txt = txt + pattern_txt + " <br>"
                    if fits_show_pattern():
                        self._draw_pattern()
                if star_classes:        # zmierzone: w oknie shape / odrzucone (czerwone kwadraty)
                    n_ok, n_rej = star_classes
                    rej = f'<span style="color:{red};"><b>{n_rej}</b></span>' if n_rej else f"<i>{n_rej}</i>"
                    txt = txt + f"star shape:  <i>{n_ok}</i> ok / {rej} rejected <br>"
                if n_spikes:
                    txt = txt + f'diffraction spikes:  <i>{n_spikes}</i> <br>'
                txt = txt + "<br>"

                if len(self.coo)>0:
                    if len(self.sat_coo)>0 and fits_show_saturated(self.parent.local_cfg["toi"].get("show_sat_stars", True)):
                        x,y = zip(*self.sat_coo)
                        self._overlays += self.axes.plot(x, y, color=SATURATED_STAR_COLOR, marker="o", markersize=5,
                                                         markerfacecolor="none", markeredgewidth=1.0, linestyle="")
                    n_sat = len(self.sat_coo)
                    sat_txt = f'<span style="color:{red};"><b>{n_sat}</b></span>' if n_sat else f"<i>{n_sat}</i>"
                    txt = txt + f"detected/saturated stars:  <i>{len(self.coo)}</i>/{sat_txt} <br>"

                txt = txt + f'min/max ADU:  <i>{frame_min:.0f}</i>/<i>{frame_max:.0f}</i><br>'
                txt = txt + f'mean/median ADU:  <i>{frame_mean:.0f}</i>/<i>{frame_median:.0f}</i> <br>'
                txt = txt + f'rms/q68 ADU:  <i>{frame_rms:.0f}</i>/<i>{frame_q_sigma:.0f}</i> <br>'

                txt = txt + f" <hr> <br>"

            #
            #

            try:
                if ok:
                    txt = txt + " <b>OFP INFO</b>  <br>"
                    txt = txt + f"alt:  <b>{alt}</b> <br>"
                    txt = txt + f"airmass:  <b>{airmass}</b> <br>"
                    txt = txt + f"focus:  <b>{focus}</b> <br>"
                    txt = txt + f"CCD temp:  <b>{ccd_temp}</b> <br>"
                    txt = txt + f"gain:  <i>{gain}</i> <br>"
                    txt = txt + f"read mode:  <i>{rm}</i> <br>"
                    txt = txt + f"bin:  <i>{xbin}</i>x<i>{ybin}</i> <br>"
                    txt = txt + f" <hr> <br>"
                    txt = txt + " <b>OFP TARGETS</b>  <br>"
                    txt = txt + txt2
            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 5: {e}")

            self.stat_e.setHtml(txt)
            self.redraw()

    def updateUI(self):


        self.axes.clear()
        self.axes.axis("off")
        theme.style_figure(self.fig, [self.axes])     # tlo wokol obrazu wg motywu (clear() je zeruje)
        self._overlays = []
        self.redraw()
        self.stat_e.setText("")

        # nazwa i kolor teleskopu sa w pasku tytulu panelu (ObsGui.set_panel_telescope)
        if self.parent.active_tel:
            self.show()
            self.raise_()




    def mkUI(self):
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_axes([0, 0, 1, 1])
        self.axes.axis("off")


        grid = QGridLayout()

        grid.addWidget(self.canvas,0,0,2,1)

        self.stat_e=QTextEdit()
        self.stat_e.setReadOnly(True)
        theme.paint(self.stat_e, bg="field_bg")
        font=QtGui.QFont("Courier New",9)
        self.stat_e.setFont(font)
        self.stat_e.setMaximumWidth(300)
        grid.addWidget(self.stat_e,0,1,2,1)


        grid.setColumnStretch(0,1)
        grid.setColumnStretch(1, 0)

        self.setLayout(grid)

        self.axes.clear()
        theme.style_figure(self.fig, [self.axes])
        self.resize(400, 500)
        self.canvas.draw_idle()
        self.show()


class FFS_Worker(QtCore.QObject):
    close_signal = QtCore.pyqtSignal()
    done_signal = QtCore.pyqtSignal(object, int)      # wynik FFS (None przy bledzie), numer zlecenia

    def __init__(self, image, saturation = 45000, token=0):
        super(FFS_Worker, self).__init__()
        self.image = np.transpose(image)
        self.saturation = saturation
        self.token = token

    def run(self):
        # w watku QThread: wyjatek stad zamknalby cale TOI
        try:
            # autobin: obraz zbinowany do tla, linii i detekcji (2k -> bin 2, 4k -> bin 3), gwiazdy
            # mierzone na oryginale; pyaraucaria z mastera (<= 2.14.5) nie zna autobin - wtedy bez binowania
            try:
                self.ffs = FFS(self.image, saturation=self.saturation, autobin=True)
            except TypeError:
                self.ffs = FFS(self.image)
            self.ffs.saturation = self.saturation       # master: saturacja tylko jako atrybut
            # gwiazdy do FWHM klatki: mgorski_dev - okno shape 0.55-0.95 (< 3 dobrych -> NaN), master - clipping
            self.ffs.calc_frame_fwhm(threshold=10, fwhm=5, box=15, N_stars=50)
            self.ffs.sky_gradient(n_segments=7)
            try:        # wzor katow gwiazd (psf_pattern, ~0.1 s); master go nie zna, < 5 gwiazd -> ValueError
                self.ffs.calc_star_field_stats()
            except Exception as e:
                logger.debug(f'TOI FITS: star field stats: {e!r}')
        except Exception as e:
            logger.warning(f'TOI FITS: FFS failed: {e!r}')
            self.ffs = None
        self.done_signal.emit(self.ffs, self.token)
        self.close_signal.emit()
