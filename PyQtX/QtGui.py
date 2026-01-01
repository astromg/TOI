# util_functions/PyQtX/QtGui.py

try:
    from PyQt6.QtGui import *
    # Compatibility aliases for QTextCursor move operations
    QTextCursor.Start = QTextCursor.MoveOperation.Start
    QTextCursor.End = QTextCursor.MoveOperation.End
    QTextCursor.Up = QTextCursor.MoveOperation.Up
    QTextCursor.Down = QTextCursor.MoveOperation.Down
    QTextCursor.Left = QTextCursor.MoveOperation.Left
    QTextCursor.Right = QTextCursor.MoveOperation.Right
    QTextCursor.WordLeft = QTextCursor.MoveOperation.WordLeft
    QTextCursor.WordRight = QTextCursor.MoveOperation.WordRight
    QTextCursor.StartOfLine = QTextCursor.MoveOperation.StartOfLine
    QTextCursor.EndOfLine = QTextCursor.MoveOperation.EndOfLine
    QTextCursor.StartOfBlock = QTextCursor.MoveOperation.StartOfBlock
    QTextCursor.EndOfBlock = QTextCursor.MoveOperation.EndOfBlock
    QTextCursor.StartOfWord = QTextCursor.MoveOperation.StartOfWord
    QTextCursor.EndOfWord = QTextCursor.MoveOperation.EndOfWord
    QTextCursor.PreviousBlock = QTextCursor.MoveOperation.PreviousBlock
    QTextCursor.NextBlock = QTextCursor.MoveOperation.NextBlock
    QTextCursor.PreviousCharacter = QTextCursor.MoveOperation.PreviousCharacter
    QTextCursor.NextCharacter = QTextCursor.MoveOperation.NextCharacter
    QTextCursor.PreviousWord = QTextCursor.MoveOperation.PreviousWord
    QTextCursor.NextWord = QTextCursor.MoveOperation.NextWord
except ImportError:
    from PyQt5.QtGui import *