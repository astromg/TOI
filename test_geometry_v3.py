#!/usr/bin/env python3
import sys
import os
import time

# Ensure we can import PyQtX from current directory
sys.path.append(os.getcwd())

from PyQtX.QtWidgets import QApplication, QWidget, QLabel
from PyQtX.QtCore import QTimer, Qt

TARGET_X = 1200
TARGET_Y = 200
W, H = 400, 300

def log(msg):
    print(f"[TEST v3] {msg}")

class AggressiveWindow(QWidget):
    def __init__(self, method_name):
        super().__init__()
        self.method_name = method_name
        self.setWindowTitle(f"Test v3: {method_name}")
        self.resize(W, H)
        
        lbl = QLabel(f"Method: {method_name}\nTarget: x>{TARGET_X}", self)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.resize(W, H)

    def showEvent(self, event):
        super().showEvent(event)
        # Wait a bit for the WM to do its initial placement, then attack
        QTimer.singleShot(500, self.apply_strategy)

    def apply_strategy(self):
        log(f"--- Applying {self.method_name} ---")
        
        if self.method_name == "WindowHandle":
            # Strategy 1: Access QWindow directly (lower level than QWidget)
            wh = self.windowHandle()
            if wh:
                log("Found windowHandle(), calling setPosition")
                wh.setPosition(TARGET_X, TARGET_Y)
            else:
                log("No windowHandle() found! (Is the window hidden?)")

        elif self.method_name == "Hammer":
            # Strategy 2: Call move multiple times with processing
            for i in range(5):
                log(f"Hammer move {i+1}")
                self.move(TARGET_X, TARGET_Y)
                QApplication.processEvents()
                time.sleep(0.1)

        elif self.method_name == "HideMoveShow":
            # Strategy 3: Hide (unmap), Move, Show (map)
            log("Hiding...")
            self.hide()
            QApplication.processEvents()
            time.sleep(0.2)
            log("Moving...")
            self.move(TARGET_X, TARGET_Y)
            QApplication.processEvents()
            time.sleep(0.2)
            log("Showing...")
            self.show()
            
        # Check result after a moment
        QTimer.singleShot(1000, self.check_result)

    def check_result(self):
        g = self.geometry()
        fg = self.frameGeometry()
        log(f"Result {self.method_name}: Qt thinks -> Widget Geo ({g.x()}, {g.y()})")

def run_suite():
    app = QApplication.instance() 
    if not app:
        app = QApplication(sys.argv)

    # Test 1: WindowHandle
    t1 = AggressiveWindow("WindowHandle")
    t1.show()
    process_for(app, 3.0)
    t1.close()
    
    # Test 2: Hammer
    t2 = AggressiveWindow("Hammer")
    t2.show()
    process_for(app, 3.0)
    t2.close()

    # Test 3: HideMoveShow
    t3 = AggressiveWindow("HideMoveShow")
    t3.show()
    process_for(app, 4.0)
    t3.close()

def process_for(app, duration):
    start = time.time()
    while time.time() - start < duration:
        app.processEvents()
        time.sleep(0.05)

if __name__ == "__main__":
    log(f"Starting Aggressive Geometry Test. Target X: {TARGET_X}")
    print("NOTE: If on Wayland, try running with: QT_QPA_PLATFORM=xcb python3 test_geometry_v3.py")
    run_suite()
