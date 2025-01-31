

import numpy
from scipy.signal import convolve2d
from scipy.signal import find_peaks
from scipy.ndimage.filters import maximum_filter

"""
    FFS (Fast Fits Statistics) library for star detection in an image, and basic statistics. 

    Args:
        image (numpy.ndarray): The input image.
        gain (float, optional): Detector gain value. Used for noise estimation. Defaults to 1.
        rn_noise (float, optional): Detector readout noise. Used for noise estimation. Defaults to 0.

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
        find_stars(self,threshold=5.,method="sigma quantile",kernel_size=9,fwhm=2): Finds the stars in the image with specified noise calulation method.

          Args:
              threshold (float, optional): The threshold value for star detection. Defaults to 5.
              method (str, optional): The method used for determining the sigma value. Can be 'rms Poisson','rms','sigma quantile'. Defaults to "sigma quantile".
              kernel_size (int, optional): The size of the Gaussian kernel. Defaults to 9.
              fwhm (float, optional): FWHM value. Defaults to 2.

          Returns:
              coo (numpy.ndarray): An sorted array of coordinates representing the positions of stars.
              adu (numpy.ndarray): An sorted array of ADU values corresponding to the detected stars.

        fwhm(self,saturation=65000,radius=10,all_stars=True): Calculates the average fwhm for stars in the X and Y axis.

          Args:
            saturation (float): Saturation level above fwhm calculation will be ignored for a star. Defaults to 65000
            radius (int): Radius in which fwhm will be calculated. Defaults to 10
            all_stars (bool): If True, fwhm will be calculated for all stars. 
                              If False, only for 100 non saturated brightests. Defaults to True

          Returns: 
            fwhm_x,fwhm_y (float,float): Median of fwhm for X and Y axis, respectively

          Attributes:
            fwhm_xarr (numpy.ndarray): array of fwhm in X axis for stars, ordered accordingly to star ADU
            fwhm_yarr (numpy.ndarray): array of fwhm in Y axis for stars, ordered accordingly to star ADU

    Example usage:
        stats = FFS(data,threshold=5,kernel_size=9,fwhm=6)
        sigma = stats.sigma_quantile
        p_noise = stats.noise
        coo,adu = stats.find_stars()
        fwhm_x,fwhm_u = stats.fwhm(saturation=50000,all_stars=True)
        fwhm_xarr = stats.fwhm_xarr
        fwhm_yarr = stats.fwhm_yarr

"""



class FFS:

    def __init__(self,image,gain=1.,rn_noise=0.):

        self.image = numpy.transpose(image)
        self.gain = float(gain)
        self.rn_noise = float(rn_noise)
        self.min = numpy.min(image)
        self.max = numpy.max(image)
        self.mean = numpy.mean(image)
        self.median = numpy.median(image)
        self.rms = numpy.std(image)
        self.sigma_quantile = numpy.median(image)-numpy.quantile(image, 0.159)
        self.noise = (self.median/self.gain+self.rn_noise)**0.5             

        self.fwhm_x=None
        self.fwhm_y=None

    def gauss_kernel(self,size,sigma):
        kernel = numpy.fromfunction(lambda x, y: (1/(2*numpy.pi*sigma**2)) * numpy.exp(-((x-(size-1)/2)**2+(y-(size-1)/2)**2)/(2*sigma**2)),(size,size))
        return kernel / numpy.sum(kernel)

    def find_stars(self,threshold=5.,method="sigma quantile",kernel_size=30,fwhm=10):
        self.coo=[]
        self.adu=[]
        self.threshold = float(threshold)
        self.method = method
        self.fwhm_adopted = float(fwhm)
        self.kernel_size = int(kernel_size)
        self.kernel_sigma = float(fwhm)/2.355
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
        if len(coo)>1:
            self.coo = coo
            x,y=zip(*self.coo)
            val = self.image[x,y]
            sorted_i = numpy.argsort(val.astype(float))[::-1]
            sorted_coo = self.coo[sorted_i]
            sorted_val = val[sorted_i]
            self.coo = sorted_coo
            self.adu = sorted_val

        return self.coo, self.adu

    def fwhm(self,saturation=65000,radius=10,all_stars=True):
        radius=int(radius)
        self.fwhm_xarr=[]
        self.fwhm_yarr=[]
        self.fwhm_x=None
        self.fwhm_y=None
        for i,tmp in enumerate(self.coo):
            if all_stars: i_max = len(self.adu)
            else: i_max = 100
            d1=d2=d3=d4 = None            
            if self.adu[i] < int(saturation) and i<i_max:
                x,y = self.coo[i]
                max_adu = self.adu[i]
                half_adu = (max_adu-self.median)/2.

                if True:           
                    line = self.image[x-radius:x+radius,y] - self.median - half_adu  
                    line = self.image[x-radius+1:x+1,y] - self.median - half_adu
                    maska1,maska2 = line > 0, line < 0
                    pos,neg = line[maska1], line[maska2]
                    if len(pos) > 0 and len(neg) > 0:
                        lower,upper = max(neg), min(pos) 
                        line = list(line)  
                        lower_i,upper_i = line.index(lower),line.index(upper)
                        lower_adu,upper_adu = line[lower_i],line[upper_i]
                        d1 = radius - upper_i - numpy.abs(lower_adu)/(numpy.abs(lower_adu)+numpy.abs(upper_adu))
          
                    line = self.image[x:x+radius,y] - self.median - half_adu
                    maska1,maska2 = line > 0, line < 0
                    pos,neg = line[maska1], line[maska2]
                    if len(pos) > 0 and len(neg) > 0:
                        lower,upper = max(neg), min(pos) 
                        line = list(line)  
                        lower_i,upper_i = line.index(lower),line.index(upper)
                        lower_adu,upper_adu = line[lower_i],line[upper_i]
                        d2 =  upper_i + 1 - numpy.abs(lower_adu)/(numpy.abs(lower_adu)+numpy.abs(upper_adu))


                    line = self.image[x,y-radius+1:y+1] - self.median - half_adu
                    maska1,maska2 = line > 0, line < 0
                    pos,neg = line[maska1], line[maska2]
                    if len(pos) > 0 and len(neg) > 0:
                        lower,upper = max(neg), min(pos) 
                        line = list(line)  
                        lower_i,upper_i = line.index(lower),line.index(upper)
                        lower_adu,upper_adu = line[lower_i],line[upper_i]
                        d3 = radius - upper_i - numpy.abs(lower_adu)/(numpy.abs(lower_adu)+numpy.abs(upper_adu))
          
                    line = self.image[x,y:y+radius] - self.median - half_adu
                    maska1,maska2 = line > 0, line < 0
                    pos,neg = line[maska1], line[maska2]
                    if len(pos) > 0 and len(neg) > 0:
                        lower,upper = max(neg), min(pos) 
                        line = list(line)  
                        lower_i,upper_i = line.index(lower),line.index(upper)
                        lower_adu,upper_adu = line[lower_i],line[upper_i]
                        d4 =  upper_i + 1 - numpy.abs(lower_adu)/(numpy.abs(lower_adu)+numpy.abs(upper_adu))

            if d1!=None and d2!=None:
                dx = (d1+d2)
            else: dx = 0    
            
            if d3!=None and d4!=None:
                dy = (d3+d4)
            else: dy = 0 
            self.fwhm_xarr.append(dx)  
            self.fwhm_yarr.append(dy)
        
        self.fwhm_xarr,self.fwhm_yarr=numpy.array(self.fwhm_xarr),numpy.array(self.fwhm_yarr)
        
        maska = self.fwhm_xarr==0
        fwhm_xarr = self.fwhm_xarr[~maska]

        maska = self.fwhm_yarr==0
        fwhm_yarr = self.fwhm_yarr[~maska]

        if len(fwhm_xarr)>2:
            self.fwhm_x = numpy.median(fwhm_xarr)
        if len(fwhm_yarr)>2:
            self.fwhm_y = numpy.median(fwhm_yarr)

        return self.fwhm_x,self.fwhm_y
