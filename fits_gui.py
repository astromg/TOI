#!/usr/bin/env python3

import numpy as np

from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import QTextEdit, QGridLayout

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import logging
import numpy
from astropy.io import fits
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


def fits_display_mode():
    mode = str(QtCore.QSettings("OCA", "TOI").value("fits_display", FITS_DISPLAY_DEFAULT))
    return mode if mode in FITS_DISPLAY_MODES else FITS_DISPLAY_DEFAULT


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
            mean, std = numpy.mean(sample), numpy.std(sample)
            vmin, vmax = mean - std, mean + std

            display, f = self.display, self.display_factor
            if display is None or f <= 1:
                display, f = self.image, 1
            h, w = numpy.shape(display)[0] * f, numpy.shape(display)[1] * f
            # extent w pikselach pelnego obrazu - nakladki (OFP, FFS) trafiaja w to samo miejsce przy binningu
            self.axes.imshow(display, vmin=vmin, vmax=vmax, interpolation='none', resample=False,
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
                    #pointing_err_ra = self.parent.fits_ofp_data["raw"]["pointing_error"]["real_ra_diff"]
                    #pointing_err_dec = self.parent.fits_ofp_data["raw"]["pointing_error"]["dec_diff"]
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
                    self._overlays += self.axes.plot(self.pointing_x,self.pointing_y,"k+",markersize=20)
                if len(self.ob_x)>0:
                    self.objects = self.axes.plot(self.ob_x, self.ob_y, color="black", marker="o", markersize="10", markerfacecolor="none",linestyle="")
                    self._overlays += self.objects

            except LookupError as e:
                logger.debug(f"TOI FITS: {e}")
            except Exception as e:
                logger.warning(f"TOI FITS EXCEPTION 3a: {e}")


            if True:
            #try:
                if self.ffs:
                    fwhm_arcsec = None

                    fwhm = self.ffs.stats["frame"]["fwhm"]

                    if (self.parent.nats_cfg.get(tel) or {}).get("pixel_scale"):
                        px = self.parent.nats_cfg[tel]["pixel_scale"]
                        fwhm_arcsec = fwhm * px

                    ell = self.ffs.stats["frame"]["ellipticity"]
                    shape = self.ffs.stats["frame"]["shape"]
                    cpe = self.ffs.stats["frame"]["cpe"]
                    ci = self.ffs.stats["frame"]["ci"]

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

                    if fwhm_arcsec:
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

                    num = lambda v: "--" if v is None else f"{v:.2f}"     # FFS daje None przy malej liczbie gwiazd
                    if ell is not None and ell > 0.1:
                        txt = txt + f'ellipse:  <span style="color:{red};"><b>{ell:.2f}</b></span> <br>'
                    else:
                        txt = txt + f'ellipse:  <b>{num(ell)}</b> <br>'

                    txt = txt + f'shape:  <b>{num(shape)}</b> <br>'
                    txt = txt + f'cpe:  <b>{num(cpe)}</b> <br>'
                    txt = txt + f'ci:  <b>{num(ci)}</b> <br>'
                    txt = txt + "<br>"

                    if len(self.coo)>0:
                        if True:
                            if len(self.sat_coo)>0 and self.parent.local_cfg["toi"]["show_sat_stars"]:
                                x,y = zip(*self.sat_coo)
                                self._overlays += self.axes.plot(x, y, color="red", marker="o", markersize="5", markerfacecolor="none",linestyle="")
                        txt = txt + f"detected/saturated stars:  <i>{len(self.coo)}</i>/<i>{len(self.sat_coo)}</i> <br>"

                    txt = txt + f'min/max ADU:  <i>{frame_min:.0f}</i>/<i>{frame_max:.0f}</i><br>'
                    txt = txt + f'mean/median ADU:  <i>{frame_mean:.0f}</i>/<i>{frame_median:.0f}</i> <br>'
                    txt = txt + f'rms/q68 ADU:  <i>{frame_rms:.0f}</i>/<i>{frame_q_sigma:.0f}</i> <br>'

                    txt = txt + f" <hr> <br>"

            # except Exception as e:
            #     print(f"TOI FITS EXCEPTION 4: {e}")
            #
            #
            # except Exception as e:
            #     print(f"TOI FITS EXCEPTION 4: {e}")

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

        #self.ffs_worker = None

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

        # self.violin_axes = self.fig.add_axes([0.82,0.0,0.18,1])
        # self.violin_axes.tick_params(axis='y', which='both', labelleft=False, labelright=True, direction='in')

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
            self.ffs = FFS(self.image)
            self.ffs.saturation = self.saturation
            self.ffs.calc_frame_fwhm(threshold=10, fwhm=5, box=15, N_stars=50, clip=4)
            self.ffs.sky_gradient(n_segments=7)
        except Exception as e:
            logger.warning(f'TOI FITS: FFS failed: {e!r}')
            self.ffs = None
        self.done_signal.emit(self.ffs, self.token)
        self.close_signal.emit()
