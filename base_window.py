from PyQtX.QtWidgets import QWidget

class BaseWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._geometry = None

    def set_initial_geometry(self, x, y, width, height):
        self._geometry = (x, y, width, height)

    def showEvent(self, event):
        super().showEvent(event)
        if self._geometry:
            self.setGeometry(*self._geometry)
            self._geometry = None
