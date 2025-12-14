#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------

from PyQtX.QtCore import Qt
from PyQtX import QtCore, QtGui
from PyQtX.QtGui import QFont
from PyQtX.QtWidgets import QMainWindow, QWidget, QLabel, QTextEdit, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, \
    QVBoxLayout, QTableWidget, QTableWidgetItem
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pyaraucaria.coordinates import *
from toi_lib import *



class SkyGui(QWidget):
    def __init__(self, parent):
        super(SkyGui, self).__init__()
        self.parent = parent
        #self.setStyleSheet("font-size: 11pt;")
        self.setGeometry(self.parent.obs_window_geometry[0]+910,self.parent.obs_window_geometry[1],500,500)

        self.updateUI()
        self.show()
        self.raise_()

    def updateUI(self):
        tmp = QWidget()
        try:
            tmp.setLayout(self.layout)
        except:
            pass

        self.layout = QGridLayout()
        if self.parent.telescope:
            w = 0

            self.user_e = QLineEdit("")
            self.user_e.setFixedWidth(180)
            self.user_e.setAlignment(Qt.AlignCenter)
            #font = QFont()
            #font.setBold(True)
            #self.tel_e.setFont(font)
            #self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")
            self.layout.addWidget(self.user_e, w, 0, 1, 1)

            self.tel_e = QLineEdit(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setBold(True)
            self.tel_e.setFont(font)
            self.tel_e.setStyleSheet(f"background-color: {self.parent.nats_cfg[self.parent.active_tel]['color']};")
            self.layout.addWidget(self.tel_e, w, 1, 1, 1)

            self.user_p = QPushButton('Take Control')
            self.user_p.setFixedWidth(100)
            self.user_p.clicked.connect(self.parent.takeControl)
            self.layout.addWidget(self.user_p, w, 2, 1, 1)

            w = 1
            self.skyView = SkyView(self.parent)
            self.layout.addWidget(self.skyView, w, 0, 1, 3)
            w = 2
            self.exit_p = QPushButton('EXIT')
            self.exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())
            self.layout.addWidget(self.exit_p, w, 0, 1, 3)
            self.layout.setColumnStretch(0, 0)
            self.layout.setColumnStretch(1, 1)
            self.layout.setColumnStretch(2, 0)
        else:
            self.skyView = None
            self.layout = QGridLayout()
            w = 0
            self.pic_l = QLabel(" ")
            self.pic_l.setPixmap(QtGui.QPixmap("./Icons/logo_oca2.png").scaled(300, 300))
            self.pic_l.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(self.pic_l, w, 0, 1, 1)

            w = 1
            self.info_e = QTextEdit()
            self.info_e.setReadOnly(True)
            self.info_e.setStyleSheet("background-color: rgb(235,235,235);")
            with open("./Misc/changelog.txt", "r") as plik:
                txt = plik.read()
            self.info_e.setHtml(txt)
            font = QtGui.QFont("Courier New", 10)
            self.info_e.setFont(font)
            self.layout.addWidget(self.info_e, w, 0, 1, 1)
            w = 2
            self.exit_p = QPushButton('EXIT')
            self.exit_p.clicked.connect(lambda: self.parent.app.closeAllWindows())
            self.layout.addWidget(self.exit_p, w, 0, 1, 1)

        self.setLayout(self.layout)
        del tmp

class SkyView(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.mkUI()
        cid = self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

        self.canSetNext = False

        self.tel_az = 5
        self.tel_alt = 90

        self.a = []
        self.h = []
        self.symbol = []

        self.silent_a = []
        self.silent_h = []
        self.silent_symbol = []

        self.rmax = 110
        self.marc_point = False

        self.a = [10, 20, 30, 40, 50, 100, 40, 40, 70]
        self.h = [50, 50, 50, 50, 50, 30, 40, 40, 20]
        self.symbol = ["b*", "b*", "b*", "b*", "b*", "ok", "or", "+r", ".r"]
        self.alpha = [0.8, 0.6, 0.5, 0.3, 0.3, 0.6, 0.3, 1, 1]

        self.log_a = [10, 20, 30]
        self.log_h = [30, 30, 30]
        self.log_s = ["k*", "k*", "k*"]
        self.log_alh = [0.5, 0.5, 0.5]

        self.update()

        self.dome_az = 0
        self.dome_color = "r"

        # self.updateDome()

    def update(self):
        self.axes.clear()

        self.axes.set_theta_direction(-1)
        self.axes.set_theta_zero_location('N')
        self.axes.set_ylim([0, 360])
        self.axes.set_rlim([0, 30])
        self.axes.set_xticks([0, 2 * 3.14 * 90 / 360, 2 * 3.14 * 180 / 360, 2 * 3.14 * 270 / 360])
        self.axes.set_xticklabels(["N", "E", "S", "W"])
        self.axes.set_rmax(self.rmax)
        self.axes.set_rticks([20, 40, 60, 90])
        self.axes.set_yticklabels(["", "", "", ""])
        self.axes.bar(0, self.rmax - 90, width=2 * math.pi, bottom=90, color='k',
                      alpha=0.05)  # tutaj zmienia sie pasek ponizej horyzoontu

        self.canvas.draw()
        self.show()

    def updateAlmanac(self):
        try:
            self.txt1.remove()
            self.txt2.remove()
            self.txt3.remove()
            self.txt4.remove()
            self.txt5.remove()
            self.txt6.remove()
            for p in self.sun: p.remove()
            for p in self.moon: p.remove()
            for p in self.nextOb: p.remove()
        except:
            pass
        sun_h = f"{deg_to_decimal_deg(self.parent.almanac['sun_alt']):.2f}"
        sunrise_tmp = str(self.parent.almanac["sunrise"]).split()[1]
        sunset_tmp = str(self.parent.almanac["sunset"]).split()[1]
        sunrise = sunrise_tmp.split(":")[0] + ":" + sunrise_tmp.split(":")[1]
        sunset = sunset_tmp.split(":")[0] + ":" + sunset_tmp.split(":")[1]

        moonrise_tmp = str(self.parent.almanac["moonrise"]).split()[1]
        moonset_tmp = str(self.parent.almanac["moonset"]).split()[1]
        moonrise = moonrise_tmp.split(":")[0] + ":" + moonrise_tmp.split(":")[1]
        moonset = moonset_tmp.split(":")[0] + ":" + moonset_tmp.split(":")[1]
        moon_phase = f"{self.parent.almanac['moon_phase']:.2f}"

        fi,r = xy2rt(130,-140)
        self.txt1 = self.axes.text(fi, r, f"Sunset: {sunset}", fontsize=9)

        fi, r = xy2rt(115, -140)
        self.txt2 = self.axes.text(fi, r, f"Sunrise: {sunrise}", fontsize=9)

        fi, r = xy2rt(100, -140)
        self.txt3 = self.axes.text(fi, r, f"Sun Alt: {sun_h}", fontsize=9)

        fi, r = xy2rt(-100, -140)
        self.txt4 = self.axes.text(fi, r, f"Moon: {moon_phase}", fontsize=9)

        fi, r = xy2rt(-115, -140)
        self.txt5 = self.axes.text(fi, r, f"Moonrise: {moonrise}", fontsize=9)

        fi,r = xy2rt(-130,-140)
        self.txt6 = self.axes.text(fi, r, f"Moonset: {moonset}", fontsize=9)

        try:
            self.sun = self.axes.plot(deg_to_decimal_deg(self.parent.almanac["sun_az"]) * 2 * 3.14 / 360.,
                                      90 - deg_to_decimal_deg(self.parent.almanac["sun_alt"]), "oy", alpha=0.7, markersize=10)
            self.moon = self.axes.plot(deg_to_decimal_deg(self.parent.almanac["moon_az"]) * 2 * 3.14 / 360.,
                                       90 - deg_to_decimal_deg(self.parent.almanac["moon_alt"]), "ok", alpha=0.7, markersize=8)
        except Exception as es:
            print(es)

        try:
            next_az = self.parent.mntGui.nextAz_e.text()
            next_alt = self.parent.mntGui.nextAlt_e.text()
            next_az = float(next_az) * 2 * 3.14 / 360.
            next_alt = 90 - float(next_alt)
            self.nextOb = self.axes.plot(next_az, next_alt, "xb")
        except:
            pass

        self.canvas.draw()
        self.show()

    def updateRadar(self):
        # ### MOUNT ###
        # try:
        #     for p in self.mount:
        #         p.remove()
        # except Exception as e:
        #     pass
        # color = "r"
        # if self.parent.mount_tracking:
        #     color = "g"
        # if self.parent.mount_slewing:
        #     color = "orange"
        # if self.parent.cover_status == 1:
        #     facecolor = "red"
        # elif self.parent.cover_status == 3:
        #     facecolor = "white"
        # else:
        #     facecolor = "red"
        # if self.parent.mount_alt:
        #     alt = 90 - self.parent.mount_alt
        #     az = self.parent.mount_az
        #     az = az * 2 * 3.14 / 360.
        #     self.mount = self.axes.plot(az, alt, color=color, marker="o", markersize="10", markerfacecolor="red",
        #                                 alpha=0.9)

        # ### STARS ###
        try:
            for p in self.stars: p[0].remove()
        except Exception as e:
            pass
        self.stars = []
        self.plan = []
        try:
            self.plan = self.parent.planGui.plan
            self.plan_i = int(self.parent.planGui.i)
            self.plan_next_i = int(self.parent.planGui.next_i)
        except AttributeError:
            pass
        if len(self.plan) > 0:
            self.plan_to_show = self.plan
            i = int(self.plan_next_i) - 1
            if i < 0: i = 0
            plan = self.plan_to_show[i:]
            az = [float(d["meta_az"]) for d in plan if "meta_az" in d]
            az = numpy.array(az)
            az = az * 2 * 3.14 / 360.

            alt = [float(d["meta_alt"]) for d in plan if "meta_alt" in d]
            alt = numpy.array(alt)
            alt = 90 - alt

            points = self.axes.plot(az, alt, color="dodgerblue", marker="*", alpha=0.1, linestyle="None")
            self.stars.append(points)

            try:
                points = self.axes.plot(az[0], alt[0], color="dodgerblue", marker="*", alpha=1, linestyle="None")
                self.stars.append(points)
            except IndexError:
                pass

            try:
                points = self.axes.plot(az[1], alt[1], color="dodgerblue", marker="*", alpha=0.7, linestyle="None")
                self.stars.append(points)
            except IndexError:
                pass

            try:
                points = self.axes.plot(az[2], alt[2], color="dodgerblue", marker="*", alpha=0.4, linestyle="None")
                self.stars.append(points)
            except IndexError:
                pass

            try:
                points = self.axes.plot(az[3], alt[3], color="dodgerblue", marker="*", alpha=0.2, linestyle="None")
                self.stars.append(points)
            except IndexError:
                pass

            try:
                star = self.plan_to_show[self.plan_i]
                az = float(star["meta_az"])
                az = az * 2 * 3.14 / 360.
                alt = 90 - float(star["meta_alt"])
                point = self.axes.plot(az, alt, color="b", marker="D", markersize="5", markerfacecolor="white",
                                       alpha=0.9)
                self.stars.append(point)
            except Exception as e:
                pass
            self.canvas.draw()
            self.show()

    def updateMount(self):
        try:
            for p in self.mount: p.remove()
        except:
            pass
        color = "r"
        facecolor = "r"
        if self.parent.mount_tracking:
            color = "g"
            facecolor = "g"
        if self.parent.mount_slewing:
            color = "orange"
            facecolor = "orange"
        if self.parent.cover_status == 3:
            facecolor = "white"
        if self.parent.mount_alt:
            alt = 90 - self.parent.mount_alt
            az = self.parent.mount_az
            az = az * 2 * 3.14 / 360.
            self.mount = self.axes.plot(az, alt, color=color, marker="o", markersize="10", markerfacecolor=facecolor,
                                        alpha=0.7)

            self.canvas.draw()
            self.show()

    def updateDome(self):
        try:
            self.dome.remove()
        except:
            pass
        if self.parent.dome_shutterstatus == 0:
            color = "g"
        elif self.parent.dome_shutterstatus == 1:
            color = "r"
        elif self.parent.dome_shutterstatus == 2:
            color = "orange"
        elif self.parent.dome_shutterstatus == 3:
            color = "orange"
        else:
            color = "b"
        ok = False
        try:
            float(self.parent.dome_az)
            ok = True
        except:
            ok = False
        if ok:
            dome_az = float(self.parent.dome_az) * (2 * math.pi) / 360.
            self.dome = self.axes.bar(dome_az, self.rmax - 90, width=30 * (2 * math.pi) / 360., bottom=90, color=color,
                                      alpha=0.5)
        self.canvas.draw()
        self.show()

    def updateWind(self, parent):
        try:
            self.wind.remove()
        except Exception as e:
            pass

        self.parent = parent
        try:
            wind = float(self.parent.telemetry_wind)
            if wind < float(self.parent.cfg_wind_limit_pointing):
                color = "g"
            elif wind < float(self.parent.cfg_wind_limit):
                color = "orange"
            else:
                color = "r"
            theta = float(self.parent.telemetry_wind_direction)
            theta = theta * numpy.pi / 180.

            self.wind = self.axes.arrow(theta, 120, 0, -20, color=color, head_width=0.1, overhang=50,
                                        length_includes_head=True, head_starts_at_zero=True)

            self.canvas.draw()
            self.show()
        except Exception as e:
            print("toi, updateWind: ", e)

    # ======= Budowa okna ====================

    def mkUI(self):
        # self.setWindowTitle('FC')
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111, polar=True)
        # self.axes.set_theta_zero_location('N')

        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.canvas)

        self.vbox = QVBoxLayout()
        self.vbox.addLayout(hbox1)
        self.setLayout(self.vbox)

        # self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw()
        # self.axes.grid(True)
        # self.axes.set_xticks([0,2*3.14*90/360,2*3.14*180/360,2*3.14*270/360])
        # self.axes.set_yticks([20,40,60,80])
        # self.axes.bar(0,self.rmax-90, width=2*math.pi,bottom=90,color='k',alpha=0.05)
        # self.axes.set_rmax(self.rmax)

    #  ============ Klikanie w punkciki ==========================

    def zaznaczenie(self, event):
        if event.xdata != None:
            az = 360. * (float(event.xdata) / (2 * 3.14))
            if az < 0: az = az + 360.
            alt = 90 - float(event.ydata)

            if event.button == 1:
                ii = 0
                if len(self.plan) > 0:
                    przetrzymywacz = 1000.
                    for i, tmp in enumerate(self.plan):
                        if "meta_alt" in self.plan[i].keys() and "meta_az" in self.plan[i].keys():
                            h1 = 90. - float(alt)
                            a1 = 2 * math.pi * (float(az)) / 360.
                            h2 = 90. - float(self.plan[i]["meta_alt"])
                            a2 = 2 * math.pi * (float(self.plan[i]["meta_az"])) / 360.
                            delta = (h1 ** 2 + h2 ** 2 - 2 * h1 * h2 * math.cos(a1 - a2)) ** 0.5
                            if delta < przetrzymywacz:
                                ii = i
                                przetrzymywacz = delta
                    self.parent.planGui.i = ii
                    self.parent.planGui.update_table()


            elif event.button == 3:
                if True:
                    self.parent.mntGui.setAltAz_r.setChecked(True)
                    self.parent.mntGui.nextAlt_e.setText(f"{alt:.3f}")
                    self.parent.mntGui.nextAz_e.setText(f"{az:.3f}")

            self.updateRadar()
