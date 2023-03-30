#!/usr/bin/env python3

from astropy.io import fits
import numpy

from ocaboxapi import formatter as form

class SaveFits():
    def __init__(self,parent,image):
        self.parent=parent
        self.image=image.astype(numpy.int16)
        self.path = "../../Desktop/FITS/"
        jd=self.parent.jd
        ojd=jd-2460000.
        ojd=f"{ojd:010.5f}"
        self.fname=self.path+"zb08c_"+ojd.split(".")[0]+"_"+ojd.split(".")[1]+".fits"


        hdr = fits.Header()
        hdr["OCASTD"]="BETA2"
        hdr.comments["OCASTD"]="OCA FITS HDU standard version"
        hdr["OBS"]="OCA"
        hdr.comments["OBS"]="Cerro Armazones Observatory"
        hdr["OBS-LAT"]=form.parse_deg_or_dms(self.parent.observatory[0])
        hdr.comments["OBS-LAT"]=f"[deg] Observatory east longitude {self.parent.observatory[0]} "
        hdr["OBS-LONG"]=form.parse_deg_or_dms(self.parent.observatory[1])
        hdr.comments["OBS-LONG"]=f"[deg] Observatory latitude {self.parent.observatory[1]} "
        hdr["OBS-ELEV"]=float(self.parent.observatory[2])
        hdr.comments["OBS-ELEV"]="[m] Observatory elevation"

        hdr["TEL"]=str(self.parent.active_tel)

        hdr["DATE-OBS"]=str(self.parent.ccd_start_time)
        hdr.comments["DATE-OBS"]="DateTime of observation start"
        hdr["JD"]=str(self.parent.ccd_jd_start)
        hdr.comments["JD"]="Julian date of observation start"

        hdr["RA"]=str(self.parent.req_ra)
        hdr.comments["RA"]="Requested object RA"
        hdr["DEC"]=str(self.parent.req_dec)
        hdr.comments["DEC"]="Requested object DEC"
        hdr["EQUINOX"]=str(self.parent.req_epoch)
        hdr.comments["EQUINOX"]="Requested RA DEC epoch"

        hdr["TEL-RA"]=str(self.parent.mount_ra )
        hdr.comments["TEL-RA"]="Telescope RA"
        hdr["TEL-DEC"]=str(self.parent.mount_dec)
        hdr.comments["TEL-DEC"]="Telescope DEC"
        hdr["TEL-ALT"]=str(self.parent.mount_alt)
        hdr.comments["TEL-ALT"]="[deg] Telescope mount ALT"
        hdr["TEL-AZ"]=str(self.parent.mount_az )
        hdr.comments["TEL-AZ"]="[deg] Telescope mount AZ"

        hdr["AIRMASS"]="unknown"
        hdr["OBSMODE"]="unknown"
        hdr.comments["OBSMODE"]="TRACKING, GUIDING, JITTER or ELSE"
        hdr["FOCUS"]=str(self.parent.focus_value)
        hdr.comments["FOCUS"]="Focus position"
        hdr["ROTATOR"]=str(self.parent.rotator_pos)
        hdr.comments["ROTATOR"]="[deg] Rotator position"

        hdr["OBSERVER"]="unknown"
        hdr["OBSTYPE"]=self.parent.ob_type
        hdr["OBJECT"]=self.parent.ob_name
        hdr["FILTER"]=self.parent.curent_filter
        hdr["EXPREQ"]=self.parent.dit_exp
        hdr.comments["EXPREQ"]="[s] Requested exposure time"
        hdr["EXPTIME"]=self.parent.ccd_exp_time
        hdr.comments["EXPTIME"]="[s] Executed exposure time"

        hdr["DETSIZE"]="unknown"
        hdr["CCDSEC"]="unknown"

        hdr["CCDNAME"]=str(self.parent.ccd_name)
        hdr["CCDTEMP"]=str(self.parent.ccd_temp)
        hdr["CCDBINX"]=str(self.parent.ccd_binx)
        hdr["CCDBINY"]=str(self.parent.ccd_biny)
        hdr["READMODE"]=str(self.parent.ccd_readmode)
        hdr["GAIN"]="unknown"
        hdr["RNOISE"]="unknown"



        hdu = fits.PrimaryHDU(data=self.image,header=hdr)
        hdul = fits.HDUList([hdu])
        hdul.writeto(self.fname)

