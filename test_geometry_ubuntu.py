#!/usr/bin/env python3
import sys
import os
import time

# Ensure we can import PyQtX from current directory
sys.path.append(os.getcwd())

from PyQtX.QtWidgets import QApplication, QWidget, QMainWindow, QLabel, QVBoxLayout
from PyQtX.QtCore import QTimer, Qt

# Target geometry
X, Y, W, H = 200, 200, 400, 300

class GeometryMixin:
    def set_geo(self, x, y, w, h):
        self._target_geo = (x, y, w, h)

    def apply_geo(self):
        if hasattr(self, '_target_geo') and self._target_geo:
            # print(f"{self.__class__.__name__}: Setting geometry to {self._target_geo}")
            self.setGeometry(*self._target_geo)
            self._target_geo = None

class TestWidgetInit(QWidget, GeometryMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: QWidget (Init)")
        self.setGeometry(X, Y, W, H)

class TestWidgetShowEvent(QWidget, GeometryMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: QWidget (ShowEvent)")
        self.set_geo(X, Y, W, H)

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_geo()

class TestMainWindowShowEvent(QMainWindow, GeometryMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: QMainWindow (ShowEvent)")
        cw = QLabel("Central Widget", self)
        cw.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(cw)
        self.set_geo(X, Y, W, H)

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_geo()

class TestWidgetShowEventTimer(QWidget, GeometryMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: QWidget (ShowEvent + Timer)")
        self.set_geo(X, Y, W, H)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.apply_geo) # Small delay 100ms

def run_test(cls):
    print(f"--- Running {cls.__name__} ---")
    app = QApplication.instance() 
    if not app:
        app = QApplication(sys.argv)
    
    win = cls()
    win.show()
    
    # Wait loop
    start = time.time()
    while time.time() - start < 1.0:
        app.processEvents()
        time.sleep(0.05)
        
    g = win.geometry()
    frame = win.frameGeometry()
    print(f"Result {cls.__name__}:")
    print(f"  Request: ({X}, {Y}, {W}, {H})")
    print(f"  Geometry: ({g.x()}, {g.y()}, {g.width()}, {g.height()})")
    # print(f"  FrameGeo: ({frame.x()}, {frame.y()}, {frame.width()}, {frame.height()})")
    
    # Check if position is roughly correct (exact match depends on WM decorations)
    success = (abs(g.x() - X) < 50 and abs(g.y() - Y) < 50) 
    print(f"  Position match: {'YES' if success else 'NO'}")
    
    win.close()
    # print("-" * 20)

if __name__ == "__main__":
    print(f"PyQtX Test Script. Target: ({X}, {Y})")
    run_test(TestWidgetInit)
    run_test(TestWidgetShowEvent)
    run_test(TestMainWindowShowEvent)
    run_test(TestWidgetShowEventTimer)
