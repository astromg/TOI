#!/usr/bin/env python3

import ephem


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





