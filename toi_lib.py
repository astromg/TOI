#!/usr/bin/env python3
import logging

import datetime as _datetime   # z podkreslnikiem, zeby "from toi_lib import *" go nie eksportowal
import ephem
import numpy

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt

def ToiIcon(name,color,size=15):
    pixmap = QPixmap(size,size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    render = QSvgRenderer(f'./Icons/{name}.svg')
    render.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(),QColor(color))
    painter.end()

    return QIcon(pixmap)

def get_dic(d, *keys, default=None):
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return default
    return d



def xy2rt(x,y):
    x=float(x)
    y=float(y)
    r = numpy.sqrt(x**2+y**2)
    theta = numpy.arctan2(y,x)
    return(theta,r)

def parse_plan_ut_str(s):
    """Normalise a plan_ut date string to the legacy slash/space format
    expected by ephem (e.g. ``2026/4/21 02:20:40``).

    Accepts both the legacy format and ISO 8601 format
    (e.g. ``2026-04-21T02:20:40``).  Any other string is returned unchanged.
    """
    s = str(s)
    if 'T' in s and '-' in s:
        return s.replace('-', '/').replace('T', ' ')
    return s


def is_fits_ascii(txt):
    """Czy tekst moze isc do naglowka FITS: tylko drukowalne ASCII (znaki 32-126)."""
    return all(32 <= ord(c) <= 126 for c in str(txt))


def fits_ascii(txt):
    """Tekst bez polskich (i innych) znakow do naglowka FITS: Mirosław -> Miroslaw, Gałan -> Galan."""
    import unicodedata as _unicodedata
    txt = str(txt).replace("ł", "l").replace("Ł", "L")
    txt = _unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in txt if 32 <= ord(c) <= 126)


def wait_ut_sec(ut, t):
    """Ile sekund od chwili t (ephem.Date) do WAIT ut=HH:MM[:SS]; 0 jak ut juz minelo.

    Bierze wystapienie ut najblizsze t (+-12 h), wiec dziala przez polnoc UT:
    o 23:50 WAIT ut=00:30 czeka 40 min, a o 00:40 jest juz zrobiony.
    """
    h, m, s = ([float(x) for x in str(ut).strip().split(":")] + [0.0, 0.0])[:3]
    dt = ephem.Date(t).datetime()
    target = dt.replace(hour=0, minute=0, second=0, microsecond=0) + _datetime.timedelta(seconds=h * 3600 + m * 60 + s)
    diff = (target - dt).total_seconds()
    if diff > 43200:
        diff -= 86400
    elif diff < -43200:
        diff += 86400
    return max(diff, 0.0)


def seq_parser(seq):
    if "x" in seq and "(" in seq and ")" in seq:
        try:
            n = int(seq.split("x")[0])
            s = seq.split("x")[1].strip("(").strip(")")+","
            r = s*n
            r=r[:-1]
            return r
        except Exception as e:
            logging.getLogger(__name__).warning(f"seq_parser: wrong sequence {seq}: {e}")
    else:
        return seq

def seq_verification(seq,filter_list):
    ok = True
    err = ""
    parsed = seq_parser(seq)
    if parsed is None:          # zly zapis powtorzen, np. "ax(1/V/30)" - komunikat zamiast AttributeError
        return False, f"wrong sequence format {seq}"
    for x_seq in parsed.split(","):
        try:
            n,f,t = x_seq.split("/")
            try:
                n = int(n)
                if n<= 0 :
                    ok,err = False, f"N value should be grater than 0: {n}"
            except ValueError:
                ok,err = False, f"wrong N value {n}"
            if t != "a":
                try:
                    t = float(t)
                    if t< 0 :
                        ok,err = False, f"EXP value should be grater than 0: {n}"
                except ValueError:
                    ok,err = False, f"wrong EXP value {t}"
            if f not in filter_list:
                ok,err = False, f"filter {f} not in a filter list {filter_list}"
        except Exception as e:
            ok,err = False, f"wrong sequence format {x_seq}, {e}"
    return ok,err

def calc_slot_time(seq, overhed):
    slotTime = 10
    k = 1
    try:
        if "x(" in seq and ")" in seq:
            k = int(seq.split("x")[0])
            seq = seq.split("x(")[1].split(")")[0]
        for x_seq in seq.split(","):
            if "a" in x_seq:
                x_seq = x_seq.replace("/a", "/5")
            slotTime = slotTime + (float(x_seq.split("/")[0]) * (float(x_seq.split("/")[2]) + float(overhed)))
        slotTime = k * slotTime
    except:
        print(f"wrong seq {seq}")
    return slotTime


def readCatalog(plik):
    l = []
    with open(plik, "r") as f:
        for line in f:
            if len(line.strip()) > 0:
                if line.strip().split()[0] != "#":
                    l.append(line)
    return l


def Almanac(obs):
    site=ephem.Observer()
    site.date=ephem.now()
    site.lon=obs[1]
    site.lat=obs[0]
    site.elevation=float(obs[2])
    alm={}
    alm["ut"]=site.date
    alm["sid"]=site.sidereal_time()
    alm["jd"]=ephem.julian_date(site)
    alm["sunrise"]=site.next_rising(ephem.Sun())
    alm["sunset"]=site.next_setting(ephem.Sun())
    sun=ephem.Sun()
    sun.compute(site)
    alm["sun_alt"]=str(sun.alt)
    alm["sun_az"]=str(sun.az)
    moon=ephem.Moon()
    moon.compute(site)
    alm["moon_alt"]=str(moon.alt)
    alm["moon_az"]=str(moon.az)
    alm["moonrise"]=site.next_rising(moon)
    alm["moonset"]=site.next_setting(moon)
    alm["moon_phase"] = moon.moon_phase

    return alm


def RaDec2AltAz(obs,time,ra,dec):
    site=ephem.Observer()
    site.date=time
    site.lon=obs[1]
    site.lat=obs[0]
    site.elevation=float(obs[2])
    
    star=ephem.FixedBody()
    star._ra=str(ra)
    star._dec=str(dec)
    star.compute(site)
    
    return star.az,star.alt
    
    
    
def AltAz2RaDec(obs,time,alt,az):
    site=ephem.Observer()
    site.date=time
    site.lon=obs[1]
    site.lat=obs[0]
    site.elevation=float(obs[2])
    
    ra,dec = site.radec_of(az=az,alt=alt)

    return ra,dec    

def calc_airmass(h):
    try:
        float(h)
        ok = True
    except:
        ok = False
    if ok and h > 20:
        z = 2 * numpy.pi * ( float(h) / 360. )
        a= 1./numpy.sin(z) - 0.0018167*(1./numpy.sin(z) -1) - 0.002875 * (1./numpy.sin(z) -1)*(1./numpy.sin(z) -1) - 0.0008083 * (1./numpy.sin(z) -1)**3
    else: a = None
    return a

