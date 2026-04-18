from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
                             QHeaderView, QMessageBox)
from PySide6.QtCore import Qt
from .widgets.hotkey_input import HotkeyInput
from ..settings import Settings

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings()
        self.setWindowTitle("Settings")
        self.resize(500, 600)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Keyboard Shortcuts")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        language_layout = QHBoxLayout()
        language_label = QLabel("UI Language")
        language_layout.addWidget(language_label)
        self.ui_language_combo = QComboBox()
        self.ui_language_combo.addItem("English", "en")
        self.ui_language_combo.addItem("한국어", "ko")
        current_language = self.settings.get_ui_language()
        language_index = self.ui_language_combo.findData(current_language)
        self.ui_language_combo.setCurrentIndex(language_index if language_index >= 0 else 0)
        language_layout.addWidget(self.ui_language_combo, 1)
        layout.addLayout(language_layout)
        
        # Shortcuts Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        
        self.populate_table()
        layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.clicked.connect(self.reset_defaults)
        btn_layout.addWidget(btn_reset)
        
        btn_layout.addStretch()
        
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save_settings)
        btn_save.setStyleSheet("background-color: #0078D4; color: white; font-weight: bold; padding: 6px 12px;")
        btn_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
        
    def populate_table(self):
        self.table.setRowCount(0)
        self.inputs = {}
        
        # Sort actions for better display order
        actions = sorted(self.settings.shortcuts.keys())
        
        # Human readable names mapping
        names = {
            "toggle_recording": "Start/Stop Recording",
            "toggle_play": "Play/Pause",
            "frame_prev": "Previous Frame",
            "frame_next": "Next Frame",
            "frame_start": "Go to Start",
            "frame_end": "Go to End",
            "add_click_step": "Add Click Step",
            "add_text_step": "Add Text Step",
            "delete_step": "Delete Selected Step",
            "save": "Save Tutorial",
            "load": "Load Tutorial",
            "new": "New Tutorial",
            "undo": "Undo",
            "redo": "Redo"
        }
        
        for row, action in enumerate(actions):
            self.table.insertRow(row)
            
            # Action Name
            name_item = QTableWidgetItem(names.get(action, action))
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled) # Read only
            self.table.setItem(row, 0, name_item)
            
            # Hotkey Input
            inp = HotkeyInput()
            inp.set_hotkey(self.settings.shortcuts.get(action, ""))
            self.table.setCellWidget(row, 1, inp)
            self.inputs[action] = inp
            
    def save_settings(self):
        self.settings.set_ui_language(self.ui_language_combo.currentData() or "en")
        for action, inp in self.inputs.items():
            self.settings.shortcuts[action] = inp.key_sequence
            
        self.settings.save()
        self.accept()
        
    def reset_defaults(self):
        if QMessageBox.question(self, "Reset Defaults", "Are you sure you want to reset all shortcuts to default?") == QMessageBox.StandardButton.Yes:
            self.settings.reset_defaults()
            self.populate_table()
