#!/usr/bin/env python3
import sys
import os
import time

# Ensure we can import PyQtX from current directory
sys.path.append(os.getcwd())

from PyQtX.QtWidgets import QApplication, QWidget, QMainWindow, QLabel
from PyQtX.QtCore import QTimer, Qt

TARGET_X = 1200
TARGET_Y = 200
W, H = 400, 300

def log(msg):
    print(f"[TEST] {msg}")

class TestWindow(QWidget):
    def __init__(self, name, delay_ms=0):
        super().__init__()
        self.setWindowTitle(f"Test: {name}")
        self.resize(W, H)
        self.move_delay = delay_ms
        self._step = 0
        
        lbl = QLabel(f"Target: x>{TARGET_X}\nDelay: {delay_ms}ms", self)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.resize(W, H)

    def showEvent(self, event):
        super().showEvent(event)
        if self.move_delay > 0:
            log(f"{self.windowTitle()}: Scheduling move in {self.move_delay}ms")
            QTimer.singleShot(self.move_delay, self.perform_move)
        else:
            log(f"{self.windowTitle()}: Moving immediately in showEvent")
            self.perform_move()

    def perform_move(self):
        log(f"{self.windowTitle()}: Calling move({TARGET_X}, {TARGET_Y})")
        self.move(TARGET_X, TARGET_Y)
        
        # Check immediately
        g = self.geometry()
        log(f"{self.windowTitle()}: Immediate geometry check -> ({g.x()}, {g.y()})")
        
        # Check again after a short delay to see if WM reverted it
        QTimer.singleShot(500, self.check_geometry)

    def check_geometry(self):
        g = self.geometry()
        # frame = self.frameGeometry()
        log(f"{self.windowTitle()}: Delayed geometry check (500ms later) -> ({g.x()}, {g.y()})")
        if g.x() >= 1000:
            log(f"{self.windowTitle()}: SUCCESS (Visually confirm if it is actually at x>1000)")
        else:
            log(f"{self.windowTitle()}: FAILED (Qt thinks x={g.x()})")

def run_suite():
    app = QApplication.instance() 
    if not app:
        app = QApplication(sys.argv)

    # Test 1: Immediate move in showEvent
    t1 = TestWindow("Immediate Move", delay_ms=0)
    t1.show() 
    
    # Run loop for a bit
    process_for(app, 2.0)
    t1.close()
    
    # Test 2: Delayed move (100ms)
    t2 = TestWindow("Delayed 100ms", delay_ms=100)
    t2.show()
    process_for(app, 2.0)
    t2.close()

    # Test 3: Long Delayed move (1000ms) - usually beats WM initial placement
    t3 = TestWindow("Delayed 1000ms", delay_ms=1000)
    t3.show()
    process_for(app, 3.0)
    t3.close()

def process_for(app, duration):
    start = time.time()
    while time.time() - start < duration:
        app.processEvents()
        time.sleep(0.05)

if __name__ == "__main__":
    log(f"Starting Geometry Test V2. Target X: {TARGET_X}")
    run_suite()
