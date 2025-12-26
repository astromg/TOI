# util_functions/PyQtX/QtWidgets.py

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtGui import QGuiApplication
    # Compatibility for QDesktopWidget
    class QDesktopWidget:
        @staticmethod
        def screenGeometry(index=0):
            screens = QGuiApplication.screens()
            if index < len(screens):
                return screens[index].geometry()
            return None

        @staticmethod
        def availableGeometry(index=0):
            screens = QGuiApplication.screens()
            if index < len(screens):
                return screens[index].availableGeometry()
            return None

    # Compatibility aliases for selection behaviors and modes
    QTableWidget.SelectRows = QTableWidget.SelectionBehavior.SelectRows
    QTableWidget.SelectColumns = QTableWidget.SelectionBehavior.SelectColumns
    QTableWidget.SelectItems = QTableWidget.SelectionBehavior.SelectItems
    QTableWidget.SingleSelection = QTableWidget.SelectionMode.SingleSelection
    QTableWidget.MultiSelection = QTableWidget.SelectionMode.MultiSelection
    QTableWidget.NoSelection = QTableWidget.SelectionMode.NoSelection
    # Compatibility aliases for edit triggers
    QTableWidget.NoEditTriggers = QTableWidget.EditTrigger.NoEditTriggers
    QTableWidget.CurrentChanged = QTableWidget.EditTrigger.CurrentChanged
    QTableWidget.DoubleClicked = QTableWidget.EditTrigger.DoubleClicked
    QTableWidget.SelectedClicked = QTableWidget.EditTrigger.SelectedClicked
    QTableWidget.EditKeyPressed = QTableWidget.EditTrigger.EditKeyPressed
    QTableWidget.AnyKeyPressed = QTableWidget.EditTrigger.AnyKeyPressed
    QTableWidget.AllEditTriggers = QTableWidget.EditTrigger.AllEditTriggers
    # Compatibility aliases for frame shapes
    QFrame.NoFrame = QFrame.Shape.NoFrame
    QFrame.Box = QFrame.Shape.Box
    QFrame.Panel = QFrame.Shape.Panel
    QFrame.WinPanel = QFrame.Shape.WinPanel
    QFrame.HLine = QFrame.Shape.HLine
    QFrame.VLine = QFrame.Shape.VLine
    QFrame.StyledPanel = QFrame.Shape.StyledPanel
    # Compatibility aliases for frame shadows
    QFrame.Plain = QFrame.Shadow.Plain
    QFrame.Raised = QFrame.Shadow.Raised
    QFrame.Sunken = QFrame.Shadow.Sunken
    # Compatibility aliases for QAbstractItemView selection behaviors and modes
    QAbstractItemView.SelectRows = QAbstractItemView.SelectionBehavior.SelectRows
    QAbstractItemView.SelectColumns = QAbstractItemView.SelectionBehavior.SelectColumns
    QAbstractItemView.SelectItems = QAbstractItemView.SelectionBehavior.SelectItems
    QAbstractItemView.SingleSelection = QAbstractItemView.SelectionMode.SingleSelection
    QAbstractItemView.MultiSelection = QAbstractItemView.SelectionMode.MultiSelection
    QAbstractItemView.NoSelection = QAbstractItemView.SelectionMode.NoSelection
    # Compatibility aliases for QHeaderView resize modes
    QHeaderView.Interactive = QHeaderView.ResizeMode.Interactive
    QHeaderView.Fixed = QHeaderView.ResizeMode.Fixed
    QHeaderView.Stretch = QHeaderView.ResizeMode.Stretch
    QHeaderView.ResizeToContents = QHeaderView.ResizeMode.ResizeToContents
except ImportError:
    from PyQt5.QtWidgets import *
