import json
import os
import tempfile
import uuid
import zipfile
import hashlib
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from .key_utils import is_special_key_name, key_code_from_key_name, normalize_key_combo, normalize_key_name

class Step(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    image_path: str = ""
    guide_image_path: str = ""
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
    drag_start_timestamp: float = 0.0
    drag_end_timestamp: float = 0.0
    auto_drag_gif_enabled: bool = True
    drag_gif_lead_seconds: float = 0.6
    drag_gif_tail_seconds: float = 0.15
    drag_gif_fps: float = 8.0
    drag_gif_preview_size: int = 260
    drag_direction_arrow_enabled: bool = True
    drag_direction_arrow_size: int = 16
    modifier_keys: List[str] = Field(default_factory=list)  # ctrl, shift, alt, cmd, space
    description: str = "Click here"
    instruction: str = ""  # Detailed instruction text for tutorial followers
    shape: str = "rect" # rect, circle
    sound_enabled: bool = True
    timestamp: float = 0.0 # Time in seconds from start of video
    keyboard_input: str = ""  # For keyboard steps: required input text
    keyboard_code: str = ""  # Physical key code for special/key-combo steps
    keyboard_mode: str = "text"  # text, key
    keyboard_space_behavior: str = "submit_step"  # insert_space, submit_step
    # Text style settings
    text_font_size: int = 24
    text_font_weight: str = "normal"
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

        fields_set = getattr(self, "model_fields_set", set())
        mode = (self.keyboard_mode or "").strip().lower()
        if mode not in {"text", "key"} or "keyboard_mode" not in fields_set:
            mode = "key" if is_special_key_name(self.keyboard_input) else "text"
        self.keyboard_mode = mode
        space_behavior = (self.keyboard_space_behavior or "").strip().lower()
        if space_behavior not in {"insert_space", "submit_step"}:
            space_behavior = "submit_step"
        self.keyboard_space_behavior = space_behavior
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
    guide_language: str = "ko"
    guide_character_image_path: str = ""
    guide_character_size: int = 112
    guide_card_anchor: str = "top_fixed"
    guide_card_direction: str = "auto"
    guide_card_offset: int = 16
    guide_card_top: int = 0
    guide_card_left: int = 0
    guide_card_width: int = 680
    guide_card_scale_percent: int = 100
    guide_step_badge_size: int = 96
    guide_card_gap: int = 18
    guide_card_padding: int = 22
    guide_card_opacity: int = 94
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
        asset_entries: list[tuple[Path, str, int]] = []
        seen_sources: dict[Path, str] = {}
        capture_roots: dict[Path, str] = {}

        def find_capture_root(source: Path) -> Optional[Path]:
            for parent in [source.parent, *source.parents]:
                if parent.name.lower() == "captures":
                    return parent
            return None

        def find_capture_session_root(source: Path) -> Optional[Path]:
            capture_root = find_capture_root(source)
            if capture_root is None:
                return None

            resolved_capture_root = capture_root.resolve()
            resolved_source = source.resolve()
            try:
                relative_parts = resolved_source.relative_to(resolved_capture_root).parts
            except ValueError:
                return None

            if not relative_parts:
                return None

            if len(relative_parts) == 1:
                return resolved_source.parent

            return resolved_capture_root / relative_parts[0]

        def compression_for_path(source: Path) -> int:
            media_suffixes = {
                ".avi", ".mp4", ".mov", ".mkv", ".webm", ".gif",
                ".wav", ".mp3", ".m4a", ".aac", ".flac",
                ".png", ".jpg", ".jpeg", ".webp", ".bmp",
            }
            if source.suffix.lower() in media_suffixes:
                return zipfile.ZIP_STORED
            return zipfile.ZIP_DEFLATED

        def register_asset(source: Path, archive_name: str, compress_type: Optional[int] = None) -> str:
            resolved = source.resolve()
            existing_archive_path = seen_sources.get(resolved)
            if existing_archive_path:
                return existing_archive_path

            used_archive_paths = {archive_path for _, archive_path, _ in asset_entries}
            candidate = archive_name.replace("\\", "/")
            stem = Path(candidate).stem
            suffix = Path(candidate).suffix
            parent = Path(candidate).parent.as_posix()
            counter = 1
            while candidate in used_archive_paths:
                filename = f"{stem}_{counter}{suffix}"
                candidate = f"{parent}/{filename}" if parent and parent != "." else filename
                counter += 1

            seen_sources[resolved] = candidate
            asset_entries.append((resolved, candidate, compress_type or compression_for_path(resolved)))
            return candidate

        def add_asset(source_path: Optional[str], archive_prefix: str, fallback_name: str) -> Optional[str]:
            if not source_path:
                return source_path

            source = Path(source_path)
            if not source.exists() or not source.is_file():
                return source_path

            resolved = source.resolve()
            capture_root = find_capture_session_root(resolved)
            if capture_root is not None and capture_root.exists():
                archive_prefix_for_root = capture_roots.get(capture_root)
                if archive_prefix_for_root is None:
                    capture_hash = hashlib.sha1(str(capture_root).encode("utf-8")).hexdigest()[:10]
                    archive_prefix_for_root = f"assets/captures/{capture_root.name}_{capture_hash}"
                    capture_roots[capture_root] = archive_prefix_for_root
                    resolved_root = capture_root.resolve()
                    for capture_file in sorted(capture_root.rglob("*")):
                        if not capture_file.is_file():
                            continue
                        relative_path = capture_file.resolve().relative_to(resolved_root).as_posix()
                        register_asset(
                            capture_file,
                            f"{archive_prefix_for_root}/{relative_path}",
                            compress_type=zipfile.ZIP_STORED,
                        )
                return seen_sources.get(resolved, source_path)

            suffix = source.suffix or ""
            archive_name = f"{archive_prefix}/{fallback_name}{suffix}"
            return register_asset(source, archive_name)

        data["video_path"] = add_asset(data.get("video_path"), "assets/video", "tutorial_video")
        data["audio_path"] = add_asset(data.get("audio_path"), "assets/audio", "tutorial_audio")
        data["guide_character_image_path"] = add_asset(
            data.get("guide_character_image_path"),
            "assets/ui",
            "guide_character",
        )

        for index, step in enumerate(data.get("steps", []), start=1):
            step["image_path"] = add_asset(
                step.get("image_path"),
                "assets/images",
                f"step_{index:04d}",
            )
            step["guide_image_path"] = add_asset(
                step.get("guide_image_path"),
                "assets/ui",
                f"step_guide_{index:04d}",
            )

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr(
                "tutorial.json",
                json.dumps(data, ensure_ascii=False, indent=2),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            for source, archive_path, compress_type in asset_entries:
                archive.write(source, archive_path, compress_type=compress_type)

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
        data["guide_character_image_path"] = resolve_asset(data.get("guide_character_image_path"))
        for step in data.get("steps", []):
            step["image_path"] = resolve_asset(step.get("image_path"))
            step["guide_image_path"] = resolve_asset(step.get("guide_image_path"))

        return cls(**data)
