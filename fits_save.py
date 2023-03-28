#!/usr/bin/env python3

from astropy.io import fits
import numpy

class SaveFits():
    def __init__(self,parent,image):
        self.parent=parent
        self.image=image.astype(numpy.int16)
        self.path = "../../Desktop/FITS/"
        jd=self.parent.jd
        ojd=jd-2460000.215949074
        ojd=f"{ojd:010.5f}"
        self.fname=self.path+"zb08c_"+ojd.split(".")[0]+"_"+ojd.split(".")[1]+".fits"


        hdr = fits.Header()
        hdr["FITS_STD"]="BETA1"
        hdr["TEL"]=str(self.parent.active_tel)
        hdr["UT"]=str(self.parent.ut)
        hdr["JD"]=str(self.parent.jd)

        hdr["TEL_RA"]=str(self.parent.mount_ra )
        hdr["TEL_DEC"]=str(self.parent.mount_dec)
        hdr["TEL_ALT"]=str(self.parent.mount_alt)
        hdr["TEL_AZ"]=str(self.parent.mount_az )

        hdr["TYPE"]=self.parent.ob_type
        hdr["OBJECT"]=self.parent.ob_name
        hdr["FILTER"]=self.parent.curent_filter
        hdr["DIT"]=self.parent.dit_exp

        hdr["CCD_NAME"]=str(self.parent.ccd_name)
        hdr["CCD_TEMP"]=str(self.parent.ccd_temp)
        hdr["CCD_BINX"]=str(self.parent.ccd_binx)
        hdr["CCD_BINY"]=str(self.parent.ccd_biny)
        hdr["RAED_MOD"]=str(self.parent.ccd_readmode)


        hdr["FOCUS"]=str(self.parent.focus_value)


        hdu = fits.PrimaryHDU(data=self.image,header=hdr)
        hdul = fits.HDUList([hdu])
        hdul.writeto(self.fname)

