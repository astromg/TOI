# util_functions/PyQtX/QtCore.py

try:
    from PyQt6.QtCore import *
    # Compatibility aliases for alignment flags
    Qt.AlignCenter = Qt.AlignmentFlag.AlignCenter
    Qt.AlignLeft = Qt.AlignmentFlag.AlignLeft
    Qt.AlignRight = Qt.AlignmentFlag.AlignRight
    Qt.AlignTop = Qt.AlignmentFlag.AlignTop
    Qt.AlignBottom = Qt.AlignmentFlag.AlignBottom
    Qt.AlignHCenter = Qt.AlignmentFlag.AlignHCenter
    Qt.AlignVCenter = Qt.AlignmentFlag.AlignVCenter
    # Compatibility aliases for layout directions
    Qt.LeftToRight = Qt.LayoutDirection.LeftToRight
    Qt.RightToLeft = Qt.LayoutDirection.RightToLeft
    # Compatibility aliases for orientations
    Qt.Horizontal = Qt.Orientation.Horizontal
    Qt.Vertical = Qt.Orientation.Vertical
    # Compatibility aliases for match flags
    Qt.MatchContains = Qt.MatchFlag.MatchContains
    # Compatibility aliases for case sensitivity
    Qt.CaseInsensitive = Qt.CaseSensitivity.CaseInsensitive
    Qt.CaseSensitive = Qt.CaseSensitivity.CaseSensitive
except ImportError:
    from PyQt5.QtCore import *