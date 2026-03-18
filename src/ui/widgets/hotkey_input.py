from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtCore import Qt

class HotkeyInput(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Press key...")
        self.setReadOnly(True)  # Prevent manual typing
        self.key_sequence = None

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # Ignore standalone modifiers
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        # Handle Backspace/Delete to clear
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            self.clear_hotkey()
            return

        # Create key sequence string
        seq = QKeySequence(int(modifiers) | key)
        self.key_sequence = seq.toString()
        self.setText(self.key_sequence)
        
    def set_hotkey(self, key_str):
        self.key_sequence = key_str
        self.setText(key_str)

    def clear_hotkey(self):
        self.key_sequence = ""
        self.clear()
