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
    # Compatibility aliases for colors (GlobalColor)
    Qt.black = Qt.GlobalColor.black
    Qt.white = Qt.GlobalColor.white
    Qt.gray = Qt.GlobalColor.gray
    Qt.red = Qt.GlobalColor.red
    Qt.blue = Qt.GlobalColor.blue
    Qt.green = Qt.GlobalColor.green
    Qt.cyan = Qt.GlobalColor.cyan
    Qt.magenta = Qt.GlobalColor.magenta
    Qt.yellow = Qt.GlobalColor.yellow
    Qt.darkRed = Qt.GlobalColor.darkRed
    Qt.darkGreen = Qt.GlobalColor.darkGreen
    Qt.darkBlue = Qt.GlobalColor.darkBlue
    Qt.darkCyan = Qt.GlobalColor.darkCyan
    Qt.darkMagenta = Qt.GlobalColor.darkMagenta
    Qt.darkYellow = Qt.GlobalColor.darkYellow
    Qt.darkGray = Qt.GlobalColor.darkGray
    Qt.lightGray = Qt.GlobalColor.lightGray
except ImportError:
    from PyQt5.QtCore import *
