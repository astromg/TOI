#!/usr/bin/env python3
from datetime import datetime

import ephem
from PyQtX.QtCore import Qt
from PyQtX.QtGui import QFont
from PyQtX import QtCore, QtGui
from PyQtX.QtWidgets import QWidget, QCheckBox, QTextEdit, QGridLayout, QLineEdit, QLabel, QComboBox, QPushButton

from matplotlib.figure import Figure
from matplotlib.dates import date2num
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import numpy
from ffs_lib.ffs import FFS
from base_window import BaseWindow
from pyaraucaria.date import datetime_to_julian, get_oca_jd


# ############### FOCUS ##########################

class ConditionsWindow(BaseWindow):
    def __init__(self, parent):
        super(ConditionsWindow, self).__init__()
        self.parent = parent
        self.set_initial_geometry(self.parent.obs_window_geometry[0] + 200, self.parent.obs_window_geometry[1]+100, 1300, 1000)
        self.mkUI()
        self.setWindowTitle('Conditions')

        self.fwhm = {t:[] for t in self.parent.fits_ffs_data.keys()}
        self.time = {t: [] for t in self.parent.fits_ffs_data.keys()}
        self.airmass = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.focus_time = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.update()

    def update(self):
        self.z0 = {t:[] for t in self.parent.fits_photo_z0_data.keys()}
        self.z0_time = {t: [] for t in self.parent.fits_photo_z0_data.keys()}

        self.fwhm = {t:[] for t in self.parent.fits_ffs_data.keys()}
        self.time = {t: [] for t in self.parent.fits_ffs_data.keys()}
        self.airmass = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.focus_time = {t: [] for t in self.parent.fits_ffs_data.keys()}

        self.ax1.clear()
        self.ax2.clear()

        if self.parent.jd:
            for t in self.parent.fits_ffs_data.keys():
                for x in self.parent.fits_ffs_data[t]:
                    try:
                        if x["raw"]["header"]["OBSTYPE"] != "focus":
                            if str(self.filter_e.text()) in x["raw"]["header"]["FILTER"]:
                                if "fwhm" in x["raw"].keys():
                                    airmass = float(x["raw"]["header"]["AIRMASS"])
                                    cond = True
                                    try:
                                        if len(str(self.airmass_e.text())) > 0:
                                            cond = float(self.airmass_e.text()) > airmass
                                    except ValueError:
                                        pass
                                    if cond:
                                        self.airmass[t].append(airmass)
                                        fwhm = (float(x["raw"]["fwhm"]["fwhm_x"])+float(x["raw"]["fwhm"]["fwhm_y"]))/2.
                                        fwhm = fwhm *  self.parent.nats_cfg[t]["pixel_scale"]
                                        self.fwhm[t].append(fwhm)
                                        time = float(x["raw"]["header"]["JD"])
                                        #time = datetime.fromisoformat(x["raw"]["header"]["DATE-OBS"])
                                        self.time[t].append(time)

                        if "OBSTYPE" in x["raw"]["header"].keys() and "NLOOPS" in x["raw"]["header"].keys() and "LOOP" in x["raw"]["header"].keys():
                            if x["raw"]["header"]["OBSTYPE"] == "focus" and float(x["raw"]["header"]["NLOOPS"]) == float(x["raw"]["header"]["LOOP"]):
                                self.focus_time[t].append(float(x["raw"]["header"]["JD"]))
                    except ValueError:
                        pass

            x0 = float(str(self.parent.jd).split(".")[0])+0.5
            x1 = x0 + 0.4

            for t in self.parent.fits_ffs_data.keys():
                x = self.time[t]
                y = self.fwhm[t]
                x = numpy.array(x)
                y = numpy.array(y)
                #x = date2num(self.time[t])
                mk = x < x0
                x = x[mk]
                y = y[mk]
                x = x + 1
                self.ax1.scatter(x, y, marker=".", color=self.parent.nats_cfg[t]['color'], alpha=0.05)

                x = self.time[t]
                y = self.fwhm[t]
                #self.ax1.plot_date(x,y,marker = ".",color=self.parent.nats_cfg[t]['color'],alpha=0.5)
                self.ax1.scatter(x, y, marker=".", color=self.parent.nats_cfg[t]['color'], alpha=1, s=100, label=t)

                ft = numpy.array(self.focus_time[t])
                mk = ft > x0
                ft = ft[mk]

                for focus_time in ft:
                    self.ax1.axvline(x=focus_time, color=self.parent.nats_cfg[t]['color'],alpha=0.8)

            xtics = []
            t =  ephem.Date(x0)
            while t < ephem.Date(x1):
                t = ephem.Date(t) + ephem.hour
                h = str(ephem.Date(t)).split()
                xtics.append( ephem.Date(h[0]+" "+h[1].split(":")[0]+":00:00"))
            xtics_labels = [str(x).split()[1].split(":")[0]+":"+str(x).split()[1].split(":")[1] for x in xtics]
            self.ax1.set_xticks(xtics)
            self.ax1.set_xticklabels(xtics_labels,rotation=45,minor=False)

            self.ax1.set_xlim(x0,x1)
            self.ax1.set_ylim(0,5)
            self.ax1.legend()
            #self.ax1.set_xlabel("UT")
            self.ax1.set_ylabel("fwhm [arcsec]")

            # zero point
            # {
            #     'filter': filter_,
            #     'zero_value': zero_value,
            #     'oca_jd': oca_jd,
            #     'mode': mode,
            # }
            # try:
            #     for t in self.parent.fits_photo_z0_data.keys():
            #         for x in self.parent.fits_photo_z0_data[t]:
            #             points = x["points"]
            #             for k in points.keys():
            #                 if k not in self.z0_time[t]:
            #                     self.z0[t].append(points[k]["zero_to_predict_value"])
            #                     self.z0_time[t].append(k)
            #
            #     for t in self.parent.fits_photo_z0_data.keys():
            #         x = [ ephem.julian_date(ephem.Date(str(q).replace("T"," ").replace("-","/"))) for q in self.z0_time[t]]
            #         y = self.z0[t]
            #
            #         x = numpy.array(x)
            #         y = numpy.array(y)
            #
            #         self.ax2.scatter(x, y, marker="o", color=self.parent.nats_cfg[t]['color'], alpha=1, s=100, label=t)
            #
            #         mk = x < x0
            #         x = x[mk]
            #         y = y[mk]
            #         x = x + 1
            #         self.ax2.scatter(x, y, marker="o", color=self.parent.nats_cfg[t]['color'], alpha=0.3)
            tim_ranges = self.parent.time_ranges()
            today_oca_jd = get_oca_jd(datetime_to_julian(tim_ranges['today']))
            yesterday_oca_jd = get_oca_jd(datetime_to_julian(tim_ranges['yesterday']))
            color = {'V': 'green', 'B': 'blue', 'Ic': 'red'}
            s = 30
            linewidths=2
            try:
                for t in self.parent.fits_photo_z0_data.keys():
                    val_td = []
                    filter_td = []
                    dat_td = []
                    val_yd = []
                    filter_yd = []
                    dat_yd = []
                    for x in self.parent.fits_photo_z0_data[t]:
                        if x["oca_jd"] >= today_oca_jd:
                            val_td.append(x["zero_value"])
                            filter_td.append(color[x["filter"]])
                            dat_td.append(x["oca_jd"] - numpy.floor(x["oca_jd"]))
                        if today_oca_jd > x["oca_jd"] >= yesterday_oca_jd:
                            val_yd.append(x["zero_value"])
                            filter_yd.append(color[x["filter"]])
                            dat_yd.append(x["oca_jd"] - numpy.floor(x["oca_jd"]))
                        else:
                            pass
                    self.ax2.scatter(
                        dat_td, val_td, edgecolor=filter_td, alpha=0.8,
                        facecolors="none", linewidths=linewidths, s=s
                    )
                    self.ax2.scatter(
                        dat_td, val_td, c=self.parent.nats_cfg[t]['color'], alpha=0.7, label=t, s=s
                    )
                    self.ax2.scatter(
                        dat_yd, val_yd, edgecolor=filter_td, alpha=0.3,
                        facecolors="none", linewidths=linewidths, s=s
                    )
                    self.ax2.scatter(
                        dat_yd, val_yd, c=self.parent.nats_cfg[t]['color'], alpha=0.2,
                        s=s
                    )
                        # for k in points.keys():
                        #     if k not in self.z0_time[t]:
                        #         self.z0[t].append(points[k]["zero_to_predict_value"])
                        #         self.z0_time[t].append(k)
                #
                # for t in self.parent.fits_photo_z0_data.keys():
                #     x = [ ephem.julian_date(ephem.Date(str(q).replace("T"," ").replace("-","/"))) for q in self.z0_time[t]]
                #     y = self.z0[t]
                #
                #     x = numpy.array(x)
                #     y = numpy.array(y)
                #
                #     self.ax2.scatter(x, y, marker="o", color=self.parent.nats_cfg[t]['color'], alpha=1, s=100, label=t)
                #
                #     mk = x < x0
                #     x = x[mk]
                #     y = y[mk]
                #     x = x + 1
                #     self.ax2.scatter(x, y, marker="o", color=self.parent.nats_cfg[t]['color'], alpha=0.3)

                # xtics = []
                # t =  ephem.Date(x0)
                # while t < ephem.Date(x1):
                #     t = ephem.Date(t) + ephem.hour
                #     h = str(ephem.Date(t)).split()
                #     xtics.append( ephem.Date(h[0]+" "+h[1].split(":")[0]+":00:00"))
                # xtics_labels = [str(x).split()[1].split(":")[0]+":"+str(x).split()[1].split(":")[1] for x in xtics]
                # self.ax2.set_xticks(xtics)
                # self.ax2.set_xticklabels(xtics_labels,rotation=45,minor=False)
                #
                # self.ax2.set_xlim(x0,x1)
                #self.ax1.set_ylim(0,5)
                self.ax2.legend()
                self.ax2.set_xlabel("UT")
                self.ax2.set_ylabel("zero point [mag]")

                self.fig.subplots_adjust(bottom=0.1,top=0.945,left=0.08,right=0.988)
                self.canvas.draw()

                #self.fig.tight_layout()
            except Exception as e:
                print(f'EXCEPTION plot_zero_point: {e}')


    # {'raw': {'min': 17467.0, 'max': 64450.0, 'mean': 19888.754051923752, 'median': 19896.0, 'std': 294.58467735596946,
    #          'file_folder': '/data/fits/wk06/raw/0704', 'file_name': 'wk06c_0704_50051.fits',
    #          'header': {'SIMPLE': True, 'BITPIX': 16, 'NAXIS': 2, 'NAXIS1': 2048, 'NAXIS2': 2048, 'OCASTD': '1.0.2',
    #                     'OBSERVAT': 'OCA', 'OBS-LAT': -24.59806, 'OBS-LONG': -70.19638, 'OBS-ELEV': 2817,
    #                     'ORIGIN': 'CAMK PAN', 'TELESCOP': 'wk06', 'DATE-OBS': '2025-01-29T00:00:44.001288',
    #                     'JD': 2460704.500509274, 'RA': 68.625, 'DEC': -45.656944, 'EQUINOX': '2000', 'RA_OBJ': '',
    #                     'DEC_OBJ': '', 'RA_TEL': 68.14736945815564, 'DEC_TEL': -45.217440960626945,
    #                     'ALT_TEL': 67.96738346025728, 'AZ_TEL': 161.72089070830447, 'AIRMASS': 1.0786216709860652,
    #                     'OBSMODE': '', 'FOCUS': 21223, 'ROTATOR': '', 'OBSERVER': '', 'IMAGETYP': 'flat',
    #                     'OBSTYPE': 'calib', 'OBJECT': 'BF04', 'OBS-PROG': '', 'NLOOPS': 7, 'LOOP': 7, 'FILTER': 'Ic',
    #                     'EXPTIME': 6.725452541363507, 'INSTRUME': 'DW936_BV', 'CCD-TEMP': -59.777000427246094,
    #                     'SET-TEMP': '', 'XBINNING': 1, 'YBINNING': 1, 'READ-MOD': 2, 'GAIN-MOD': 2, 'GAIN': 0.97,
    #                     'RON': 10.4, 'SUBRASTR': '', 'SCALE': 0.66, 'SATURATE': '', 'PIERSIDE': 1, 'FLAT_ERA': 1,
    #                     'ZERO_ERA': 0, 'DARK_ERA': 0, 'TEST': 0, 'CCD-BLCL': '', 'CCD-SCMP': '', 'CCD-PORT': '',
    #                     'CCD-VSSP': '', 'BZERO': 32768, 'COMMENT': ''}}, 'fits_id': 'wk06c_0704_50051'}

    def mkUI(self):

        grid = QGridLayout()
        w = 0
        self.filter_l = QLabel("Filter filter: ")
        self.filter_e = QLineEdit("")
        self.filter_e.textChanged.connect(self.update)

        self.airmass_l = QLabel("Filter airmass: ")
        self.airmass_e = QLineEdit("")
        self.airmass_e.textChanged.connect(self.update)

        grid.addWidget(self.filter_l, w, 0)
        grid.addWidget(self.filter_e, w, 1)
        grid.addWidget(self.airmass_l, w, 2)
        grid.addWidget(self.airmass_e, w, 3)

        w = w + 1

        self.fig = Figure((1, 1), linewidth=1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)

        grid.addWidget(self.canvas, w, 0, 1, 4)

        w = w + 1
        self.toolbar = NavigationToolbar(self.canvas,self)
        grid.addWidget(self.toolbar, w, 0, 1, 4)

        w = w + 1
        self.close_p = QPushButton('Close')
        self.close_p.clicked.connect(lambda: self.close())
        grid.addWidget(self.close_p, w, 3)


        self.setLayout(grid)

