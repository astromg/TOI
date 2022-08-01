#!/usr/bin/env python3

#----------------
# 1.08.2022
# Marek Gorski
#----------------
from PyQt5.QtWidgets import  QApplication
import sys
from mnt_gui import *
from tel_gui import *
from sky_gui import *

app = QApplication(sys.argv)

mnt = MntGui()
mnt.show()
mnt.raise_()  

tel = TelGui()
tel.show()
tel.raise_()  

sky = SkyView()
sky.show()
sky.raise_()  



sys.exit(app.exec_())
