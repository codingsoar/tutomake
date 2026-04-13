import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from .key_utils import is_special_key_name, key_code_from_key_name, normalize_key_combo, normalize_key_name

class Step(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    image_path: str = ""
    action_type: str = "click"  # click, keyboard, mouse_drag
    click_button: str = "left"  # left, right, middle
    x: int = 0
    y: int = 0
    width: int = 50  # Default hitbox size
    height: int = 50
    drag_button: str = "left"  # left, right, middle
    drag_end_x: int = 0
    drag_end_y: int = 0
    drag_end_width: int = 50
    drag_end_height: int = 50
    drag_path_tolerance: int = 40
    drag_min_distance: int = 30
    modifier_keys: List[str] = Field(default_factory=list)  # ctrl, shift, alt, cmd, space
    description: str = "Click here"
    instruction: str = ""  # Detailed instruction text for tutorial followers
    shape: str = "rect" # rect, circle
    sound_enabled: bool = True
    timestamp: float = 0.0 # Time in seconds from start of video
    keyboard_input: str = ""  # For keyboard steps: required input text
    keyboard_code: str = ""  # Physical key code for special/key-combo steps
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
        self.modifier_keys = self._normalize_modifier_keys(self.modifier_keys)

        if self.action_type != "keyboard":
            return self

        mode = (self.keyboard_mode or "").strip().lower()
        if mode not in {"text", "key"}:
            mode = "key" if is_special_key_name(self.keyboard_input) else "text"
        self.keyboard_mode = mode
        if self.keyboard_mode == "key" and not self.keyboard_code:
            normalized_input = normalize_key_combo(self.keyboard_input) if "+" in (self.keyboard_input or "") else normalize_key_name(self.keyboard_input)
            main_key = normalized_input.split("+")[-1] if normalized_input else ""
            self.keyboard_code = key_code_from_key_name(main_key)
        return self

    @staticmethod
    def _normalize_modifier_keys(values: List[str]) -> List[str]:
        order = {"ctrl": 0, "shift": 1, "alt": 2, "cmd": 3, "space": 4}
        normalized = []
        for value in values or []:
            key_name = normalize_key_name(value)
            if key_name in order and key_name not in normalized:
                normalized.append(key_name)
        normalized.sort(key=lambda item: order[item])
        return normalized
    
class Tutorial(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Tutorial"
    start_subtitle: str = "인터랙티브 튜토리얼"
    start_button_text: str = "시작하기"
    completion_title: str = "튜토리얼 완료"
    completion_subtitle: str = "모든 단계를 완료했습니다."
    restart_button_text: str = "다시 시작"
    audio_input_device: Optional[int] = None
    audio_input_name: str = "Default Input [Windows Default]"
    video_path: Optional[str] = None
    audio_path: Optional[str] = None      # External audio file path
    audio_offset: float = 0.0              # Audio sync offset in seconds (positive = audio delayed)
    audio_trim_start: float = 0.0          # Trim amount at the start of external audio in seconds
    audio_trim_end: Optional[float] = None # Absolute source end time for trimmed external audio
    steps: List[Step] = []

    def save(self, filepath: str):
        path = Path(filepath)
        if path.suffix.lower() == ".json":
            self._save_json(path)
            return
        self._save_packaged(path)

    @classmethod
    def load(cls, filepath: str) -> "Tutorial":
        path = Path(filepath)
        if zipfile.is_zipfile(path):
            return cls._load_packaged(path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def _save_json(self, filepath: Path):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    def _save_packaged(self, filepath: Path):
        data = self.model_dump()
        asset_entries: list[tuple[Path, str]] = []
        seen_sources: dict[Path, str] = {}

        def add_asset(source_path: Optional[str], archive_prefix: str, fallback_name: str) -> Optional[str]:
            if not source_path:
                return source_path

            source = Path(source_path)
            if not source.exists() or not source.is_file():
                return source_path

            resolved = source.resolve()
            existing_archive_path = seen_sources.get(resolved)
            if existing_archive_path:
                return existing_archive_path

            suffix = source.suffix or ""
            archive_name = f"{archive_prefix}/{fallback_name}{suffix}"
            counter = 1
            used_archive_paths = {archive_path for _, archive_path in asset_entries}
            while archive_name in used_archive_paths:
                archive_name = f"{archive_prefix}/{fallback_name}_{counter}{suffix}"
                counter += 1

            seen_sources[resolved] = archive_name
            asset_entries.append((resolved, archive_name))
            return archive_name

        data["video_path"] = add_asset(data.get("video_path"), "assets/video", "tutorial_video")
        data["audio_path"] = add_asset(data.get("audio_path"), "assets/audio", "tutorial_audio")

        for index, step in enumerate(data.get("steps", []), start=1):
            step["image_path"] = add_asset(
                step.get("image_path"),
                "assets/images",
                f"step_{index:04d}",
            )

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("tutorial.json", json.dumps(data, ensure_ascii=False, indent=2))
            for source, archive_path in asset_entries:
                archive.write(source, archive_path)

    @classmethod
    def _load_packaged(cls, filepath: Path) -> "Tutorial":
        extract_dir = Path(tempfile.gettempdir()) / "tutomake" / "packages" / f"{filepath.stem}_{uuid.uuid4().hex}"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(filepath, "r") as archive:
            archive.extractall(extract_dir)

        manifest_path = extract_dir / "tutorial.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def resolve_asset(asset_path: Optional[str]) -> Optional[str]:
            if not asset_path:
                return asset_path

            candidate = extract_dir / asset_path
            if candidate.exists():
                return str(candidate.resolve())
            return asset_path

        data["video_path"] = resolve_asset(data.get("video_path"))
        data["audio_path"] = resolve_asset(data.get("audio_path"))
        for step in data.get("steps", []):
            step["image_path"] = resolve_asset(step.get("image_path"))

        return cls(**data)
