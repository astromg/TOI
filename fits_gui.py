#!/usr/bin/env python3
import time

import numpy as np

from PyQtX.QtCore import Qt
from PyQtX.QtGui import QFont
from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS_old
from pyaraucaria.ffs import FFS
from toi_lib import *
from base_window import BaseWindow


  # ######### Fits GUI #############

class FitsWindow(BaseWindow):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle('Fits')
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 1910, self.parent.obs_window_geometry[1], 1000, 700)
        self.mkUI()
        self.colorbar = None
        self.image=[]
        self.coo = []
        self.sat_coo = []
        self.fwhm_x = None
        self.fwhm_y = None
        self.ffs = None


        #self.ffs_worker = None

    def clear(self):
        self.axes.clear()
        self.axes.axis("off")
        self.canvas.draw()
        self.stat_e.setText("")
        self.tel_e.setText("")
        self.tel_e.setStyleSheet(f"background-color: rgb(233, 233, 233);")


    def plot_image(self):
        self.axes.clear()
        self.axes.axis("off")
        if self.image is not None and len(self.image)>0:

            vmin = numpy.mean(self.image) - 1 * numpy.std(self.image)
            vmax = numpy.mean(self.image) + 1 * numpy.std(self.image)

            im = self.axes.imshow(self.image, vmin=vmin, vmax=vmax, interpolation='none', resample=False)

            self.canvas.draw()
            self.show()

    def updateImage(self, image):
        self.image = image

        self.ffs = None
        self.coo = []
        self.adu = []
        self.sat_coo = []
        self.sat_adu = []
        self.ok_coo = []
        self.ok_adu = []
        self.fwhm_x = None
        self.fwhm_y = None

        self.plot_image()
        self.update_fits_data()
        self.calc_ffs()


    def calc_ffs(self):
        self.ffs = None

        try:
            self.thread.quit()
            self.thread.wait()
            self.ffs_worker.deleteLater()
        except AttributeError:
            pass
        except RuntimeError:
            pass

        self.saturation = 45000
        if self.parent.active_tel == "jk15":
            self.saturation = 180000

        self.thread = QtCore.QThread()
        self.ffs_worker = FFS_Worker(self.image,saturation = self.saturation)
        self.ffs_worker.moveToThread(self.thread)
        self.thread.started.connect(self.ffs_worker.run)

        # obsluga zatrzymania
        self.ffs_worker.close_signal.connect(self.thread.quit)
        self.ffs_worker.close_signal.connect(self.ffs_worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # robota
        self.ffs_worker.done_signal.connect(self.ffs_done)
        self.thread.start()

    def ffs_done(self,val):
        self.ffs = val
        if len(self.ffs.coo) > 1:
            self.coo = self.ffs.coo
            self.adu = self.ffs.adu
            maska1 = numpy.array(self.adu) > self.saturation
            self.sat_coo = self.coo[maska1]
            self.sat_adu = self.adu[maska1]
            maska2 = [not val for val in maska1]
            self.ok_coo = self.coo[maska2]
            self.ok_adu = self.adu[maska2]
        self.update_fits_data()


    def update_fits_data(self):
        if True:
            ok = False
            fname = None
            self.ob_x = []
            self.ob_y = []
            self.pointing_x = None
            self.pointing_y = None
            exptime = "??"

            txt = ""
            txt2 = ""
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
                print(f"TOI FITS EXCEPTION 1: {e}")

    #DUPA
            #try:
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

                        if "pointing_error" in self.parent.fits_ofp_data["raw"].keys():
                            #pointing_err_ra = self.parent.fits_ofp_data["raw"]["pointing_error"]["real_ra_diff"]
                            #pointing_err_dec = self.parent.fits_ofp_data["raw"]["pointing_error"]["dec_diff"]
                            self.pointing_x = self.parent.fits_ofp_data["raw"]["pointing_error"]["new_px_ra"]
                            self.pointing_y = self.parent.fits_ofp_data["raw"]["pointing_error"]["new_px_dec"]

                        if "objects" in self.parent.fits_ofp_data["raw"].keys():
                            for k in self.parent.fits_ofp_data["raw"]["objects"].keys():
                                if "x_pix" not in self.parent.fits_ofp_data["raw"]["objects"][k].keys():
                                    pass
                                else:
                                    self.ob_x.append(self.parent.fits_ofp_data["raw"]["objects"][k]["x_pix"])
                                    self.ob_y.append(self.parent.fits_ofp_data["raw"]["objects"][k]["y_pix"])
                                if "saturation_max" in self.parent.fits_ofp_data['raw']['objects'][k].keys():
                                    txt2 = txt2 + f"<i>{k}</i> max ADU: <b>{self.parent.fits_ofp_data['raw']['objects'][k]['saturation_max']:.0f}</b> <br>"
                        if self.pointing_x:
                            self.poining_center = self.axes.plot(self.pointing_x,self.pointing_x,"k+",markersize=20)
                        if len(self.ob_x)>0:
                            self.objects = self.axes.plot(self.ob_x, self.ob_y, color="black", marker="o", markersize="10", markerfacecolor="none",linestyle="")

            # except Exception as e:
            #     print(f"TOI FITS EXCEPTION 2: {e}")

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
                print(f"TOI FITS EXCEPTION 3: {e}")

            #try:
            if self.ffs:
                fwhm_arcsec = None

                fwhm = self.ffs.stats["frame"]["fwhm"]

                if self.parent.nats_cfg[tel]["pixel_scale"]:
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

                if abs(bkg_ampl/frame_median) > 0.1:
                    txt = txt + f'<span style="color:red;">WARNING</span>: bkg amplitude: <span style="color:red;"><b>{bkg_ampl:.0f}</b></span> <br>'
                if abs(frame_ampl/frame_median) > 0.1:
                    txt = txt + f'<span style="color:red;">WARNING</span>: frame gradient: <span style="color:red;"><b>{frame_ampl:.0f}</b></span><br>'

                if fwhm_arcsec:
                    if fwhm_arcsec > 2.3:
                        txt = txt + f'FWHM:  <span style="color:red;"><b>{fwhm:.1f}</b></span> px'
                        if fwhm_arcsec:
                            txt = txt + f'&nbsp; &nbsp; (<span style="color:red;"><b>{fwhm_arcsec:.1f}</b></span> arcsec) '
                    else:
                        txt = txt + f'FWHM:  <b>{fwhm:.1f}</b> px'
                        if fwhm_arcsec:
                            txt = txt + f'&nbsp; &nbsp; <b>({fwhm_arcsec:.1f})</b> arcsec '
                else:
                    txt = txt + f'FWHM:  <b>{fwhm:.1f}</b> px'



                txt = txt + "<br>"

                if ell:
                    if ell > 0.01:
                        txt = txt + f'ellipse:  <span style="color:red;"><b>{ell:.2f}</b></span> <br>'
                    else:
                        txt = txt + f'ellipse:  <b>{ell:.2f}</b> <br>'
                else:
                    txt = txt + f'ellipse:  <b>{ell:.2f}</b> <br>'

                txt = txt + f'ellipse:  <b>{ell:.2f}</b> <br>'
                txt = txt + f'shape:  <b>{shape:.2f}</b> <br>'
                txt = txt + f'cpe:  <b>{cpe:.2f}</b> <br>'
                txt = txt + f'ci:  <b>{ci:.2f}</b> <br>'
                txt = txt + "<br>"

                if len(self.coo)>0:
                    if True:
                        if len(self.sat_coo)>0 and self.parent.local_cfg["toi"]["show_sat_stars"]:
                            x,y = zip(*self.sat_coo)
                            self.axes.plot(x, y, color="red", marker="o", markersize="5", markerfacecolor="none",linestyle="")
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
                print(f"TOI FITS EXCEPTION 5: {e}")

            self.tel_e.setText(tel)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[tel]['color']};")
            self.stat_e.setHtml(txt)
        self.canvas.draw()
        self.raise_()

    def updateUI(self):

        #self.ffs_worker = None

        self.axes.clear()
        self.axes.axis("off")
        self.canvas.draw()
        self.stat_e.setText("")
        self.tel_e.setText("")
        self.tel_e.setStyleSheet(f"background-color: rgb(233, 233, 233);")

        if self.parent.active_tel:
            self.tel_e.setText(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont("Courier New",9)
            font.setBold(True)
            self.tel_e.setFont(font)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")

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

        self.tel_e = QLineEdit()
        self.tel_e.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setBold(True)
        self.tel_e.setFont(font)
        self.tel_e.setStyleSheet(f"background-color: rgb(233, 233, 233);")
        grid.addWidget(self.tel_e, 0, 1)

        self.stat_e=QTextEdit()
        self.stat_e.setReadOnly(True)
        self.stat_e.setStyleSheet("background-color: rgb(235,235,235);")
        font=QtGui.QFont("Courier New",9)
        self.stat_e.setFont(font)
        self.stat_e.setMaximumWidth(300)
        grid.addWidget(self.stat_e,1,1)


        grid.setColumnStretch(0,1)
        grid.setColumnStretch(1, 0)

        self.setLayout(grid)

        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw()
        self.show()


class FFS_Worker(QtCore.QObject):
    close_signal = QtCore.pyqtSignal()
    done_signal = QtCore.pyqtSignal(FFS)

    def __init__(self, image, saturation = 45000):
        super(FFS_Worker, self).__init__()
        self.image = np.transpose(image)
        self.saturation = saturation

    def run(self):
        self.ffs = FFS(self.image)
        self.ffs.saturation = self.saturation
        self.ffs.calc_frame_fwhm(threshold=10, fwhm=5, box=15, N_stars=50, clip=4)
        self.ffs.sky_gradient(n_segments=7)

        self.done_signal.emit(self.ffs)
        self.close_signal.emit()
