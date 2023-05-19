

import numpy
from scipy.signal import convolve2d
from scipy.signal import find_peaks
from scipy.ndimage.filters import maximum_filter

"""
    FFS (Fast Fits Statistics) library for star detection in an image, and basic statistics. 

    Args:
        image (numpy.ndarray): The input image.
        threshold (float, optional): The threshold value for star detection. Defaults to 5.
        gain (float, optional): Detector gain value. Used for noise estimation. Defaults to 1.
        rn_noise (float, optional): Detector readout noise. Used for noise estimation. Defaults to 0.
        method (str, optional): The method used for determining the sigma value. Can be 'rms Poisson','rms','sigma quantile'. Defaults to "sigma quantile".
        kernel_size (int, optional): The size of the Gaussian kernel. Defaults to 9.
        fwhm (float, optional): FWHM value. Defaults to 2.

    Attributes:
        all Args
        min (float): The minimum value of the ADU.
        max (float): The maximum value of the ADU.
        mean (float): The mean value of the ADU.
        median (float): The median value of the ADU.
        rms (float): The root mean square value of the ADU.
        sigma_quantile (float): The sigma value calculated as the quantile 0.5 - 0.159 .
        noise (float): The noise calculated as the Poisson noise accounting gain and readout noise.

    Methods:
        find_stars(): Finds the stars in the image with specified noise calulation method.
    
        Returns:
            coo (numpy.ndarray): An sorted array of coordinates representing the positions of stars.
            adu (numpy.ndarray): An sorted array of ADU values corresponding to the detected stars.

    Example usage:
        stats = FFS(data,threshold=5,kernel_size=9,fwhm=6)
        sigma = stats.sigma_quantile
        p_noise = stats.noise
        coo,adu = stats.find_stars()

"""



class FFS:

    def __init__(self,image,threshold=5.,gain=1.,rn_noise=0.,method="sigma quantile",kernel_size=9,fwhm=2):
        self.image = numpy.transpose(image)
        self.threshold = float(threshold)
        self.gain = float(gain)
        self.rn_noise = float(rn_noise)
        self.method = method
        self.fwhm = float(fwhm)
        self.kernel_size = int(kernel_size)
        self.kernel_sigma = float(fwhm)/2.355

        self.min = numpy.min(image)
        self.max = numpy.max(image)
        self.mean = numpy.mean(image)
        self.median = numpy.median(image)
        self.rms = numpy.std(image)
        self.sigma_quantile = numpy.median(image)-numpy.quantile(image, 0.159)
        self.noise = (self.median/self.gain+self.rn_noise)**0.5             

    def gauss_kernel(self,size,sigma):
        kernel = numpy.fromfunction(lambda x, y: (1/(2*numpy.pi*sigma**2)) * numpy.exp(-((x-(size-1)/2)**2+(y-(size-1)/2)**2)/(2*sigma**2)),(size,size))
        return kernel / numpy.sum(kernel)


    def find_stars(self):

        self.kernel = self.gauss_kernel(self.kernel_size,self.kernel_sigma)

        if self.method == "rms Poisson":
          self.sigma = self.noise
        elif self.method == "rms":
          self.sigma = self.rms
        elif self.method == "sigma quantile":
          self.sigma = self.sigma_quantile
        else: raise ValueError(f"Invalid method type {self.method}") 


        maska1 = self.image > self.median + self.threshold * self.sigma
        data2 = convolve2d(self.image, self.kernel, mode='same')
        maska2 = (data2 == maximum_filter(data2, 3))
        maska = numpy.logical_and(maska1, maska2) 
        coo = numpy.argwhere(maska)
        self.coo = coo
        x,y=zip(*self.coo)
        val = self.image[x,y]
        sorted_i = numpy.argsort(val.astype(float))[::-1]
        sorted_coo = self.coo[sorted_i]
        sorted_val = val[sorted_i]
        self.coo = sorted_coo
        self.adu = sorted_val

        return self.coo, self.adu

