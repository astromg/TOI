#!/usr/bin/env python3

import ephem

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
    
    print(ra,dec)
    return ra,dec    

def arcDeg2float(arc):
    arc=arc.split(":")
    f=float(arc[0])+float(arc[1])/60.+float(arc[2])/3600.
    return f
    
