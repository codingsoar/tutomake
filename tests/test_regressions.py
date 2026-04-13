import os
import shutil
import unittest
import uuid
import wave
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.exporters.package_exporter import PackageExporter
from src.exporters.video_exporter import VideoExporter
from src.exporters.web_exporter import WebExporter
from src.key_utils import display_key_combo, normalize_key_combo
from src.model import Step, Tutorial
from src.recorder import Recorder, get_audio_input_devices, record_test_audio_clip
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

    def _make_wav(self, path: Path, duration_seconds: float = 1.0, sample_rate: int = 8000):
        frame_count = int(duration_seconds * sample_rate)
        samples = np.full(frame_count, 800, dtype=np.int16)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())

    def make_tempdir(self) -> Path:
        path = self.workspace_tmp_root / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        return path

    def cleanup_tempdir(self, path: Path):
        shutil.rmtree(path, ignore_errors=True)

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

    def test_web_export_shows_default_prompt_for_special_key_steps(self):
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
        self.assertIn("const defaultSpecialInstruction = isSpecial ? `${expectedInput.toUpperCase()}", html)
        self.assertIn("const modalMessage = customInstruction || defaultSpecialInstruction;", html)
        self.assertIn("eventMatchesExpectedInput(e, expectedInput, expectedCode)", html)

    def test_html_exports_do_not_render_header_instruction_text(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        image_path = tmpdir / "source.png"
        self._make_image(image_path)

        tutorial = Tutorial(
            title="No Header Instruction",
            video_path="demo.mp4",
            steps=[
                Step(
                    description="Left click here",
                    instruction="Click with the left mouse button",
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
        self.assertNotIn('id="stepBadge"', html)
        self.assertNotIn('id="stepDesc"', html)
        self.assertNotIn('id="stepInstruction"', html)
        self.assertNotIn("document.getElementById('stepBadge')", html)
        self.assertNotIn("document.getElementById('stepDesc')", html)
        self.assertNotIn("document.getElementById('stepInstruction')", html)

        video_html = WebExporter(tutorial)._generate_video_html(
            [WebExporter(tutorial)._serialize_step(tutorial.steps[0], 0)],
            "demo.mp4",
        )
        self.assertNotIn('class="header"', video_html)
        self.assertNotIn('id="stepBadge"', video_html)
        self.assertNotIn('id="stepDesc"', video_html)
        self.assertNotIn('id="stepInstruction"', video_html)
        self.assertNotIn("document.getElementById('stepBadge')", video_html)
        self.assertNotIn("document.getElementById('stepDesc')", video_html)
        self.assertNotIn("document.getElementById('stepInstruction')", video_html)

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
