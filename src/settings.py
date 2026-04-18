import json
import os
from PySide6.QtGui import QKeySequence

class Settings:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.settings_file = "settings.json"
        self.ui_language = "en"
        self.shortcuts = {
            "toggle_recording": "Alt+S",
            "toggle_play": "Space",
            "frame_prev": "Left",
            "frame_next": "Right",
            "frame_start": "Home",
            "frame_end": "End",
            "add_click_step": "C", # New
            "add_text_step": "T",  # New
            "delete_step": "Delete",
            "save": "Ctrl+S",
            "load": "Ctrl+O",
            "new": "Ctrl+N",
            "undo": "Ctrl+Z",
            "redo": "Ctrl+Y",
        }
        self.load()

    def load(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "ui_language" in data:
                        self.ui_language = data["ui_language"] or "en"
                    if "shortcuts" in data:
                        self.shortcuts.update(data["shortcuts"])
            except Exception as e:
                print(f"Failed to load settings: {e}")

    def save(self):
        try:
            data = {
                "ui_language": self.ui_language,
                "shortcuts": self.shortcuts
            }
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def get_key(self, action_name):
        """Get QKeySequence for an action."""
        key_str = self.shortcuts.get(action_name, "")
        return QKeySequence(key_str)

    def set_key(self, action_name, key_sequence_str):
        self.shortcuts[action_name] = key_sequence_str
        self.save()

    def get_ui_language(self):
        return self.ui_language or "en"

    def set_ui_language(self, language_code: str):
        self.ui_language = language_code or "en"
        self.save()
        
    def reset_defaults(self):
        self._init()
        self.save()
