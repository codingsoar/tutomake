import json
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from .key_utils import is_special_key_name

class Step(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    image_path: str = ""
    action_type: str = "click"  # click, keyboard
    click_button: str = "left"  # left, right, middle
    x: int = 0
    y: int = 0
    width: int = 50  # Default hitbox size
    height: int = 50
    description: str = "Click here"
    instruction: str = ""  # Detailed instruction text for tutorial followers
    shape: str = "rect" # rect, circle
    sound_enabled: bool = True
    timestamp: float = 0.0 # Time in seconds from start of video
    keyboard_input: str = ""  # For keyboard steps: required input text
    keyboard_mode: str = "text"  # text, key
    # Text style settings
    text_font_size: int = 24
    text_color: str = "#FFFFFF"
    text_bg_color: str = "#000000"
    # Hitbox style settings
    hitbox_line_width: int = 2          # Line thickness (1-10)
    hitbox_line_style: str = "solid"    # solid, dashed, dotted
    hitbox_line_color: str = "#FF0000"  # Line color (hex)
    hitbox_fill_color: str = "#FF0000"   # Background color (hex RGB)
    hitbox_fill_opacity: int = 20        # Fill opacity (0-100%)

    @model_validator(mode="after")
    def normalize_keyboard_mode(self):
        if self.action_type != "keyboard":
            return self

        mode = (self.keyboard_mode or "").strip().lower()
        if mode not in {"text", "key"}:
            mode = "key" if is_special_key_name(self.keyboard_input) else "text"
        self.keyboard_mode = mode
        return self
    
class Tutorial(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Tutorial"
    start_subtitle: str = "인터랙티브 튜토리얼"
    start_button_text: str = "시작하기"
    completion_title: str = "튜토리얼 완료"
    completion_subtitle: str = "모든 단계를 완료했습니다."
    restart_button_text: str = "다시 시작"
    video_path: Optional[str] = None
    audio_path: Optional[str] = None      # External audio file path
    audio_offset: float = 0.0              # Audio sync offset in seconds (positive = audio delayed)
    steps: List[Step] = []

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, filepath: str) -> "Tutorial":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
