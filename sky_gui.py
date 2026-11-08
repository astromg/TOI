#!/usr/bin/env python3

# ----------------
# 01.08.2022
# Marek Gorski
# ----------------

import logging

from PyQtX.QtCore import Qt
from PyQtX import QtGui, QtCore
from PyQtX.QtGui import QFont
from PyQtX.QtWidgets import QWidget, QLabel, QTextEdit, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, \
    QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pyaraucaria.coordinates import *
from toi_lib import *
from base_window import BaseWindow
from toi_theme import theme

logger = logging.getLogger(__name__)



class SkyGui(BaseWindow):
    def __init__(self, parent):
        super(SkyGui, self).__init__()
        self.parent = parent
        self.set_initial_geometry(self.parent.obs_window_geometry[0]+910,self.parent.obs_window_geometry[1],500,500)

        self.skyView = None
        self.updateUI()
        self.show()
        self.raise_()
        theme.on_change(self.on_theme)      # raz na okno - SkyView powstaje od nowa przy kazdej zmianie teleskopu

    def on_theme(self):
        if self.skyView is not None:
            self.skyView.refresh(telescope=True)
        if self.parent.telescope:
            self.paint_tel()

    def paint_tel(self):
        # pole teleskopu w jego kolorze (z configu TIC), tekst czytelny na nim
        color = QtGui.QColor(self.parent.nats_cfg[self.parent.active_tel]['color'] or "#cdd2dc")
        theme.paint(self.tel_e, extra=f"background-color: {color.name()}; color: {theme.text_on(color)};")

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
            self.layout.addWidget(self.user_e, w, 0, 1, 1)

            self.tel_e = QLineEdit(self.parent.active_tel)
            self.tel_e.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setBold(True)
            self.tel_e.setFont(font)
            self.paint_tel()
            self.layout.addWidget(self.tel_e, w, 1, 1, 1)

            self.user_p = QPushButton('Take Control')
            self.user_p.setFixedWidth(100)
            self.user_p.clicked.connect(self.parent.takeControl)
            self.layout.addWidget(self.user_p, w, 2, 1, 1)

            w = 1
            self.skyView = SkyView(self.parent)
            self.layout.addWidget(self.skyView, w, 0, 1, 3)
            # nowy wykres: od razu to, co nie zalezy od teleskopu (montaz i kopula nowego teleskopu przyjda
            # z subskrypcji - w zmiennych sa jeszcze wartosci poprzedniego)
            self.skyView.refresh(telescope=False)
            w = 2
            self.exit_p = QPushButton('EXIT')
            self.exit_p.clicked.connect(lambda: self.parent.obsGui.ask_quit())    # z pytaniem, jak krzyzyk
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
            theme.paint(self.info_e, bg="field_bg")
            with open("./Misc/changelog.txt", "r") as plik:
                txt = plik.read()
            self.info_e.setHtml(txt)
            font = QtGui.QFont("Courier New", 10)
            self.info_e.setFont(font)
            self.layout.addWidget(self.info_e, w, 0, 1, 1)
            w = 2
            self.exit_p = QPushButton('EXIT')
            self.exit_p.clicked.connect(lambda: self.parent.obsGui.ask_quit())
            self.layout.addWidget(self.exit_p, w, 0, 1, 1)

        self.setLayout(self.layout)
        del tmp

class SkyView(QWidget):
    REDRAW_MS = 500

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        # przerysowanie wykresu (matplotlib, ~50 ms) najwyzej co REDRAW_MS: zdarzenia montazu i kopuly (ra/dec/alt/az,
        # status, kopula) przychodza po kilka na sekunde, a kazde wolalo pelne canvas.draw() - glowny watek TOI byl
        # zajety w ~60% samym rysowaniem nieba (py-spy, 2026-11-05). Gdy panel niewidoczny (zakladka doku z tylu) -
        # nie rysujemy, dorysuje sie w showEvent
        self._redraw_dirty = False
        self._redraw_timer = QtCore.QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(self.REDRAW_MS)
        self._redraw_timer.timeout.connect(self._redraw_now)
        self.mkUI()
        self.canvas.mpl_connect('button_press_event', self.zaznaczenie)

        self.a = []
        self.h = []

        self.rmax = 110

        self.a = [10, 20, 30, 40, 50, 100, 40, 40, 70]
        self.h = [50, 50, 50, 50, 50, 30, 40, 40, 20]

        self.plan = []
        self.draw_base()

        self.dome_az = 0


    @staticmethod
    def c(key):
        """kolor motywu dla matplotlib (hex)"""
        return theme.qcolor(key).name()

    def refresh(self, telescope=True):
        """wszystko od nowa w kolorach motywu: tlo, siatka, almanac, plan, wiatr; telescope - takze montaz i kopula"""
        self.draw_base()
        steps = [self.updateAlmanac, self.updateRadar, lambda: self.updateWind(self.parent)]
        if telescope:
            steps += [self.updateMount, self.updateDome]
        for step in steps:
            try:
                step()
            except Exception as e:
                logger.warning(f'TOI: sky refresh: {e!r}')

    def draw_base(self):
        # dawniej update() - przeslanialo QWidget.update()
        self.axes.clear()
        self._alm = None        # artysci almanacu poszli z clear() - updateAlmanac utworzy ich od nowa
        self._alm_shown = None
        self.mount = []
        self.dome = None
        self.wind = None
        self.stars = []
        self.track = []
        bg = self.c("window") if theme.c("window") else "white"
        text = self.c("text")
        self.fig.set_facecolor(bg)
        self.fig.set_edgecolor(bg)      # bez tego biala ramka wokol wykresu w nocy
        self.axes.set_facecolor(bg)
        self.axes.tick_params(colors=text)
        self.axes.grid(color=self.c("muted_fg"))
        for spine in self.axes.spines.values():
            spine.set_edgecolor(self.c("muted_fg"))

        self.axes.set_theta_direction(-1)
        self.axes.set_theta_zero_location('N')
        self.axes.set_ylim([0, 360])
        self.axes.set_rlim([0, 30])
        self.axes.set_xticks([0, 2 * 3.14 * 90 / 360, 2 * 3.14 * 180 / 360, 2 * 3.14 * 270 / 360])
        self.axes.set_xticklabels(["N", "E", "S", "W"])
        self.axes.set_rmax(self.rmax)
        self.axes.set_rticks([20, 40, 60, 90])
        self.axes.set_yticklabels(["", "", "", ""])
        self.axes.bar(0, self.rmax - 90, width=2 * math.pi, bottom=90, color=text,
                      alpha=0.05)  # tutaj zmienia sie pasek ponizej horyzoontu

        self.redraw()

    # napisy almanacu: (x, y) w ukladzie wykresu, etykieta
    ALMANAC_TEXTS = (((130, -140), "Sunset"), ((115, -140), "Sunrise"), ((100, -140), "Sun Alt"),
                     ((-100, -140), "Moon"), ((-115, -140), "Moonrise"), ((-130, -140), "Moonset"))

    def updateAlmanac(self):
        """co 1 s z petli almanacu: zmienia tylko tekst i polozenie istniejacych elementow, a przerysowuje wykres
        tylko, gdy cos widocznego sie zmienilo (godziny co minute, wysokosc Slonca z dokladnoscia 0.1)"""
        alm = self.parent.almanac
        hm = lambda d: ":".join(str(d).split()[1].split(":")[:2])
        texts = [hm(alm["sunset"]), hm(alm["sunrise"]), f"{deg_to_decimal_deg(alm['sun_alt']):.1f}",
                 f"{alm['moon_phase']:.2f}", hm(alm["moonrise"]), hm(alm["moonset"])]
        rad = lambda deg: deg * 2 * math.pi / 360.
        sun = (round(rad(deg_to_decimal_deg(alm["sun_az"])), 3), round(90 - deg_to_decimal_deg(alm["sun_alt"]), 1))
        moon = (round(rad(deg_to_decimal_deg(alm["moon_az"])), 3), round(90 - deg_to_decimal_deg(alm["moon_alt"]), 1))
        try:
            next_ob = (rad(float(self.parent.mntGui.nextAz_e.text())), 90 - float(self.parent.mntGui.nextAlt_e.text()))
        except (ValueError, AttributeError):
            next_ob = None
        shown = (tuple(texts), sun, moon, next_ob)
        if shown == self._alm_shown:
            return
        self._alm_shown = shown

        if self._alm is None:
            text_color = self.c("text")
            self._alm = {
                "texts": [self.axes.text(*xy2rt(*xy), "", fontsize=9, color=text_color)
                          for xy, _ in self.ALMANAC_TEXTS],
                "sun": self.axes.plot([], [], "o", color=self.c("warn_bg"), alpha=0.7, markersize=10)[0],
                "moon": self.axes.plot([], [], "o", color=self.c("text"), alpha=0.7, markersize=8)[0],
                "next": self.axes.plot([], [], "x", color=self.c("change_fg"))[0],
            }
        for artist, (_, label), value in zip(self._alm["texts"], self.ALMANAC_TEXTS, texts):
            artist.set_text(f"{label}: {value}")
        self._alm["sun"].set_data([sun[0]], [sun[1]])
        self._alm["moon"].set_data([moon[0]], [moon[1]])
        self._alm["next"].set_data(*(([next_ob[0]], [next_ob[1]]) if next_ob else ([], [])))
        self.redraw()

    def updateRadar(self):
        # ### STARS ###
        try:
            for p in self.stars: p[0].remove()
        except Exception:
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
            az = [float(d["meta"]["az"]) for d in plan if "az" in d["meta"]]
            az = numpy.array(az)
            az = az * 2 * 3.14 / 360.

            alt = [float(d["meta"]["alt"]) for d in plan if "alt" in d["meta"]]
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
                az = float(star["meta"]["az"])
                az = az * 2 * 3.14 / 360.
                alt = 90 - float(star["meta"]["alt"])
                point = self.axes.plot(az, alt, color="b", marker="D", markersize="5", markerfacecolor="white",
                                       alpha=0.9)
                self.stars.append(point)
            except Exception:
                pass
            self.updateTrack()
        else:
            # pusty plan (Del All): bez toru obiektu
            try:
                for p in self.track: p[0].remove()
            except Exception:
                pass
            self.track = []
        self.redraw()       # zawsze - takze gdy gwiazdki tylko zniknely

    def updateTrack(self):
        try:
            for p in self.track: p[0].remove()
        except Exception:
            pass
        self.track = []


        try:
            star = self.plan_to_show[self.plan_i]
            if "plan_ut" in star["meta"] and "slotTime" in star["meta"] and "ra" in star["ob"]:
                ra = star["ob"]["ra"]
                dec = star["ob"]["dec"]
                plan_ut = star["meta"]["plan_ut"]
                slotTime = star["meta"]["slotTime"]
                t0 = ephem.Date(self.parent.ut)
                te = t0 + 6 * ephem.hour
                t0_star = ephem.Date(parse_plan_ut_str(plan_ut))
                te_star = t0_star + slotTime * ephem.second
                alt_l = []
                az_l = []
                obs_alt_l = []
                obs_az_l = []
                t = t0
                while t < te:
                    az, alt = RaDec2AltAz(self.parent.observatory, t, ra, dec)
                    alt = deg_to_decimal_deg(str(alt))
                    az = deg_to_decimal_deg(str(az))
                    az = az * 2 * 3.14 / 360.
                    alt = 90 - alt
                    if t0_star < t <  te_star:
                        obs_alt_l.append(alt)
                        obs_az_l.append(az)
                    else:
                        alt_l.append(alt)
                        az_l.append(az)
                    t = t + 1 * ephem.minute

                track = self.axes.plot(az_l, alt_l, color="dodgerblue", linestyle='-', alpha=0.5, linewidth=1)
                obs = self.axes.plot(obs_az_l, obs_alt_l, color="darkorange", linestyle='-', alpha=1, linewidth=2)
                self.track.append(track)
                self.track.append(obs)

        except Exception as e:
            print(f'{e}')

    def updateMount(self):
        try:
            for p in self.mount: p.remove()
        except:
            pass
        self.mount = []
        # montaz: w spoczynku czerwony, sledzi zielony, w ruchu pomaranczowy; otwarte lustro - srodek jasny
        color = self.c("bad_fg")
        if self.parent.mount_tracking:
            color = self.c("ok_fg")
        if self.parent.mount_slewing:
            color = self.c("tab_moving")
        facecolor = color
        if self.parent.cover_status == 3:
            facecolor = self.c("text") if theme.dark else "white"
        if self.parent.mount_alt is not None and self.parent.mount_az is not None:
            alt = 90 - self.parent.mount_alt
            az = self.parent.mount_az
            az = az * 2 * 3.14 / 360.
            self.mount = self.axes.plot(az, alt, color=color, marker="o", markersize="10", markerfacecolor=facecolor,
                                        alpha=0.7)

            self.redraw()

    def updateDome(self):
        try:
            self.dome.remove()
        except:
            pass
        self.dome = None
        # kopula: otwarta zielona, zamknieta czerwona, otwiera / zamyka sie pomaranczowa, nieznana niebieska
        color = {0: "ok_fg", 1: "bad_fg", 2: "tab_moving", 3: "tab_moving"}.get(self.parent.dome_shutterstatus,
                                                                               "change_fg")
        color = self.c(color)
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
        self.redraw()

    def updateWind(self, parent):
        try:
            self.wind.remove()
        except Exception:
            pass

        self.parent = parent
        try:
            wind = float(self.parent.telemetry_wind)
            wind_limit, wind_limit_pointing = self.parent.wind_limits(self.parent.active_tel)
            if wind < wind_limit_pointing:
                color = self.c("ok_fg")
            elif wind < wind_limit:
                color = self.c("tab_moving")
            else:
                color = self.c("bad_fg")
            theta = float(self.parent.telemetry_wind_direction)
            theta = theta * numpy.pi / 180.

            self.wind = self.axes.arrow(theta, 120, 0, -20, color=color, head_width=0.1, overhang=50,
                                        length_includes_head=True, head_starts_at_zero=True)

            self.redraw()
        except Exception as e:
            logger.warning(f"TOI: sky updateWind: {e!r}")

    # ======= Budowa okna ====================


    def redraw(self):
        if not self._redraw_timer.isActive():
            self._redraw_timer.start()

    def _redraw_now(self):
        if not self.isVisible():
            self._redraw_dirty = True
            return
        self._redraw_dirty = False
        self.canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        if self._redraw_dirty:
            self.redraw()

    def mkUI(self):
        self.fig = Figure((1.0, 1.0), linewidth=-1, dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111, polar=True)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.canvas)

        self.vbox = QVBoxLayout()
        self.vbox.addLayout(hbox1)
        self.setLayout(self.vbox)


        self.axes.clear()
        self.resize(400, 500)
        self.canvas.draw_idle()

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
                        if "alt" in self.plan[i]["meta"].keys() and "az" in self.plan[i]["meta"].keys():
                            h1 = 90. - float(alt)
                            a1 = 2 * math.pi * (float(az)) / 360.
                            h2 = 90. - float(self.plan[i]["meta"]["alt"])
                            a2 = 2 * math.pi * (float(self.plan[i]["meta"]["az"])) / 360.
                            delta = (h1 ** 2 + h2 ** 2 - 2 * h1 * h2 * math.cos(a1 - a2)) ** 0.5
                            if delta < przetrzymywacz:
                                ii = i
                                przetrzymywacz = delta
                    self.parent.planGui.i = ii
                    self.parent.planGui.update_table()


            elif event.button == 3:
                self.parent.mntGui.setAltAz_r.setChecked(True)
                self.parent.mntGui.nextAlt_e.setText(f"{alt:.3f}")
                self.parent.mntGui.nextAz_e.setText(f"{az:.3f}")

            self.updateRadar()
