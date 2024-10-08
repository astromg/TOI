#!/usr/bin/env python3

import os
import numpy
from ffs_lib.ffs import FFS
from scipy.optimize import curve_fit

from astropy.io import fits

METHODS = ["rms","rms_quad","lorentzian" ]


def calculate(fits_path, focus_keyword="FOCUS", focus_list=None, crop=10, method="rms_quad"):
    """
    Function to calculate the focus position of maximum sharpness for a given FITS files.

    Parameters:
    fits_path (str): The path to the FITS files directory or a list with FITS files.
    focus_keyword (str, optional): FIST file header keyword to retrive focus encoder position. Default: "FOCUS".
    focus_list (list or None, optional): A list of focus values to use for the calculation. If None, the focus values will be extracted from the FITS header. Defaults to None.
    crop (int, optional): The amount of pixels to crop from the edges of each image. Defaults to 10.
    method (str, optional): The method to use for calculating sharpness. Can be "rms", "rms_quad". Defaults to "rms_quad".

    Returns:
    tuple: (ax_sharpness_focus, calc_metadata). 
    * ax_sharpness_focus: focus encoder value for maximum sharpness
    * calc_metadata: Dictionary of metadata has the following keys:
    - poly_coef: A NumPy array of coefficients for the polynomial fit used to calculate sharpness.
    - focus_values: A list of focus values used for the calculation.
    - sharpness_values: A list of corresponding sharpness values for each focus value.
    """

    if method not in METHODS:
        raise ValueError(f"Invalid method {method}")
    if isinstance(fits_path, list):
        if not all(os.path.isfile(file) for file in fits_path):
            raise ValueError(f"Invalid list with fits {fits_path}")
        lista = fits_path
    else:
        if os.path.isdir(fits_path):
            lista = [os.path.join(fits_path, f) for f in os.listdir(fits_path) if ".fits" in f]
        else:
            raise ValueError(f"{fits_path} is not valid dir")

    if focus_list:
        if not isinstance(fits_path, list):
            raise TypeError(f"if focus_list is provided, FITS files must be provided as a list")
        elif len(lista) != len(focus_list):
            raise ValueError(f"focus_list and fits_files_list must have same length")



    focus_list_ret = []
    sharpness_list_ret = []

    for my_iter, f_file in enumerate(lista):
        hdu = fits.open(f_file)
        hdr = hdu[0].header
        if focus_list is None:
            focus = hdr[focus_keyword]
        else:
            focus = focus_list[my_iter]
        data = hdu[0].data

        edge_rows = int(data.shape[0] * float(crop) / 100.)
        edge_cols = int(data.shape[1] * float(crop) / 100.)

        data = data[edge_rows:-edge_rows, edge_cols:-edge_cols]

        mean = numpy.mean(data)
        median = numpy.median(data)
        rms = numpy.std(data)
        sharpness = rms

        focus_list_ret.append(float(focus))
        sharpness_list_ret.append(sharpness)

        hdu.close()

    focus_list_ret = numpy.array(focus_list_ret)
    sharpness_list_ret = numpy.array(sharpness_list_ret)

    # ##### RMS with quadratic fit ######
    if method == "lorentzian":
        if len(lista) < 4:
            raise ValueError(f"for {method} method at least 4 focus positions are required")
        p0 = [max(sharpness_list_ret) - min(sharpness_list_ret), numpy.median(focus_list_ret), 10,
              min(sharpness_list_ret)]
        coef, _ = curve_fit(lorentzian, focus_list_ret, sharpness_list_ret, p0=p0)
        fit_x = numpy.linspace(min(focus_list_ret), max(focus_list_ret), 100)
        fit_y = lorentzian(fit_x,*coef)
        max_sharpness_focus = coef[1]

    # ##### RMS with quadratic fit ######

    elif method == "rms_quad":
        if len(lista) < 4:
            raise ValueError(f"for {method} method at least 4 focus positions are required")
        coef = numpy.polyfit(focus_list_ret, sharpness_list_ret, 4)
        fit_x = numpy.linspace(min(focus_list_ret), max(focus_list_ret), 100)
        fit_y = coef[0] * fit_x ** 4 + coef[1] * fit_x ** 3 + coef[2] * fit_x ** 2 + coef[3] * fit_x + coef[4]
        a = numpy.max(focus_list_ret)
        b = numpy.min(focus_list_ret)
        x = numpy.linspace(a, b, 1000)
        y = numpy.polyval(coef, x)
        k = numpy.argmax(y)
        max_sharpness_focus = x[k]


    # ##### RMS with parabolic fit ######
    elif method == "rms":
        if len(lista) < 2:
            raise ValueError(f"for {method} method at least 2 focus positions are required")
        coef = numpy.polyfit(focus_list_ret, sharpness_list_ret, 2)
        fit_x = numpy.linspace(min(focus_list_ret), max(focus_list_ret), 100)
        fit_y = coef[0] * fit_x ** 2 + coef[1] * fit_x + coef[2]
        a = numpy.max(focus_list_ret)
        b = numpy.min(focus_list_ret)
        x = numpy.linspace(a, b, 1000)
        y = numpy.polyval(coef, x)
        k = numpy.argmax(y)
        max_sharpness_focus = x[k]

    if numpy.abs(numpy.max(sharpness_list_ret) - numpy.min(sharpness_list_ret)) < 5:
        status = "to small sharpness range"
    elif max_sharpness_focus < min(focus_list_ret) or  max_sharpness_focus > max(focus_list_ret):
        status = "wrong range"
    else : status = "ok"

    calc_metadata = {
        "status":status,
        "coef": coef,
        "focus_values": focus_list_ret,
        "sharpness_values": sharpness_list_ret,
        "fit_x": fit_x,
        "fit_y": fit_y
        }

    return max_sharpness_focus, calc_metadata

def lorentzian(x, A, x0, gamma, z):
    return A * (gamma**2) / ((x - x0)**2 + gamma**2) + z



