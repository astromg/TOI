#!/usr/bin/env python3

from collections import OrderedDict
import ephem
import numpy
import time

from PyQt5.QtCore import QThread,pyqtSignal



class Worker(QThread):
    finished = pyqtSignal()
    def __init__(self,ccd):
        super().__init__()
        self.ccd = ccd
    def run(self):
        print("IDE CZY NIE IDE!!!!!!!!!!!!!")
        self.image = self.ccd.imagearray
        if self.image:
            self.image = numpy.asarray(self.image)
            self.image = self.image.astype(numpy.uint16)
            print("DUPA!!! ", numpy.mean(self.image))
            self.finished.emit()


#seq=10x(4/B/10,2/V/46)
#seq=4/B/10,2/V/46,4/B/10,2/V/46,4/B/10,2/V/46,4/B/10,2/V/46,4/B/10,2/V/46,4/B/10,2/V/46,4/B/10,2/V/46






def seq_parser(seq):
    if "x" in seq and "(" in seq and ")" in seq:
        try:
            n = int(seq.split("x")[0])
            s = seq.split("x")[1].strip("(").strip(")")+","
            r = s*n
            r=r[:-1]
            return r
        except Exception as e:
            print(f"seq_parser: {e}")
    else:
        return seq

def seq_verification(seq,filter_list):
    ok = True
    err = ""
    seq = seq_parser(seq)
    for x_seq in seq.split(","):
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

def ob_parser(block,overhed = 0, types=["STOP","BELL","WAIT","OBJECT","DARK","ZERO","SKYFLAT","DOMEFLAT","FOCUS"],filter_list=["B","V","Ic"]):
    ob = OrderedDict({"block":block,"type":"","name":"","ra":"","dec":"","seq":"","pos":"","wait":"","wait_ut":"","wait_sunset":"","wait_sunrise":"","slotTime":"","comment":""})
    ob_header = OrderedDict({"block":"","type":"","name":"","ra":"","dec":"","seq":"seq=","pos":"pos=","wait":"wait=","wait_ut":"ut=","wait_sunset":"sunset=","wait_sunrise":"sunrise=","slotTime":"","comment":"comment="})
    active = OrderedDict({"block":True,"type":True,"name":True,"ra":None,"dec":None,"seq":None,"pos":None,"wait":None,"wait_ut":None,"wait_sunset":None,"wait_sunrise":None,"slotTime":None,"comment":None})
    ok = OrderedDict({"block":None,"type":None,"name":None,"ra":None,"dec":None,"seq":None,"pos":None,"wait":None,"wait_ut":None,"wait_sunset":None,"wait_sunrise":None,"slotTime":None,"comment":None})
    options = OrderedDict({"block":None,"type":None,"name":None,"ra":None,"dec":None,"seq":None,"pos":None,"wait":None,"wait_ut":None,"wait_sunset":None,"wait_sunrise":None,"slotTime":None,"comment":None})

    err = block+"\n"

    ll = block.split()

    type = ""
    try:
        type = ll[0]
        if type in types:
            ob["type"] = type
            ok["type"] = True
    except IndexError:
        ok["type"] = False


    if type == "STOP":
        ob["name"] = "STOP"
        ok["name"] = True
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": False, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

    if type == "BELL":
        ob["name"] = "BELL"
        ok["name"] = True
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": False, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

    if type == "WAIT":
        ob["name"] = "WAIT"
        ok["name"] = True
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": False, "pos": False, "wait": None,
             "wait_ut": None, "wait_sunset": None, "wait_sunrise": None, "slotTime": False, "comment": None})

        if "wait=" in block:
            try:
                tmp = block.split("wait=")[1].split()[0]
                ob["wait"] = tmp
                q = float(tmp)+1
                ok["wait"] = True
            except:
                ok["wait"] = False
            active["wait"] = True
        elif "ut=" in block:
            try:
                tmp = block.split("ut=")[1].split()[0]
                ob["wait_ut"] = tmp
                q = 3600*float(tmp.split(":")[0])+60*float(tmp.split(":")[1])+float(tmp.split(":")[2])
                ok["wait_ut"] = True
            except:
                ok["wait_ut"] = False
            active["wait_ut"] = True
        elif "sunset=" in block:
            try:
                tmp = block.split("sunset=")[1].split()[0]
                ob["wait_sunset"] = tmp
                q = float(tmp)
                ok["wait_sunset"] = True
            except:
                ok["wait_sunset"] = False
            active["wait_sunset"] = True
        elif "sunrise=" in block:
            try:
                tmp = block.split("sunrise=")[1].split()[0]
                ob["wait_sunrise"] = tmp
                q = float(tmp)
                ok["wait_sunrise"] = True
            except:
                ok["wait_sunrise"] = False
            active["wait_sunrise"] = True
        else:
            ok["wait"] = False
            active["wait"] = True
            ok["wait_ut"] = False
            active["wait_ut"] = True
            ok["wait_sunset"] = False
            active["wait_sunset"] = True
            ok["wait_sunrise"] = False
            active["wait_sunrise"] = True

    if type == "ZERO":
        ob["name"] = "ZERO"
        ok["name"] = True
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": True, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver,err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False


    if type == "DARK":
        ob["name"] = "DARK"
        ok["name"] = True
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": True, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver,err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False

    if type == "DOMEFLAT":
        try:
            ob["name"] = ll[0]
            ok["name"] = True
        except:
            ok["name"] = False
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": False, "dec": False, "seq": True, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver,err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False

    if type == "SKYFLAT":
        try:
            ob["name"] = ll[0]
            ok["name"] = True
        except:
            ok["name"] = False
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": True, "dec": True, "seq": True, "pos": False, "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        try:
            ra = ll[2]
            ob["ra"] = ra
            ok["ra"] = True
            if float(ra.split(":")[0])<0 or float(ra.split(":")[0])>24:
                ok["ra"] = False
            if float(ra.split(":")[1])<0 or float(ra.split(":")[1])>60:
                ok["ra"] = False
            if float(ra.split(":")[2])<0 or float(ra.split(":")[2])>60:
                ok["ra"] = False
        except:
            ok["ra"] = False

        try:
            dec = ll[3]
            ob["dec"] = dec
            ok["dec"] = True
            if float(dec.split(":")[0]) < -90 or float(dec.split(":")[0]) > 90:
                ok["dec"] = False
            if float(dec.split(":")[1]) < 0 or float(dec.split(":")[1]) > 60:
                ok["dec"] = False
            if float(dec.split(":")[2]) < 0 or float(dec.split(":")[2]) > 60:
                ok["dec"] = False
        except:
            ok["dec"] = False


        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver,err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False


    if type == "OBJECT":
        try:
            ob["name"] = ll[1]
            ok["name"] = True
        except:
            ok["name"] = False
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": True, "dec": True, "seq": True, "pos": False,
             "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        try:
            ra = ll[2]
            ob["ra"] = ra
            ok["ra"] = True
            if float(ra.split(":")[0]) < 0 or float(ra.split(":")[0]) > 24:
                ok["ra"] = False
            if float(ra.split(":")[1]) < 0 or float(ra.split(":")[1]) > 60:
                ok["ra"] = False
            if float(ra.split(":")[2]) < 0 or float(ra.split(":")[2]) > 60:
                ok["ra"] = False
        except:
            ok["ra"] = False

        try:
            dec = ll[3]
            ob["dec"] = dec
            ok["dec"] = True
            if float(dec.split(":")[0]) < -90 or float(dec.split(":")[0]) > 90:
                ok["dec"] = False
            if float(dec.split(":")[1]) < 0 or float(dec.split(":")[1]) > 60:
                ok["dec"] = False
            if float(dec.split(":")[2]) < 0 or float(dec.split(":")[2]) > 60:
                ok["dec"] = False
        except:
            ok["dec"] = False

        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver, err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False

    if type == "FOCUS":
        try:
            ob["name"] = ll[1]
            ok["name"] = True
        except:
            ok["name"] = False
        active = OrderedDict(
            {"block": True, "type": True, "name": True, "ra": True, "dec": True, "seq": True, "pos": True,
             "wait": False,
             "wait_ut": False, "wait_sunset": False, "wait_sunrise": False, "slotTime": False, "comment": None})

        try:
            ra = ll[2]
            ob["ra"] = ra
            ok["ra"] = True
            if float(ra.split(":")[0]) < 0 or float(ra.split(":")[0]) > 24:
                ok["ra"] = False
            if float(ra.split(":")[1]) < 0 or float(ra.split(":")[1]) > 60:
                ok["ra"] = False
            if float(ra.split(":")[2]) < 0 or float(ra.split(":")[2]) > 60:
                ok["ra"] = False
        except:
            ok["ra"] = False

        try:
            dec = ll[3]
            ob["dec"] = dec
            ok["dec"] = True
            if float(dec.split(":")[0]) < -90 or float(dec.split(":")[0]) > 90:
                ok["dec"] = False
            if float(dec.split(":")[1]) < 0 or float(dec.split(":")[1]) > 60:
                ok["dec"] = False
            if float(dec.split(":")[2]) < 0 or float(dec.split(":")[2]) > 60:
                ok["dec"] = False
        except:
            ok["dec"] = False

        if "seq=" in block:
            try:
                tmp = block.split("seq=")[1].split()[0]
                ob["seq"] = tmp
                ver, err = seq_verification(tmp, filter_list)
                if ver:
                    ok["seq"] = True
                    ob["slotTime"] = calc_slot_time(ob["seq"], overhed)
                else:
                    ok["seq"] = False
            except:
                ok["seq"] = False

        if "pos=" in block:
            try:
                tmp = block.split("pos=")[1].split()[0]
                ob["pos"] = tmp
                if float(tmp.split("/")[0])>0 and float(tmp.split("/")[1])>0:
                    ok["pos"] = True
                else:
                    ok["pos"] = False
            except:
                ok["pos"] = False

    ok["block"] = True
    for key in ob.keys():
        if active[key]:
            if not ok[key]:
                ok["block"] = False

    return ob,ok,active,options,ob_header

def calc_slot_time(seq, overhed):
    slotTime = 0
    k = 1
    res = 0
    try:
        if "x(" in seq and ")" in seq:
            k = int(seq.split("x")[0])
            seq = seq.split("x(")[1].split(")")[0]
        for x_seq in seq.split(","):
            if "a" in x_seq:
                x_seq = x_seq.replace("/a", "/5")
            slotTime = slotTime + (float(x_seq.split("/")[0]) * (float(x_seq.split("/")[2]) + float(overhed)))
        res = k * slotTime
    except:
        print(f"wrong seq {seq}")
    return res


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


def UT_SID(obs):
    site=ephem.Observer()
    site.date=ephem.now()
    site.lon=obs[1]
    site.lat=obs[0]
    site.elevation=float(obs[2])
    sid=site.sidereal_time()
    jd=ephem.julian_date(site)
    sunrise=site.next_rising(ephem.Sun())
    sunset=site.next_setting(ephem.Sun())
    sun=ephem.Sun()
    sun.compute(site)
    sun_alt=float(str(sun.alt).split(":")[0])+float(str(sun.alt).split(":")[1])/60.
    sun_az=float(str(sun.az).split(":")[0])+float(str(sun.az).split(":")[1])/60.
    moon=ephem.Moon()
    moon.compute(site)
    moon_alt=float(str(moon.alt).split(":")[0])+float(str(moon.alt).split(":")[1])/60.
    moon_az=float(str(moon.az).split(":")[0])+float(str(moon.az).split(":")[1])/60.

    moonrise=site.next_rising(ephem.Moon())
    moonset=site.next_setting(ephem.Moon())
    moon_phase = moon.moon_phase

    return sid, jd, site.date, sunrise, sunset,sun_alt,sun_az,moon_alt,moon_az,moonrise,moonset,moon_phase

def RaDecEpoch(obs,ra,dec,epoch):
    site=ephem.Observer()
    site.date=ephem.now()
    site.lon=obs[1]
    site.lat=obs[0]
    site.elevation=float(obs[2])
    star=ephem.FixedBody()
    star._ra=ephem.hours(ra)
    star._dec=ephem.degrees(dec)
    star._epoch=epoch
    star.compute(site)
    return str(star.g_ra), str(star.g_dec)

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


def hmsRa2float(hms):
    h=float(hms.split(":")[0])
    m=float(hms.split(":")[1])
    s=float(hms.split(":")[2])
    deg=15*h+15*m/60.+15*s/3600.
    return deg


def arcDeg2float(arc):
    arc=arc.split(":")
    if float(arc[0])<0:
       f=float(arc[0])-float(arc[1])/60.-float(arc[2])/3600.
    else:
       f=float(arc[0])+float(arc[1])/60.+float(arc[2])/3600.
    return f
    
def Deg2H(deg):
    h=(deg/360.)*24
    m=(h-int(h))*60
    s=(m-int(m))*60
    h,m=int(h),int(m)
    hms=f"{h}:{m}:{s:.2f}"
    return hms

def Deg2DMS(deg):
    d=int(deg)
    m=(deg-d)*60
    s=(m-int(m))*60
    m=abs(int(m))
    s=abs(s)
    dms=f"{d}:{m}:{s:.2f}"
    return dms





