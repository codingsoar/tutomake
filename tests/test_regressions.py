import os
import shutil
import time
import unittest
import uuid
import wave
import zipfile
from pathlib import Path
from unittest import mock
import base64
import io

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.exporters.package_exporter import PackageExporter
from src.exporters.video_exporter import VideoExporter
from src.exporters.web_exporter import WebExporter
from src.key_utils import display_key_combo, normalize_key_combo
from src.model import Step, Tutorial
from src.recorder import Recorder, get_audio_input_devices, record_test_audio_clip
from src.settings import Settings
from src.ui.editor import Editor
from src.ui.player import Player
from pynput import keyboard


class DummyCharKey:
    def __init__(self, char: str):
        self.char = char
        self.vk = None


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.workspace_tmp_root = Path(__file__).resolve().parent.parent / ".test_tmp"
        cls.workspace_tmp_root.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.app.closeAllWindows()
        cls.app.processEvents()
        cls.app.quit()
        cls.app.processEvents()

    def cleanup_widget(self, widget):
        widget.close()
        widget.deleteLater()
        self.app.processEvents()

    def _make_image(self, path: Path):
        image = np.full((32, 32, 3), 255, dtype=np.uint8)
        ok = cv2.imwrite(str(path), image)
        self.assertTrue(ok)

    def _make_gif(self, path: Path):
        path.write_bytes(
            b"GIF89a"
            b"\x01\x00\x01\x00"
            b"\x80\x00\x00"
            b"\x00\x00\x00"
            b"\xff\xff\xff"
            b"!\xf9\x04\x01\x00\x00\x00\x00"
            b",\x00\x00\x00\x00\x01\x00\x01\x00\x00"
            b"\x02\x02D\x01\x00;"
        )

    def _make_wav(self, path: Path, duration_seconds: float = 1.0, sample_rate: int = 8000):
        frame_count = int(duration_seconds * sample_rate)
        samples = np.full(frame_count, 800, dtype=np.int16)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())

    def _make_video(self, path: Path, frame_count: int = 24, size=(160, 120), fps: float = 12.0):
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(str(path), fourcc, fps, size)
        self.assertTrue(writer.isOpened())
        width, height = size
        for i in range(frame_count):
            frame = np.full((height, width, 3), 245, dtype=np.uint8)
            start_x = 20 + min(i * 4, 60)
            start_y = 30 + min(i * 2, 30)
            cv2.rectangle(frame, (start_x, start_y), (start_x + 26, start_y + 26), (0, 90, 255), -1)
            cv2.rectangle(frame, (90, 70), (118, 98), (0, 220, 120), 2)
            writer.write(frame)
        writer.release()
        self.assertTrue(path.exists())

    def make_tempdir(self) -> Path:
        path = self.workspace_tmp_root / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        return path

    def cleanup_tempdir(self, path: Path):
        shutil.rmtree(path, ignore_errors=True)

    def restore_settings(self, previous_text):
        settings_path = Path("settings.json")
        if previous_text is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(previous_text, encoding="utf-8")
        Settings._instance = None

    def test_export_exe_allows_basename_output_path(self):
        tutorial = Tutorial(title="Export Test")
        exporter = PackageExporter(tutorial)

        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        previous_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            result = exporter.export_exe("demo.exe")
            self.assertTrue(result)
            self.assertTrue((tmpdir / "demo.html").exists())
            self.assertTrue((tmpdir / "demo_launcher.bat").exists())
        finally:
            os.chdir(previous_cwd)

    def test_portable_package_uses_relative_markdown_image_paths(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Portable",
            steps=[Step(description="Click", image_path=str(image_path))],
        )

        output_path = tmpdir / "portable.zip"
        result = PackageExporter(tutorial).create_portable_package(str(output_path))

        self.assertTrue(result)
        import zipfile

        with zipfile.ZipFile(output_path) as zf:
            markdown = zf.read("tutorial.md").decode("utf-8")
            self.assertIn("![Step 1](images/step_001.png)", markdown)
            self.assertIn("images/step_001.png", zf.namelist())

    def test_packaged_tutorial_preserves_guide_character_asset(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "character.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Guide Asset",
            guide_language="en",
            guide_character_image_path=str(image_path),
            guide_character_size=148,
            guide_card_anchor="top_fixed",
            guide_card_offset=22,
            guide_card_top=6,
            guide_card_left=18,
            guide_card_width=720,
            guide_card_scale_percent=125,
            guide_step_badge_size=104,
            guide_card_gap=24,
            guide_card_padding=28,
            guide_card_opacity=61,
        )

        package_path = tmpdir / "guide_asset.tutomake"
        tutorial.save(str(package_path))

        loaded = Tutorial.load(str(package_path))
        self.assertEqual(loaded.guide_language, "en")
        self.assertTrue(loaded.guide_character_image_path)
        self.assertTrue(Path(loaded.guide_character_image_path).exists())
        self.assertEqual(loaded.guide_character_size, 148)
        self.assertEqual(loaded.guide_card_anchor, "top_fixed")
        self.assertEqual(loaded.guide_card_offset, 22)
        self.assertEqual(loaded.guide_card_top, 6)
        self.assertEqual(loaded.guide_card_left, 18)
        self.assertEqual(loaded.guide_card_width, 720)
        self.assertEqual(loaded.guide_card_scale_percent, 125)
        self.assertEqual(loaded.guide_step_badge_size, 104)
        self.assertEqual(loaded.guide_card_gap, 24)
        self.assertEqual(loaded.guide_card_padding, 28)
        self.assertEqual(loaded.guide_card_opacity, 61)

    def test_packaged_tutorial_preserves_step_guide_asset(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "step_character.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Step Guide Asset",
            steps=[Step(description="Click", guide_image_path=str(image_path))],
        )

        package_path = tmpdir / "step_guide_asset.tutomake"
        tutorial.save(str(package_path))

        loaded = Tutorial.load(str(package_path))
        self.assertTrue(loaded.steps[0].guide_image_path)
        self.assertTrue(Path(loaded.steps[0].guide_image_path).exists())

    def test_packaged_tutorial_includes_full_captures_directory_for_recorded_assets(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        captures_dir = tmpdir / "captures"
        captures_dir.mkdir()
        image_path = captures_dir / "step_001.png"
        video_path = captures_dir / "session.mp4"
        extra_path = captures_dir / "unused_reference.txt"
        nested_dir = captures_dir / "sub"
        nested_dir.mkdir()
        nested_extra_path = nested_dir / "notes.bin"

        self._make_image(image_path)
        video_path.write_bytes(b"\x00" * 4096)
        extra_path.write_text("keep me", encoding="utf-8")
        nested_extra_path.write_bytes(b"\x01\x02\x03")

        tutorial = Tutorial(
            title="Recorded Assets",
            video_path=str(video_path),
            steps=[Step(description="Captured", image_path=str(image_path))],
        )

        package_path = tmpdir / "recorded_assets.tutomake"
        tutorial.save(str(package_path))

        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            self.assertTrue(any(name.endswith("/session.mp4") for name in names))
            self.assertTrue(any(name.endswith("/step_001.png") for name in names))
            self.assertTrue(any(name.endswith("/unused_reference.txt") for name in names))
            self.assertTrue(any(name.endswith("/sub/notes.bin") for name in names))

            video_entry = next(name for name in names if name.endswith("/session.mp4"))
            image_entry = next(name for name in names if name.endswith("/step_001.png"))
            self.assertEqual(archive.getinfo(video_entry).compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.getinfo(image_entry).compress_type, zipfile.ZIP_STORED)

        loaded = Tutorial.load(str(package_path))
        self.assertTrue(Path(loaded.video_path).exists())
        self.assertTrue(Path(loaded.steps[0].image_path).exists())

    def test_recorder_flushes_text_buffer_before_special_key_step(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        recorder._on_key_press(DummyCharKey("a"))
        recorder._on_key_press(DummyCharKey("b"))
        recorder._on_key_press(keyboard.Key.tab)

        self.assertEqual(len(tutorial.steps), 2)
        self.assertEqual(tutorial.steps[0].keyboard_input, "ab")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "text")
        self.assertEqual(tutorial.steps[1].keyboard_input, "tab")
        self.assertEqual(tutorial.steps[1].keyboard_mode, "key")

    def test_recorder_creates_new_session_directory_under_captures_root(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir), video_mode=True)

        session_dir = recorder._create_recording_session_dir("20260419_120000_123456")

        self.assertTrue(Path(session_dir).exists())
        self.assertEqual(Path(session_dir).parent, tmpdir)
        self.assertEqual(Path(session_dir).name, "recording_20260419_120000_123456")

    def test_recorder_records_modifier_key_combo_as_key_step(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        ctrl_key = type("CtrlKey", (), {"name": "ctrl_l"})()
        recorder._on_key_press(ctrl_key)
        recorder._on_key_press(DummyCharKey("z"))
        recorder._on_key_release(ctrl_key)

        self.assertEqual(len(tutorial.steps), 1)
        self.assertEqual(tutorial.steps[0].keyboard_input, "ctrl+z")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "key")
        self.assertEqual(tutorial.steps[0].description, "Press Ctrl + Z")

    def test_key_combo_normalizes_control_character_to_letter(self):
        self.assertEqual(normalize_key_combo("ctrl+\x1a"), "ctrl+z")
        self.assertEqual(display_key_combo("ctrl+\x1a"), "Ctrl + Z")

    def test_recorder_records_space_as_special_key_step(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        recorder._on_key_press(keyboard.Key.space)
        recorder._on_key_release(keyboard.Key.space)

        self.assertEqual(len(tutorial.steps), 1)
        self.assertEqual(tutorial.steps[0].keyboard_input, "space")
        self.assertEqual(tutorial.steps[0].keyboard_code, "Space")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "key")

    def test_recorder_records_ctrl_space_as_key_combo(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        ctrl_key = type("CtrlKey", (), {"name": "ctrl_l"})()
        recorder._on_key_press(ctrl_key)
        recorder._on_key_press(keyboard.Key.space)
        recorder._on_key_release(keyboard.Key.space)
        recorder._on_key_release(ctrl_key)

        self.assertEqual(len(tutorial.steps), 1)
        self.assertEqual(tutorial.steps[0].keyboard_input, "ctrl+space")
        self.assertEqual(tutorial.steps[0].keyboard_code, "Space")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "key")
        self.assertEqual(tutorial.steps[0].description, "Press Ctrl + Space")

    def test_recorder_records_enter_as_special_key_step_with_distinct_code(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        recorder._on_key_press(keyboard.Key.enter)

        self.assertEqual(len(tutorial.steps), 1)
        self.assertEqual(tutorial.steps[0].keyboard_input, "enter")
        self.assertEqual(tutorial.steps[0].keyboard_code, "Enter")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "key")

    def test_recorder_space_submits_current_text_step_and_starts_next_one(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        for char in "hello":
            recorder._on_key_press(DummyCharKey(char))
        recorder._on_key_press(keyboard.Key.space)
        for char in "world":
            recorder._on_key_press(DummyCharKey(char))
        recorder._on_key_press(keyboard.Key.enter)

        self.assertEqual(len(tutorial.steps), 2)
        self.assertEqual(tutorial.steps[0].keyboard_input, "hello")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "text")
        self.assertEqual(tutorial.steps[0].keyboard_space_behavior, "submit_step")
        self.assertEqual(tutorial.steps[1].keyboard_input, "world")
        self.assertEqual(tutorial.steps[1].keyboard_mode, "text")
        self.assertEqual(tutorial.steps[1].keyboard_space_behavior, "submit_step")

    def test_recorder_shift_space_inserts_literal_space_inside_text_step(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir))
        recorder.is_recording = True
        recorder.start_time = 0.0
        recorder.frame_count = 24
        recorder.fps = 24.0

        shift_key = type("ShiftKey", (), {"name": "shift"})()
        for char in "hello":
            recorder._on_key_press(DummyCharKey(char))
        recorder._on_key_press(shift_key)
        recorder._on_key_press(keyboard.Key.space)
        recorder._on_key_release(keyboard.Key.space)
        recorder._on_key_release(shift_key)
        for char in "world":
            recorder._on_key_press(DummyCharKey(char))
        recorder._on_key_press(keyboard.Key.enter)

        self.assertEqual(len(tutorial.steps), 1)
        self.assertEqual(tutorial.steps[0].keyboard_input, "hello world")
        self.assertEqual(tutorial.steps[0].keyboard_mode, "text")
        self.assertEqual(tutorial.steps[0].keyboard_space_behavior, "insert_space")

    def test_recorder_keeps_audio_path_when_audio_saved_separately(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir), video_mode=True)
        recorder.audio_path = str(tmpdir / "audio.wav")
        recorder.video_path = str(tmpdir / "video.avi")
        recorder.audio_data = [np.zeros((8, 2), dtype=np.float32)]

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "imageio_ffmpeg":
                raise ImportError("forced for test")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            recorder._save_and_merge_audio()

        self.assertEqual(tutorial.audio_path, recorder.audio_path)
        self.assertTrue(Path(recorder.audio_path).exists())
        with wave.open(recorder.audio_path, "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), recorder.audio_channels)

    def test_recorder_uses_audio_device_defaults_when_available(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()

        with mock.patch("src.recorder.AUDIO_AVAILABLE", True), \
             mock.patch("src.recorder.sd.query_devices", return_value={
                 "max_input_channels": 1,
                 "default_samplerate": 48000,
             }):
            recorder = Recorder(tutorial, str(tmpdir), audio_device=3)

        self.assertEqual(recorder.audio_channels, 1)
        self.assertEqual(recorder.audio_sample_rate, 48000)

    def test_recorder_pads_initial_silence_for_audio_sync(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial()
        recorder = Recorder(tutorial, str(tmpdir), video_mode=True)
        recorder.audio_path = str(tmpdir / "audio_sync.wav")
        recorder.video_path = str(tmpdir / "video.avi")
        recorder.audio_channels = 1
        recorder.audio_sample_rate = 4
        recorder.audio_start_delay = 0.5
        recorder.audio_data = [np.array([[0.5], [0.5]], dtype=np.float32)]

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "imageio_ffmpeg":
                raise ImportError("forced for test")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            recorder._save_and_merge_audio()

        with wave.open(recorder.audio_path, "rb") as wav_file:
            self.assertEqual(wav_file.getnframes(), 4)
            samples = np.frombuffer(wav_file.readframes(4), dtype=np.int16)

        self.assertEqual(samples[0], 0)
        self.assertEqual(samples[1], 0)
        self.assertGreater(samples[2], 0)

    def test_audio_input_devices_are_labeled_and_deduplicated(self):
        fake_devices = [
            {"name": "Microphone (USB Audio Device) (WASAPI)", "max_input_channels": 1},
            {"name": "Microphone (USB Audio Device) (MME)", "max_input_channels": 1},
            {"name": "CABLE Output (VB-Audio Virtual Cable) (WASAPI)", "max_input_channels": 2},
            {"name": "Line In (Focusrite USB) (WASAPI)", "max_input_channels": 2},
        ]

        with mock.patch("src.recorder.AUDIO_AVAILABLE", True), \
             mock.patch("src.recorder.sd.query_devices", return_value=fake_devices), \
             mock.patch("src.recorder.sd.default.device", (0, 1)):
            devices = get_audio_input_devices()

        self.assertEqual(len(devices), 2)
        labels = [device["label"] for device in devices]
        self.assertTrue(any("[Mic, 1 ch]" in label for label in labels))
        self.assertTrue(any("[Line In, 2 ch]" in label for label in labels))

    def test_audio_input_devices_hide_virtual_and_system_capture_when_possible(self):
        fake_devices = [
            {"name": "Input 1 (WASAPI)", "max_input_channels": 2},
            {"name": "CABLE Output (VB-Audio Virtual Cable) (WASAPI)", "max_input_channels": 2},
            {"name": "Stereo Mix (Realtek) (WASAPI)", "max_input_channels": 2},
            {"name": "Line In (Focusrite USB) (WASAPI)", "max_input_channels": 2},
        ]

        with mock.patch("src.recorder.AUDIO_AVAILABLE", True), \
             mock.patch("src.recorder.sd.query_devices", return_value=fake_devices), \
             mock.patch("src.recorder.sd.default.device", (0, 1)):
            devices = get_audio_input_devices()

        self.assertEqual(len(devices), 2)
        self.assertTrue(all(device["kind"] in {"Input", "Line In"} for device in devices))

    def test_record_test_audio_clip_writes_wav_file(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        output_path = tmpdir / "mic_test.wav"
        fake_audio = np.array([[100], [200], [300]], dtype=np.int16)

        with mock.patch("src.recorder.AUDIO_AVAILABLE", True), \
             mock.patch("src.recorder.sd.query_devices", return_value={
                 "max_input_channels": 1,
                 "default_samplerate": 16000,
             }), \
             mock.patch("src.recorder.sd.rec", return_value=fake_audio), \
             mock.patch("src.recorder.sd.wait"):
            success, path = record_test_audio_clip(str(output_path), device=2, duration=0.1)

        self.assertTrue(success)
        self.assertEqual(path, str(output_path))
        with wave.open(str(output_path), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 16000)
            self.assertEqual(wav_file.getnchannels(), 1)

    def test_video_export_builds_mux_command_with_external_audio_offset(self):
        tutorial = Tutorial(title="Export", audio_path="voice.wav", audio_offset=0.5)
        exporter = VideoExporter(tutorial)

        command = exporter._build_audio_mux_command(
            "ffmpeg",
            "overlay.mp4",
            "final.mp4",
            "voice.wav",
            True,
            "mp4",
        )

        command_text = " ".join(command)
        self.assertIn("adelay=500|500", command_text)
        self.assertIn("-map [aout]", command_text)
        self.assertIn("-c:a aac", command_text)

    def test_video_export_builds_mux_command_with_audio_trim(self):
        tutorial = Tutorial(
            title="Export",
            audio_path="voice.wav",
            audio_offset=-0.25,
            audio_trim_start=1.0,
            audio_trim_end=4.5,
        )
        exporter = VideoExporter(tutorial)

        command = exporter._build_audio_mux_command(
            "ffmpeg",
            "overlay.mp4",
            "final.mp4",
            "voice.wav",
            True,
            "mp4",
        )

        command_text = " ".join(command)
        self.assertIn("atrim=start=1.000:end=4.500", command_text)
        self.assertIn("atrim=start=0.250", command_text)

    def test_video_export_builds_mux_command_for_embedded_audio(self):
        tutorial = Tutorial(title="Export")
        exporter = VideoExporter(tutorial)

        command = exporter._build_audio_mux_command(
            "ffmpeg",
            "overlay.mp4",
            "final.mp4",
            "source_with_audio.mp4",
            False,
            "mp4",
        )

        command_text = " ".join(command)
        self.assertIn("-map 1:a:0?", command_text)
        self.assertNotIn("filter_complex", command_text)

    def test_web_export_uses_custom_intro_and_completion_text(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        custom_title = "\ucee4\uc2a4\ud140 \uc81c\ubaa9"
        start_subtitle = "\uc2dc\uc791 \uc548\ub0b4"
        start_button = "\ubc14\ub85c \uc2dc\uc791"
        completion_title = "\uc644\ub8cc \uc81c\ubaa9"
        completion_subtitle = "\uc644\ub8cc \uc548\ub0b4"
        restart_button = "\ucc98\uc74c\ubd80\ud130 \ub2e4\uc2dc"

        tutorial = Tutorial(
            title=custom_title,
            start_subtitle=start_subtitle,
            start_button_text=start_button,
            completion_title=completion_title,
            completion_subtitle=completion_subtitle,
            restart_button_text=restart_button,
            steps=[Step(description="Click", image_path=str(image_path))],
        )

        html_path = tmpdir / "tutorial.html"
        result = WebExporter(tutorial).export_html(str(html_path))

        self.assertTrue(result)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn(custom_title, html)
        self.assertIn(start_subtitle, html)
        self.assertIn(start_button, html)
        self.assertIn(completion_title, html)
        self.assertIn(completion_subtitle, html)
        self.assertIn(restart_button, html)

    def test_web_export_restores_center_prompt_for_special_key_steps(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Special Key Prompt",
            steps=[
                Step(
                    description="Press ESC",
                    instruction="",
                    action_type="keyboard",
                    keyboard_input="esc",
                    keyboard_mode="key",
                    image_path=str(image_path),
                )
            ],
        )

        html_path = tmpdir / "tutorial.html"
        result = WebExporter(tutorial).export_html(str(html_path))

        self.assertTrue(result)
        html = html_path.read_text(encoding="utf-8")
        self.assertIn('"keyboard_code": "Escape"', html)
        self.assertIn("eventMatchesExpectedInput(e, expectedInput, expectedCode)", html)
        self.assertIn('class="modal-copy"', html)
        self.assertIn("const spaceSubmits = (step.keyboard_space_behavior || 'submit_step') === 'submit_step';", html)
        self.assertIn("title: customTitle ? escapeHtml(customTitle) : `${strings.press} <span class=\"guide-accent\">${escapeHtml(comboLabel)}</span>`,", html)
        self.assertIn("body: customInstruction ? escapeHtml(customInstruction) : strings.pressComboBody", html)
        self.assertIn("const defaultSpecialInstruction = isSpecial", html)
        self.assertIn("Press ${formatKeyCombo(expectedInput)} to continue.", html)
        self.assertIn("키를 눌러 다음 단계로 진행하세요.", html)
        self.assertIn("const titleMessage = isSpecial", html)
        self.assertIn("const hintMessage = isSpecial", html)
        self.assertIn("modalTitle.style.display = titleMessage ? 'block' : 'none';", html)
        self.assertIn("modalHint.style.display = hintMessage ? 'block' : 'none';", html)
        self.assertIn("typeBody: 'Type the requested text, then press Enter to submit.'", html)
        self.assertIn("if (e.key === 'Enter' || (spaceSubmits && e.key === ' ')) {", html)

    def test_html_exports_do_not_render_header_instruction_text(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)
        character_path = tmpdir / "character.png"
        self._make_image(character_path)

        tutorial = Tutorial(
            title="No Header Instruction",
            video_path="demo.mp4",
            guide_language="en",
            guide_character_image_path=str(character_path),
            guide_character_size=144,
            guide_card_anchor="top_fixed",
            guide_card_direction="left",
            guide_card_offset=28,
            guide_card_top=8,
            guide_card_left=20,
            guide_card_width=760,
            guide_card_scale_percent=135,
            guide_step_badge_size=108,
            guide_card_gap=26,
            guide_card_padding=30,
            guide_card_opacity=57,
            steps=[
                Step(
                    description="Left click here",
                    instruction="Click with the left mouse button",
                    guide_image_path=str(character_path),
                    action_type="click",
                    image_path=str(image_path),
                    x=10,
                    y=10,
                    width=20,
                    height=20,
                    timestamp=1.0,
                )
            ],
        )

        html_path = tmpdir / "tutorial.html"
        result = WebExporter(tutorial).export_html(str(html_path))

        self.assertTrue(result)
        html = html_path.read_text(encoding="utf-8")
        self.assertNotIn('class="header"', html)
        self.assertIn('id="stepBadge"', html)
        self.assertIn('id="stepDesc"', html)
        self.assertIn('id="stepInstruction"', html)
        self.assertIn("document.getElementById('stepBadge')", html)
        self.assertIn("document.getElementById('stepDesc')", html)
        self.assertIn("document.getElementById('stepInstruction')", html)
        self.assertIn('id="guideOverlay"', html)
        self.assertIn("function getStepGuide(step)", html)
        self.assertIn("showGuide(step);", html)
        self.assertIn('const guideConfig = {"language": "en"', html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn('id="guideCharacter"', html)
        self.assertIn('"cardDirection": "left"', html)
        self.assertIn('"cardOffset": 28', html)
        self.assertIn('"cardAnchor": "top_fixed"', html)
        self.assertIn('"cardTop": 8', html)
        self.assertIn('"cardLeft": 20', html)
        self.assertIn('"cardWidth": 760', html)
        self.assertIn('"cardScale": 135', html)
        self.assertIn('"badgeSize": 108', html)
        self.assertIn('"characterSize": 144', html)
        self.assertIn('"cardGap": 26', html)
        self.assertIn('"cardPadding": 30', html)
        self.assertIn('"cardOpacity": 57', html)
        self.assertIn('"guide_image": "data:image/png;base64,', html)
        self.assertIn("const cardOpacity = Math.min(100, Math.max(0, Number(guideConfig.cardOpacity ?? 94))) / 100;", html)
        self.assertIn("const cardBlur = 18 * cardOpacity;", html)
        self.assertIn("guideCard.style.backdropFilter = cardBlur > 0 ? `blur(${cardBlur.toFixed(2)}px)` : 'none';", html)
        self.assertIn("guideCard.style.borderColor = `rgba(255, 255, 255, ${outlineAlpha.toFixed(3)})`;", html)
        self.assertIn("function positionGuideNearAction(step)", html)
        self.assertIn("const anchorMode = (guideConfig.cardAnchor || 'top_fixed').toLowerCase();", html)
        self.assertIn("if (anchorMode === 'top_fixed') {", html)
        self.assertIn("const cardScale = Math.min(200, Math.max(50, Number(guideConfig.cardScale || 100))) / 100;", html)
        self.assertIn("const baseWidth = Math.max(220, Math.min(fixedWidth, Math.round(availableWidth / Math.max(cardScale, 0.01))));", html)
        self.assertIn("guideOverlay.style.transform = `scale(${cardScale})`;", html)
        self.assertIn("const centeredLeft = Math.round((window.innerWidth - overlayWidth) / 2);", html)
        self.assertIn("const baseTop = 24;", html)
        self.assertIn("guideOverlay.style.width = `${baseWidth}px`;", html)
        self.assertIn("positionGuideNearAction(step);", html)
        self.assertIn("width: min(680px, calc(100vw - 40px));", html)
        self.assertIn("const preferredDirection = (guideConfig.cardDirection || 'auto').toLowerCase();", html)
        self.assertIn("const offset = Math.max(28, Number(guideConfig.cardOffset || 16));", html)
        self.assertIn("return step.guide_image || guideConfig.characterImage || '';", html)
        self.assertIn("title: customTitle ? escapeHtml(customTitle) : fallbackClickTitle,", html)
        self.assertIn("body: customInstruction ? escapeHtml(customInstruction) : (modifierText", html)
        self.assertEqual(html.count("const guideCard = guideOverlay.querySelector('.guide-card');"), 1)
        self.assertIn("stepBadge.textContent = String(step.index || '');", html)
        self.assertIn("stepDesc.innerHTML = guide.title;", html)
        self.assertIn("stepInstruction.innerHTML = guide.body;", html)
        self.assertIn("class=\"guide-step-badge\" id=\"stepBadge\"", html)
        self.assertIn("stepBadge.style.width = `${badgeSize}px`;", html)
        self.assertIn("stepBadge.style.height = `${badgeSize}px`;", html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )
        self.assertNotIn('class="header"', video_html)
        self.assertIn('id="stepBadge"', video_html)
        self.assertIn('id="stepDesc"', video_html)
        self.assertIn('id="stepInstruction"', video_html)
        self.assertIn("document.getElementById('stepBadge')", video_html)
        self.assertIn("document.getElementById('stepDesc')", video_html)
        self.assertIn("document.getElementById('stepInstruction')", video_html)
        self.assertIn('id="guideOverlay"', video_html)
        self.assertIn("function getStepGuide(step)", video_html)
        self.assertIn("showGuide(step);", video_html)
        self.assertIn('const guideConfig = {"language": "en"', video_html)
        self.assertIn("data:image/png;base64,", video_html)
        self.assertIn('id="guideCharacter"', video_html)
        self.assertIn('"cardDirection": "left"', video_html)
        self.assertIn('"cardOffset": 28', video_html)
        self.assertIn('"cardAnchor": "top_fixed"', video_html)
        self.assertIn('"cardTop": 8', video_html)
        self.assertIn('"cardLeft": 20', video_html)
        self.assertIn('"cardWidth": 760', video_html)
        self.assertIn('"cardScale": 135', video_html)
        self.assertIn('"badgeSize": 108', video_html)
        self.assertIn('"characterSize": 144', video_html)
        self.assertIn('"cardGap": 26', video_html)
        self.assertIn('"cardPadding": 30', video_html)
        self.assertIn('"cardOpacity": 57', video_html)
        self.assertIn('"guide_image": "data:image/png;base64,', video_html)
        self.assertIn("const cardOpacity = Math.min(100, Math.max(0, Number(guideConfig.cardOpacity ?? 94))) / 100;", video_html)
        self.assertIn("const cardBlur = 18 * cardOpacity;", video_html)
        self.assertIn("guideCard.style.backdropFilter = cardBlur > 0 ? `blur(${cardBlur.toFixed(2)}px)` : 'none';", video_html)
        self.assertIn("guideCard.style.borderColor = `rgba(255, 255, 255, ${outlineAlpha.toFixed(3)})`;", video_html)
        self.assertIn("function positionGuideNearAction(step)", video_html)
        self.assertIn("const anchorMode = (guideConfig.cardAnchor || 'top_fixed').toLowerCase();", video_html)
        self.assertIn("if (anchorMode === 'top_fixed') {", video_html)
        self.assertIn("const cardScale = Math.min(200, Math.max(50, Number(guideConfig.cardScale || 100))) / 100;", video_html)
        self.assertIn("const baseWidth = Math.max(220, Math.min(fixedWidth, Math.round(availableWidth / Math.max(cardScale, 0.01))));", video_html)
        self.assertIn("guideOverlay.style.transform = `scale(${cardScale})`;", video_html)
        self.assertIn("const centeredLeft = Math.round((window.innerWidth - overlayWidth) / 2);", video_html)
        self.assertIn("const baseTop = 24;", video_html)
        self.assertIn("guideOverlay.style.width = `${baseWidth}px`;", video_html)
        self.assertIn("positionGuideNearAction(step);", video_html)
        self.assertIn("width: min(680px, calc(100vw - 40px));", video_html)
        self.assertIn("const preferredDirection = (guideConfig.cardDirection || 'auto').toLowerCase();", video_html)
        self.assertIn("const offset = Math.max(28, Number(guideConfig.cardOffset || 16));", video_html)
        self.assertIn("return step.guide_image || guideConfig.characterImage || '';", video_html)
        self.assertIn("title: customTitle ? escapeHtml(customTitle) : fallbackClickTitle,", video_html)
        self.assertIn("body: customInstruction ? escapeHtml(customInstruction) : (modifierText", video_html)
        self.assertEqual(video_html.count("const guideCard = guideOverlay.querySelector('.guide-card');"), 1)
        self.assertIn("stepBadge.textContent = String(step.index || '');", video_html)
        self.assertIn("stepDesc.innerHTML = guide.title;", video_html)
        self.assertIn("stepInstruction.innerHTML = guide.body;", video_html)
        self.assertIn("stepBadge.style.width = `${badgeSize}px`;", video_html)
        self.assertIn("stepBadge.style.height = `${badgeSize}px`;", video_html)

    def test_keyboard_steps_use_custom_guide_card_text_and_minimal_input_modal(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Keyboard Guide Card",
            steps=[
                Step(
                    description="Type project name",
                    instruction="Enter the final project title exactly as shown.",
                    action_type="keyboard",
                    keyboard_input="My Project",
                    keyboard_mode="text",
                    image_path=str(image_path),
                )
            ],
        )

        html = WebExporter(tutorial)._generate_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)]
        )
        self.assertIn("title: customTitle ? escapeHtml(customTitle) : `${strings.type} <span class=\"guide-accent\">${escapeHtml(step.keyboard_input || '')}</span>`,", html)
        self.assertIn("body: customInstruction ? escapeHtml(customInstruction) : typeBody", html)
        self.assertIn("const titleMessage = isSpecial", html)
        self.assertIn("const hintMessage = isSpecial", html)
        self.assertIn("modalInputGhost.textContent = step.keyboard_input || '';", html)
        self.assertIn("modalInputGhost.style.display = 'flex';", html)
        self.assertIn("background: rgba(7, 12, 24, 0.20);", html)
        self.assertIn("box-shadow: none;", html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )
        self.assertIn("title: customTitle ? escapeHtml(customTitle) : `${strings.type} <span class=\"guide-accent\">${escapeHtml(step.keyboard_input || '')}</span>`,", video_html)
        self.assertIn("body: customInstruction ? escapeHtml(customInstruction) : typeBody", video_html)
        self.assertIn("const titleMessage = isSpecial", video_html)
        self.assertIn("const hintMessage = isSpecial", video_html)
        self.assertIn("modalInputGhost.textContent = step.keyboard_input || '';", video_html)
        self.assertIn("modalInputGhost.style.display = 'flex';", video_html)
        self.assertIn("background: rgba(7, 12, 24, 0.20);", video_html)
        self.assertIn("box-shadow: none;", video_html)

    def test_keyboard_step_korean_fallback_strings_are_readable_in_export(self):
        tutorial = Tutorial(
            title="Keyboard Korean Strings",
            guide_language="ko",
            steps=[
                Step(
                    description="Press Space",
                    action_type="keyboard",
                    keyboard_input="space",
                    keyboard_mode="key",
                )
            ],
        )

        html = WebExporter(tutorial)._generate_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)]
        )
        self.assertIn("const defaultSpecialInstruction = isSpecial", html)
        self.assertIn("키를 눌러 다음 단계로 진행하세요.", html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )
        self.assertIn("const defaultSpecialInstruction = isSpecial", video_html)
        self.assertIn("키를 눌러 다음 단계로 진행하세요.", video_html)

    def test_drag_step_uses_gif_overlay_instead_of_guide_card(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)
        gif_path = tmpdir / "drag.gif"
        self._make_gif(gif_path)

        tutorial = Tutorial(
            title="Drag Gif Guide",
            video_path="demo.mp4",
            guide_language="en",
            steps=[
                Step(
                    description="Drag to target",
                    instruction="Drag while holding the button down",
                    guide_image_path=str(gif_path),
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=10,
                    y=10,
                    width=30,
                    height=30,
                    drag_end_x=80,
                    drag_end_y=60,
                    drag_end_width=30,
                    drag_end_height=30,
                    timestamp=1.0,
                )
            ],
        )

        html = WebExporter(tutorial)._generate_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)]
        )
        self.assertIn('id="dragGuideOverlay"', html)
        self.assertIn('id="dragGuideMedia"', html)
        self.assertIn("function stepUsesDragGuideGif(step)", html)
        self.assertIn("return step.action_type === 'mouse_drag' && /^data:image\\/gif;base64,/i.test(step.guide_image || '');", html)
        self.assertIn("dragGuideMedia.src = step.guide_image;", html)
        self.assertIn("dragGuideOverlay.classList.remove('hidden');", html)
        self.assertIn("guideOverlay.classList.remove('hidden');", html)
        self.assertIn("function positionDragGuideNearAction(step)", html)
        self.assertIn("const actionLeft = canvasRect.left + (Math.min(step.x, step.drag_end_x) * scale);", html)
        self.assertIn("const sideCandidates = [", html)
        self.assertIn("const verticalCandidates = [", html)
        self.assertIn("const dragDx = (step.drag_end_x + (step.drag_end_width / 2)) - (step.x + (step.width / 2));", html)
        self.assertIn("function candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin)", html)
        self.assertIn("if (a.overlapArea !== b.overlapArea) return a.overlapArea - b.overlapArea;", html)
        self.assertIn("const bestCandidate = rankedCandidates[0] || { left: margin, top: margin };", html)
        self.assertIn(".drag-line::after {", html)
        self.assertIn("border-left: var(--drag-arrow-size, 14px) solid #38bdf8;", html)
        self.assertIn(".drag-line.no-arrow::after {", html)
        self.assertIn("const arrowEnabled = step.drag_direction_arrow_enabled !== false;", html)
        self.assertIn("dragLine.style.setProperty('--drag-arrow-size', `${arrowSize}px`);", html)
        self.assertIn("dragLine.style.width = Math.max(18, Math.hypot(dx, dy) - 8) + 'px';", html)
        self.assertIn("startButton: requiredButton", html)
        self.assertIn('"guide_image": "data:image/gif;base64,', html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )
        self.assertIn('id="dragGuideOverlay"', video_html)
        self.assertIn('id="dragGuideMedia"', video_html)
        self.assertIn("function stepUsesDragGuideGif(step)", video_html)
        self.assertIn("dragGuideMedia.src = step.guide_image;", video_html)
        self.assertIn("dragGuideOverlay.classList.remove('hidden');", video_html)
        self.assertIn("guideOverlay.classList.remove('hidden');", video_html)
        self.assertIn("function positionDragGuideNearAction(step)", video_html)
        self.assertIn("const actionLeft = videoRect.left + (Math.min(step.x, step.drag_end_x) * scaleX);", video_html)
        self.assertIn("const sideCandidates = [", video_html)
        self.assertIn("const verticalCandidates = [", video_html)
        self.assertIn("const dragDx = (step.drag_end_x + (step.drag_end_width / 2)) - (step.x + (step.width / 2));", video_html)
        self.assertIn("function candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin)", video_html)
        self.assertIn("if (a.overlapArea !== b.overlapArea) return a.overlapArea - b.overlapArea;", video_html)
        self.assertIn("const bestCandidate = rankedCandidates[0] || { left: margin, top: margin };", video_html)
        self.assertIn(".drag-line::after {", video_html)
        self.assertIn("border-left: var(--drag-arrow-size, 14px) solid #38bdf8;", video_html)
        self.assertIn(".drag-line.no-arrow::after {", video_html)
        self.assertIn("const arrowEnabled = step.drag_direction_arrow_enabled !== false;", video_html)
        self.assertIn("dragLine.style.setProperty('--drag-arrow-size', `${arrowSize}px`);", video_html)
        self.assertIn("dragLine.style.width = Math.max(18, Math.hypot(dx, dy) - 8) + 'px';", video_html)
        self.assertIn("startButton: requiredButton", video_html)
        self.assertIn('"guide_image": "data:image/gif;base64,', video_html)

    def test_drag_step_auto_generates_gif_from_recorded_video(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        video_path = tmpdir / "drag.avi"
        self._make_image(image_path)
        self._make_video(video_path)

        tutorial = Tutorial(
            title="Auto Drag Gif",
            video_path=str(video_path),
            steps=[
                Step(
                    description="Auto drag",
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=20,
                    y=30,
                    width=26,
                    height=26,
                    drag_end_x=90,
                    drag_end_y=70,
                    drag_end_width=28,
                    drag_end_height=28,
                    timestamp=0.8,
                    drag_start_timestamp=0.8,
                    drag_end_timestamp=1.6,
                    drag_gif_preview_size=312,
                    drag_direction_arrow_size=24,
                )
            ],
        )

        step_data = WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)
        self.assertTrue(step_data["guide_image"].startswith("data:image/gif;base64,"))
        self.assertEqual(step_data["drag_gif_fps"], 8.0)
        self.assertEqual(step_data["drag_gif_preview_size"], 312)
        self.assertEqual(step_data["drag_start_timestamp"], 0.8)
        self.assertEqual(step_data["drag_end_timestamp"], 1.6)
        self.assertEqual(step_data["drag_direction_arrow_size"], 24)
        self.assertTrue(step_data["drag_direction_arrow_enabled"])
        gif_bytes = base64.b64decode(step_data["guide_image"].split(",", 1)[1])
        with Image.open(io.BytesIO(gif_bytes)) as gif_image:
            first_frame = gif_image.convert("RGB")
            self.assertEqual(gif_image.size, (312, 312))
        pixels = np.array(first_frame)
        arrow_mask = (
            (pixels[:, :, 0] >= 210)
            & (pixels[:, :, 1] >= 140)
            & (pixels[:, :, 2] <= 120)
        )
        self.assertTrue(bool(np.count_nonzero(arrow_mask)))

    def test_drag_step_can_disable_direction_arrow_in_generated_gif(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        video_path = tmpdir / "drag.avi"
        self._make_image(image_path)
        self._make_video(video_path)

        tutorial = Tutorial(
            title="No Drag Arrow",
            video_path=str(video_path),
            steps=[
                Step(
                    description="Auto drag no arrow",
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=20,
                    y=30,
                    width=26,
                    height=26,
                    drag_end_x=90,
                    drag_end_y=70,
                    drag_end_width=28,
                    drag_end_height=28,
                    timestamp=0.8,
                    drag_start_timestamp=0.8,
                    drag_end_timestamp=1.6,
                    drag_direction_arrow_enabled=False,
                )
            ],
        )

        step_data = WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)
        self.assertFalse(step_data["drag_direction_arrow_enabled"])

    def test_recorder_drag_step_keeps_start_and_end_timestamps(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial(title="Recorded Drag")
        recorder = Recorder(tutorial, str(tmpdir), video_mode=False)

        recorder._capture_drag_step(100, 120, 180, 200, 1.25, 2.10, "middle", [])

        self.assertEqual(len(tutorial.steps), 1)
        step = tutorial.steps[0]
        self.assertEqual(step.action_type, "mouse_drag")
        self.assertAlmostEqual(step.timestamp, 1.25, places=2)
        self.assertAlmostEqual(step.drag_start_timestamp, 1.25, places=2)
        self.assertAlmostEqual(step.drag_end_timestamp, 2.10, places=2)

    def test_drag_step_can_disable_auto_generated_gif(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        video_path = tmpdir / "drag.avi"
        self._make_image(image_path)
        self._make_video(video_path)

        tutorial = Tutorial(
            title="No Auto Drag Gif",
            video_path=str(video_path),
            steps=[
                Step(
                    description="Auto drag off",
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=20,
                    y=30,
                    width=26,
                    height=26,
                    drag_end_x=90,
                    drag_end_y=70,
                    drag_end_width=28,
                    drag_end_height=28,
                    timestamp=1.1,
                    auto_drag_gif_enabled=False,
                )
            ],
        )

        step_data = WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)
        self.assertEqual(step_data["guide_image"], "")

    def test_editor_updates_drag_panel_settings(self):
        tutorial = Tutorial(
            title="Editor Drag Settings",
            steps=[Step(description="Drag", action_type="mouse_drag")],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)
        editor.refresh()
        editor.set_current_step(0)

        editor.drag_button_combo.setCurrentIndex(editor.drag_button_combo.findData("right"))
        editor.drag_min_distance_spin.setValue(84)
        editor.auto_drag_gif_checkbox.setChecked(False)
        editor.drag_gif_lead_spin.setValue(420)
        editor.drag_gif_tail_spin.setValue(180)
        editor.drag_gif_fps_spin.setValue(12)
        editor.drag_gif_size_spin.setValue(212)
        editor.drag_arrow_enabled_checkbox.setChecked(False)
        editor.drag_arrow_enabled_checkbox.setChecked(True)
        editor.drag_arrow_size_spin.setValue(22)
        editor.update_drag_gif_timing()

        step = tutorial.steps[0]
        self.assertTrue(editor.drag_button_combo.isEnabled())
        self.assertTrue(editor.drag_min_distance_spin.isEnabled())
        self.assertEqual(step.drag_button, "right")
        self.assertEqual(step.drag_min_distance, 84)
        self.assertFalse(step.auto_drag_gif_enabled)
        self.assertAlmostEqual(step.drag_gif_lead_seconds, 0.42, places=2)
        self.assertAlmostEqual(step.drag_gif_tail_seconds, 0.18, places=2)
        self.assertEqual(step.drag_gif_fps, 12.0)
        self.assertEqual(step.drag_gif_preview_size, 212)
        self.assertTrue(step.drag_direction_arrow_enabled)
        self.assertEqual(step.drag_direction_arrow_size, 22)

    def test_drag_export_shows_post_drag_state_before_advancing(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        video_path = tmpdir / "drag.avi"
        self._make_image(image_path)
        self._make_video(video_path)

        tutorial = Tutorial(
            title="Post Drag Screen",
            video_path=str(video_path),
            steps=[
                Step(
                    description="Drag to target",
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=20,
                    y=30,
                    width=26,
                    height=26,
                    drag_end_x=90,
                    drag_end_y=70,
                    drag_end_width=28,
                    drag_end_height=28,
                    timestamp=0.8,
                    drag_start_timestamp=0.8,
                    drag_end_timestamp=1.6,
                )
            ],
        )

        html = WebExporter(tutorial)._generate_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0) | {"image": "data:image/jpeg;base64,aaa", "post_drag_image": "data:image/jpeg;base64,bbb"}]
        )
        self.assertIn("function showPostDragState(step, onDone)", html)
        self.assertIn("if (step.post_drag_image) {", html)
        self.assertIn("stepImage.src = step.post_drag_image;", html)
        self.assertIn("showPostDragState(step, () => nextStep());", html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            str(video_path),
        )
        self.assertIn("function showPostDragState(step, onDone)", video_html)
        self.assertIn("const targetTime = Math.max(", video_html)
        self.assertIn("Number(step.drag_end_timestamp || step.timestamp || 0)", video_html)
        self.assertIn("video.currentTime = targetTime;", video_html)
        self.assertIn("showPostDragState(step, () => nextStep());", video_html)

    def test_editor_updates_guide_card_settings(self):
        tutorial = Tutorial(title="Editor Guide Settings")
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.guide_language_combo.setCurrentIndex(editor.guide_language_combo.findData("en"))
        editor.guide_character_size_spin.setValue(156)
        editor.guide_card_anchor_combo.setCurrentIndex(editor.guide_card_anchor_combo.findData("top_fixed"))
        editor.guide_card_direction_combo.setCurrentIndex(editor.guide_card_direction_combo.findData("left"))
        editor.guide_card_offset_spin.setValue(34)
        editor.guide_card_top_spin.setValue(-6)
        editor.guide_card_left_spin.setValue(18)
        editor.guide_card_width_spin.setValue(740)
        editor.guide_card_scale_spin.setValue(140)
        editor.guide_step_badge_size_spin.setValue(102)
        editor.guide_card_gap_spin.setValue(20)
        editor.guide_card_padding_spin.setValue(32)
        editor.guide_card_opacity_spin.setValue(45)
        editor.update_export_text_fields()

        self.assertEqual(tutorial.guide_language, "en")
        self.assertEqual(tutorial.guide_character_size, 156)
        self.assertEqual(tutorial.guide_card_anchor, "top_fixed")
        self.assertEqual(tutorial.guide_card_direction, "left")
        self.assertEqual(tutorial.guide_card_offset, 34)
        self.assertEqual(tutorial.guide_card_top, -6)
        self.assertEqual(tutorial.guide_card_left, 18)
        self.assertEqual(tutorial.guide_card_width, 740)
        self.assertEqual(tutorial.guide_card_scale_percent, 140)
        self.assertEqual(tutorial.guide_step_badge_size, 102)
        self.assertEqual(tutorial.guide_card_gap, 20)
        self.assertEqual(tutorial.guide_card_padding, 32)
        self.assertEqual(tutorial.guide_card_opacity, 45)

    def test_editor_updates_keyboard_space_behavior_for_text_steps(self):
        tutorial = Tutorial(
            title="Keyboard Space Behavior",
            steps=[
                Step(
                    description="Type text",
                    action_type="keyboard",
                    keyboard_mode="text",
                    keyboard_input="hello world",
                )
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.set_current_step(0)
        editor.keyboard_space_behavior_combo.setCurrentIndex(
            editor.keyboard_space_behavior_combo.findData("submit_step")
        )

        self.assertEqual(tutorial.steps[0].keyboard_space_behavior, "submit_step")
        self.assertTrue(editor.keyboard_space_behavior_combo.isEnabled())

    def test_editor_retranslates_properties_panel_from_settings_language(self):
        settings_path = Path("settings.json")
        previous_settings = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
        self.addCleanup(self.restore_settings, previous_settings)
        Settings._instance = None

        settings = Settings()
        settings.set_ui_language("ko")

        tutorial = Tutorial(title="Localized Editor")
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        self.assertEqual(editor.props_dock.windowTitle(), "속성")
        self.assertEqual(editor.property_label_widgets["description"].text(), "설명:")
        self.assertEqual(editor.property_sections["guide_card"]["widget"].title(), "가이드 카드")
        self.assertEqual(editor.keyboard_mode_combo.itemText(0), "텍스트 입력")

    def test_editor_keyboard_input_change_refreshes_key_code(self):
        tutorial = Tutorial(
            title="Keyboard Code Refresh",
            steps=[
                Step(
                    description="Press Enter",
                    action_type="keyboard",
                    keyboard_input="enter",
                    keyboard_mode="key",
                )
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.set_current_step(0)
        editor.text_content.setText("space")
        editor.save_state()

        self.assertEqual(tutorial.steps[0].keyboard_input, "space")
        self.assertEqual(tutorial.steps[0].keyboard_code, "Space")
        self.assertEqual(tutorial.steps[0].description, "Press Space")

    def test_editor_text_mode_treats_enter_as_literal_text(self):
        tutorial = Tutorial(
            title="Literal Enter",
            steps=[
                Step(
                    description="Press Enter",
                    action_type="keyboard",
                    keyboard_input="enter",
                    keyboard_mode="key",
                )
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.set_current_step(0)
        editor.keyboard_mode_combo.setCurrentIndex(editor.keyboard_mode_combo.findData("text"))
        editor.text_content.setText("enter")
        editor.save_state()

        step = tutorial.steps[0]
        self.assertEqual(step.keyboard_mode, "text")
        self.assertEqual(step.keyboard_input, "enter")
        self.assertEqual(step.keyboard_code, "")
        self.assertFalse(Player(tutorial)._is_special_keyboard_step(step))

        html = WebExporter(tutorial)._generate_html([WebExporter(tutorial)._serialize_step(step, 0)])
        self.assertIn("const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);", html)
        self.assertIn("eyebrow: strings.typingStep", html)

    def test_legacy_keyboard_step_without_mode_is_inferred_as_special_key(self):
        legacy_step = Step.model_validate(
            {
                "action_type": "keyboard",
                "keyboard_input": "enter",
                "description": "Press Enter",
            }
        )
        self.assertEqual(legacy_step.keyboard_mode, "key")

    def test_drag_preview_generation_runs_asynchronously(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        video_path = tmpdir / "drag.avi"
        self._make_image(image_path)
        self._make_video(video_path)

        tutorial = Tutorial(
            title="Async Drag Preview",
            video_path=str(video_path),
            steps=[
                Step(
                    description="Drag preview",
                    action_type="mouse_drag",
                    image_path=str(image_path),
                    x=20,
                    y=30,
                    width=26,
                    height=26,
                    drag_end_x=90,
                    drag_end_y=70,
                    drag_end_width=28,
                    drag_end_height=28,
                    timestamp=0.8,
                    drag_start_timestamp=0.8,
                    drag_end_timestamp=1.6,
                )
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.refresh()
        editor.set_current_step(0)
        editor._clear_drag_gif_preview("")
        editor._update_drag_gif_preview(tutorial.steps[0])
        self.assertEqual(editor.drag_gif_preview.text(), "Generating drag GIF preview...")

        for _ in range(50):
            self.app.processEvents()
            if editor.drag_gif_preview.movie() is not None:
                break
            time.sleep(0.02)

        self.assertIsNotNone(editor.drag_gif_preview.movie())

    def test_editor_font_weight_updates_keyboard_text_style(self):
        tutorial = Tutorial(
            title="Font Weight",
            steps=[
                Step(
                    description="Type text",
                    action_type="keyboard",
                    keyboard_mode="text",
                    keyboard_input="hello",
                )
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.set_current_step(0)
        editor.font_weight_combo.setCurrentIndex(editor.font_weight_combo.findData("Bold"))

        self.assertEqual(tutorial.steps[0].text_font_weight, "bold")

    def test_export_guide_card_respects_keyboard_mode_for_literal_text(self):
        tutorial = Tutorial(
            title="Literal Export Text",
            steps=[
                Step(
                    description="Type literal enter",
                    action_type="keyboard",
                    keyboard_mode="text",
                    keyboard_input="enter",
                )
            ],
        )

        html = WebExporter(tutorial)._generate_html([WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)])
        self.assertIn("const usesLegacyInference = !step.keyboard_mode;", html)
        self.assertIn("const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);", html)

    def test_player_distinguishes_space_and_enter_for_special_key_steps(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="Space vs Enter",
            steps=[
                Step(
                    description="Press Space",
                    action_type="keyboard",
                    keyboard_input="space",
                    keyboard_code="Space",
                    keyboard_mode="key",
                    sound_enabled=False,
                    image_path=str(image_path),
                )
            ],
        )
        player = Player(tutorial, video_mode=False)
        self.addCleanup(self.cleanup_widget, player)
        player.waiting_for_click = True

        enter_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        space_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")

        with mock.patch.object(player, "_complete_current_step") as complete_step:
            self.assertFalse(player._handle_step_key_press(enter_event))
            complete_step.assert_not_called()

        with mock.patch.object(player, "_complete_current_step") as complete_step:
            self.assertTrue(player._handle_step_key_press(space_event))
            complete_step.assert_called_once()

    def test_video_html_export_includes_safe_resume_and_right_click_handler(self):
        tutorial = Tutorial(
            title="Video HTML",
            video_path="demo.mp4",
            steps=[
                Step(
                    description="Right click",
                    action_type="click",
                    click_button="right",
                    x=10,
                    y=10,
                    width=20,
                    height=20,
                    timestamp=1.0,
                )
            ],
        )

        html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )

        self.assertIn("function safePlayMedia()", html)
        self.assertIn("hitbox.addEventListener('contextmenu'", html)
        self.assertIn("safePlayMedia();", html)

    def test_editor_import_image_sequence_creates_screenshot_steps(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        first = tmpdir / "first.png"
        second = tmpdir / "second.png"
        self._make_image(first)
        self._make_image(second)

        tutorial = Tutorial(
            title="Import Images",
            video_path=str(tmpdir / "old_video.mp4"),
            audio_path=str(tmpdir / "old_audio.wav"),
            steps=[Step(description="Old", timestamp=3.0)],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        imported_count = editor.import_image_sequence([str(first), str(second)])

        self.assertEqual(imported_count, 2)
        self.assertIsNone(editor.tutorial.video_path)
        self.assertIsNone(editor.tutorial.audio_path)
        self.assertEqual(len(editor.tutorial.steps), 2)
        self.assertEqual(editor.tutorial.steps[0].image_path, str(first))
        self.assertEqual(editor.tutorial.steps[1].image_path, str(second))
        self.assertEqual(editor.tutorial.steps[0].timestamp, 0.0)
        self.assertEqual(editor.tutorial.steps[1].timestamp, 1.0)
        self.assertEqual(editor.view_mode, "screenshot")
        self.assertEqual(editor.step_list.count(), 2)

    def test_editor_undo_restores_audio_state(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial(title="Editor")
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        tutorial.audio_path = str(tmpdir / "narration.wav")
        tutorial.audio_offset = 1.5
        tutorial.audio_trim_start = 0.5
        tutorial.audio_trim_end = 2.5
        editor.save_state()

        tutorial.audio_path = None
        tutorial.audio_offset = 0.0
        tutorial.audio_trim_start = 0.0
        tutorial.audio_trim_end = None
        editor.save_state()
        editor.undo()

        self.assertEqual(editor.tutorial.audio_path, str(tmpdir / "narration.wav"))
        self.assertEqual(editor.tutorial.audio_offset, 1.5)
        self.assertEqual(editor.tutorial.audio_trim_start, 0.5)
        self.assertEqual(editor.tutorial.audio_trim_end, 2.5)
        self.assertEqual(editor.audio_file_label.text(), "narration.wav")
        self.assertEqual(editor.audio_offset_slider.value(), 15)

    def test_editor_set_tutorial_resets_history_and_syncs_audio_ui(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        editor = Editor(Tutorial(title="First"))
        self.addCleanup(self.cleanup_widget, editor)

        editor.tutorial.audio_path = str(tmpdir / "old.wav")
        editor.tutorial.audio_offset = -0.5
        editor.save_state()

        new_tutorial = Tutorial(
            title="Second",
            audio_path=str(tmpdir / "new.wav"),
            audio_offset=2.0,
        )
        editor.set_tutorial(new_tutorial)

        self.assertEqual(len(editor.history_stack), 1)
        self.assertEqual(editor.history_index, 0)
        self.assertEqual(editor.audio_file_label.text(), "new.wav")
        self.assertEqual(editor.audio_offset_slider.value(), 20)
        self.assertEqual(editor.audio_offset_label.text(), "+2.0s")

    def test_editor_timeline_audio_offset_preview_syncs_slider_and_model(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial(
            title="Audio Timeline",
            video_path=str(tmpdir / "video.mp4"),
            audio_path=str(tmpdir / "voice.wav"),
            audio_offset=0.0,
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.preview_audio_offset_from_timeline(-1.3)

        self.assertAlmostEqual(editor.tutorial.audio_offset, -1.3)
        self.assertEqual(editor.audio_offset_slider.value(), -13)
        self.assertEqual(editor.audio_offset_label.text(), "-1.3s")

    def test_timeline_snap_time_depends_on_zoom_level(self):
        editor = Editor(Tutorial(title="Snap"))
        self.addCleanup(self.cleanup_widget, editor)

        editor.timeline.zoom_scale = 4.0
        self.assertAlmostEqual(editor.timeline.snap_time(1.23), 1.2)

        editor.timeline.zoom_scale = 0.6
        self.assertAlmostEqual(editor.timeline.snap_time(1.23), 1.0)

    def test_timeline_snap_can_be_temporarily_disabled(self):
        editor = Editor(Tutorial(title="Snap Off"))
        self.addCleanup(self.cleanup_widget, editor)

        editor.timeline.zoom_scale = 4.0
        editor.timeline.snap_temporarily_disabled = True
        self.assertAlmostEqual(editor.timeline.snap_time(1.23), 1.23)
        editor.timeline.snap_temporarily_disabled = False

    def test_timeline_audio_handles_are_created_with_audio_clip(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial(
            title="Audio Handles",
            video_path=str(tmpdir / "video.mp4"),
            audio_path=str(tmpdir / "voice.wav"),
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.timeline.set_tutorial(tutorial)
        editor.timeline.rebuild_scene()

        self.assertEqual(len(editor.timeline.audio_handle_items), 2)

    def test_timeline_audio_duration_respects_trimmed_wav_range(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        audio_path = tmpdir / "voice.wav"
        self._make_wav(audio_path, duration_seconds=4.0)
        tutorial = Tutorial(
            title="Audio Trim",
            video_path=str(tmpdir / "video.mp4"),
            audio_path=str(audio_path),
            audio_trim_start=0.5,
            audio_trim_end=2.0,
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)
        editor.timeline.set_tutorial(tutorial)

        self.assertAlmostEqual(editor.timeline.get_audio_source_duration(), 4.0)
        self.assertAlmostEqual(editor.timeline.get_effective_audio_duration(), 1.5)

    def test_editor_audio_trim_preview_updates_offset_label(self):
        tutorial = Tutorial(
            title="Trim Preview",
            audio_offset=1.2,
            audio_trim_start=0.4,
            audio_trim_end=1.8,
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.preview_audio_trim_from_timeline()

        self.assertEqual(editor.audio_offset_label.text(), "+1.2s  Trim 0.4s-1.8s")

    def test_editor_ripple_delete_shifts_later_steps_and_clears_range(self):
        tutorial = Tutorial(
            title="Ripple",
            steps=[
                Step(description="A", timestamp=1.0),
                Step(description="B", timestamp=3.0),
                Step(description="C", timestamp=5.0),
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.timeline.current_position = 2.0
        editor.timeline.mark_range_start()
        editor.timeline.current_position = 4.0
        editor.timeline.mark_range_end()
        editor.delete_selected_range(True)

        self.assertEqual(len(editor.tutorial.steps), 2)
        self.assertEqual(editor.tutorial.steps[0].description, "A")
        self.assertAlmostEqual(editor.tutorial.steps[0].timestamp, 1.0)
        self.assertEqual(editor.tutorial.steps[1].description, "C")
        self.assertAlmostEqual(editor.tutorial.steps[1].timestamp, 3.0)
        self.assertIsNone(editor.timeline.get_edit_range())

    def test_editor_split_at_playhead_duplicates_selected_step(self):
        tutorial = Tutorial(
            title="Split",
            steps=[
                Step(description="A", timestamp=1.0),
                Step(description="B", timestamp=3.0),
            ],
        )
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        editor.set_current_step(1)
        editor.timeline.current_position = 2.2
        editor.split_at_playhead()

        self.assertEqual(len(editor.tutorial.steps), 3)
        timestamps = [step.timestamp for step in editor.tutorial.steps]
        self.assertIn(2.2, timestamps)
        split_step = next(step for step in editor.tutorial.steps if abs(step.timestamp - 2.2) < 1e-9)
        self.assertEqual(split_step.description, "B")


if __name__ == "__main__":
    unittest.main()
