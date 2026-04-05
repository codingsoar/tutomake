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
from PySide6.QtWidgets import QApplication

from src.exporters.package_exporter import PackageExporter
from src.exporters.web_exporter import WebExporter
from src.key_utils import display_key_combo, normalize_key_combo
from src.model import Step, Tutorial
from src.recorder import Recorder
from src.ui.editor import Editor
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
        self.assertEqual(tutorial.steps[0].keyboard_mode, "key")
        self.assertEqual(tutorial.steps[0].description, "Press Ctrl + Space")

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
        self.assertIn("const defaultSpecialInstruction = isSpecial ? `${expectedInput.toUpperCase()}", html)
        self.assertIn("const modalMessage = customInstruction || defaultSpecialInstruction;", html)

    def test_editor_undo_restores_audio_state(self):
        tmpdir = self.make_tempdir()
        self.addCleanup(self.cleanup_tempdir, tmpdir)
        tutorial = Tutorial(title="Editor")
        editor = Editor(tutorial)
        self.addCleanup(self.cleanup_widget, editor)

        tutorial.audio_path = str(tmpdir / "narration.wav")
        tutorial.audio_offset = 1.5
        editor.save_state()

        tutorial.audio_path = None
        tutorial.audio_offset = 0.0
        editor.save_state()
        editor.undo()

        self.assertEqual(editor.tutorial.audio_path, str(tmpdir / "narration.wav"))
        self.assertEqual(editor.tutorial.audio_offset, 1.5)
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


if __name__ == "__main__":
    unittest.main()
