import time
import threading
import math
from typing import Callable, Optional
from pathlib import Path
from pynput import mouse, keyboard
import mss
import mss.tools
from datetime import datetime
import os
import wave
import re
import cv2
import numpy as np
from .key_utils import (
    display_key_combo,
    display_key_name,
    key_code_from_char,
    key_code_from_key_name,
    normalize_key_combo,
    normalize_key_name,
)
from .model import Step, Tutorial

# Audio recording support
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: sounddevice not installed. Audio recording disabled.")


def get_audio_input_devices():
    """Return physical-looking input devices and hide obvious virtual/system capture endpoints."""
    if not AUDIO_AVAILABLE:
        return []

    devices = []
    try:
        default_input = None
        try:
            default_devices = sd.default.device
            if isinstance(default_devices, (list, tuple)) and len(default_devices) >= 1:
                default_input = default_devices[0]
        except Exception:
            default_input = None

        seen_names = set()
        for index, device in enumerate(sd.query_devices()):
            if device.get("max_input_channels", 0) <= 0:
                continue
            raw_name = device.get("name", f"Input {index}")
            cleaned_name = _clean_audio_device_name(raw_name)
            normalized_name = _normalize_audio_device_name(cleaned_name)
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)

            device_class = _classify_audio_device(cleaned_name)
            label = _format_audio_device_label(
                cleaned_name,
                device_class,
                int(device.get("max_input_channels", 0)),
                is_default=(default_input == index),
            )
            devices.append({
                "id": index,
                "name": cleaned_name,
                "label": label,
                "channels": int(device.get("max_input_channels", 0)),
                "kind": device_class,
            })
    except Exception as e:
        print(f"Failed to query audio devices: {e}")

    filtered_devices = [
        device for device in devices
        if device.get("kind") not in {"Virtual", "System"}
    ]
    return filtered_devices or devices


def _clean_audio_device_name(name: str) -> str:
    cleaned = re.sub(r"\s*\((mme|wdm-ks|windows directsound|wasapi|asio)\)\s*$", "", name or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\b(input|output)\b\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return cleaned or "Unknown Input"


def _normalize_audio_device_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _classify_audio_device(name: str) -> str:
    lowered = (name or "").lower()
    if any(token in lowered for token in ("cable", "virtual", "vb-audio", "voicemeter", "blackhole", "loopback")):
        return "Virtual"
    if any(token in lowered for token in ("stereo mix", "what u hear", "wave out")):
        return "System"
    if any(token in lowered for token in ("line in", "line-input", "aux", "spdif", "digital in")):
        return "Line In"
    if any(token in lowered for token in ("webcam", "camera", "usb", "mic", "microphone", "headset", "airpods", "bluetooth")):
        return "Mic"
    return "Input"


def _format_audio_device_label(name: str, kind: str, channels: int, is_default: bool = False) -> str:
    prefix = "[Recommended] " if is_default else ""
    return f"{prefix}{name} [{kind}, {channels} ch]"


def record_test_audio_clip(output_path: str, device=None, duration: float = 3.0):
    """Record a short WAV clip from the selected input device for validation."""
    if not AUDIO_AVAILABLE:
        return False, "sounddevice is not installed."

    try:
        device_info = sd.query_devices(device, "input")
        channels = min(2, int(device_info.get("max_input_channels", 0) or 1))
        sample_rate = int(device_info.get("default_samplerate") or 44100)
        frame_count = max(1, int(round(duration * sample_rate)))

        audio_array = sd.rec(
            frame_count,
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=device,
        )
        sd.wait()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_file), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(np.asarray(audio_array, dtype=np.int16).tobytes())
        return True, str(output_file)
    except Exception as e:
        return False, str(e)


class Recorder:
    def __init__(
        self,
        tutorial: Tutorial,
        storage_dir: str,
        video_mode: bool = False,
        record_audio: bool = True,
        audio_device=None,
        audio_device_name: Optional[str] = None,
        show_cursor: bool = True,
        highlight_clicks: bool = True,
    ):
        self.tutorial = tutorial
        self.storage_dir = storage_dir
        self.video_mode = video_mode
        self.record_audio = record_audio and AUDIO_AVAILABLE
        self.audio_device = audio_device
        self.audio_device_name = audio_device_name or "Default Input"
        self.show_cursor = show_cursor
        self.highlight_clicks = highlight_clicks
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            
        self.is_recording = False
        self.listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        self.on_step_callback: Optional[Callable[[Step], None]] = None
        self.stop_event = threading.Event()
        self.video_writer = None
        self.start_time = 0.0
        self.video_thread = None
        self.video_path = None
        self.audio_path = None
        self.recording_dir = None
        self.monitor_left = 0
        self.monitor_top = 0
        self.native_width = 0
        self.native_height = 0
        
        # Audio settings
        self.audio_sample_rate = 44100
        self.audio_channels = 2
        self.audio_data = []
        self.audio_start_delay = 0.0
        self._audio_started_at = None
        self._configure_audio_input()
        
        # Keyboard recording buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0
        self.middle_press_pos: Optional[tuple[int, int]] = None
        self.middle_last_pos: Optional[tuple[int, int]] = None
        self.middle_press_timestamp: float = 0.0
        self.middle_press_modifier_keys: list[str] = []
        self.middle_drag_threshold = 30
        self.current_modifier_keys: set[str] = set()
        self.space_modifier_pending = False
        self.space_modifier_used = False
        self.pending_text_space = False
        self.mouse_feedback_events: list[dict] = []

    def _configure_audio_input(self):
        """Match stream settings to the selected device to avoid distorted capture."""
        if not AUDIO_AVAILABLE:
            return

        try:
            device_info = sd.query_devices(self.audio_device, "input")
        except Exception as e:
            print(f"Falling back to default audio settings: {e}")
            return

        max_input_channels = int(device_info.get("max_input_channels", 0) or 0)
        if max_input_channels > 0:
            self.audio_channels = min(2, max_input_channels)

        default_samplerate = device_info.get("default_samplerate")
        if default_samplerate:
            self.audio_sample_rate = int(default_samplerate)

    def start(self):
        if self.is_recording:
            return
        self.is_recording = True
        self.stop_event.clear()
        
        self.start_time = time.time()
        session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.recording_dir = self._create_recording_session_dir(session_timestamp)
        
        if self.video_mode:
            # Initialize video writer
            self.video_path = os.path.join(self.recording_dir, "video.avi")
            self.tutorial.video_path = self.video_path
            
            # Audio file path
            if self.record_audio:
                self.audio_path = os.path.join(self.recording_dir, "audio.wav")
                self.audio_data = []
            
            # Get screen size from monitor 1
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                self.native_width = monitor["width"]
                self.native_height = monitor["height"]
                self.monitor_left = monitor["left"]
                self.monitor_top = monitor["top"]
            
            # Revert to Full Native Resolution (User Request)
            self.rec_width = self.native_width
            self.rec_height = self.native_height
                
            # Codec: MJPG
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            fps = 24.0 
            self.video_writer = cv2.VideoWriter(self.video_path, fourcc, fps, (self.rec_width, self.rec_height))
            
            # Queue for frames to decouple capture from writing
            import queue
            self.frame_queue = queue.Queue()
            
            # Start threads
            # 1. Capture Thread
            self.capture_thread = threading.Thread(target=self._capture_loop, args=(fps,))
            self.capture_thread.start()
            
            # 2. Key Frame Writer Thread
            self.writer_thread = threading.Thread(target=self._writer_loop)
            self.writer_thread.start()
            
            # 3. Audio Recording Thread
            if self.record_audio:
                self.audio_thread = threading.Thread(target=self._audio_loop)
                self.audio_thread.start()
                print("Audio recording enabled")
            
        else:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                self.monitor_left = monitor["left"]
                self.monitor_top = monitor["top"]
            self.tutorial.video_path = None
        
        # Mouse listener
        self.listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
        self.listener.start()
        
        # Keyboard listener for text input recording
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.keyboard_listener.start()
        
        # Reset keyboard buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0
        self.pending_text_space = False
        
        print("Recording started...")

    def _create_recording_session_dir(self, session_timestamp: Optional[str] = None) -> str:
        session_timestamp = session_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        session_dir = os.path.join(self.storage_dir, f"recording_{session_timestamp}")
        os.makedirs(session_dir, exist_ok=True)
        return session_dir

    def stop(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.stop_event.set()
        
        # Save any pending keyboard buffer
        if self.key_buffer or self.pending_text_space:
            self._save_keyboard_step()
        
        # Calculate stats
        duration = time.time() - self.start_time
        if hasattr(self, 'frame_count') and duration > 0:
            actual_fps = self.frame_count / duration
            print(f"Recording finished. Duration: {duration:.2f}s, Frames: {self.frame_count}, Avg FPS: {actual_fps:.2f}")
            self.last_recording_stats = f"Time: {duration:.2f}s, FPS: {actual_fps:.2f}"
        
        if self.listener:
            self.listener.stop()
            self.listener = None
            
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
            
        # Wait for threads
        if hasattr(self, 'capture_thread'):
            self.capture_thread.join()
        
        # Signal writer to stop (using None or just let it empty queue)
        if hasattr(self, 'frame_queue'):
            self.frame_queue.put(None)
            
        if hasattr(self, 'writer_thread'):
            self.writer_thread.join()
        
        # Wait for audio thread
        if hasattr(self, 'audio_thread'):
            self.audio_thread.join()
            
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        # Save audio file and merge with video
        if self.record_audio and self.audio_data:
            self._save_and_merge_audio()
            
        print("Recording stopped.")

    def _capture_loop(self, fps):
        interval = 1.0 / fps
        self.frame_count = 0
        self.fps = fps
        
        # Mouse controller for cursor position
        from pynput.mouse import Controller
        mouse_controller = Controller()
        
        start_time = time.time()
        next_frame_idx = 0
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            monitor_left = monitor["left"]
            monitor_top = monitor["top"]
            
            while not self.stop_event.is_set():
                # loops start
                
                # 1. Capture Frame
                img = sct.grab(monitor)
                frame_np = np.array(img)
                frame_np = self._render_mouse_overlay(
                    frame_np,
                    cursor_position=mouse_controller.position,
                    monitor_left=monitor_left,
                    monitor_top=monitor_top,
                    now=time.time(),
                )
                
                # 3. Time Sync Logic
                # Calculate how many video frames belong to this moment
                now = time.time()
                elapsed = now - start_time
                target_frame_count = int(elapsed * fps)
                
                # If we are behind, emit duplicate frames to catch up
                # Always emit at least 1 frame to keep going
                frames_to_emit = max(1, target_frame_count - next_frame_idx)
                
                # Cap excessive duplication to avoid memory explosion if we hang
                frames_to_emit = min(frames_to_emit, 5)
                
                for _ in range(frames_to_emit):
                    self.frame_queue.put(frame_np) # Put SAME frame multiple times
                    next_frame_idx += 1
                
                self.frame_count = next_frame_idx # Sync public counter
                
                # 4. Sleep if ahead (unlikely at 4K, but good hygiene)
                # usage: we just pushed up to target_frame_count.
                # next target is (target_frame_count + 1) * interval
                next_target_time = (target_frame_count + 1) * interval
                sleep_time = max(0, next_target_time - (time.time() - start_time))
                time.sleep(sleep_time)

    def _writer_loop(self):
        while True:
            img = self.frame_queue.get()
            if img is None:
                break
                
            # Heavy processing here
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            if self.video_writer:
                self.video_writer.write(frame)
            
            self.frame_queue.task_done()
    
    def _audio_loop(self):
        """Record audio in a separate thread."""
        if not AUDIO_AVAILABLE:
            return
            
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"Audio status: {status}")
            if self._audio_started_at is None:
                self._audio_started_at = time.time()
                self.audio_start_delay = max(0.0, self._audio_started_at - self.start_time)
            self.audio_data.append(indata.copy())
        
        try:
            with sd.InputStream(samplerate=self.audio_sample_rate, 
                               channels=self.audio_channels,
                               device=self.audio_device,
                               callback=audio_callback):
                while not self.stop_event.is_set():
                    time.sleep(0.1)
        except Exception as e:
            print(f"Audio recording error: {e}")
            self.record_audio = False
    
    def _save_and_merge_audio(self):
        """Save audio to WAV file and merge with video using ffmpeg."""
        if not self.audio_data:
            return
            
        try:
            # Combine all audio chunks
            audio_array = np.concatenate(self.audio_data, axis=0)

            # Pad initial silence so audio lines up with video start.
            if self.audio_start_delay > 0:
                padding_frames = int(round(self.audio_start_delay * self.audio_sample_rate))
                if padding_frames > 0:
                    silence = np.zeros((padding_frames, self.audio_channels), dtype=audio_array.dtype)
                    audio_array = np.concatenate([silence, audio_array], axis=0)

            # Convert float audio samples from sounddevice to 16-bit PCM WAV.
            if np.issubdtype(audio_array.dtype, np.floating):
                audio_array = np.clip(audio_array, -1.0, 1.0)
                audio_array = (audio_array * 32767).astype(np.int16)
            elif audio_array.dtype != np.int16:
                audio_array = audio_array.astype(np.int16)

            # Save as WAV using the standard library to avoid scipy packaging overhead.
            with wave.open(self.audio_path, 'wb') as wav_file:
                wav_file.setnchannels(self.audio_channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.audio_sample_rate)
                wav_file.writeframes(audio_array.tobytes())

            self.tutorial.audio_path = self.audio_path
            print(f"Audio saved to: {self.audio_path}")
            
            # Merge video and audio using ffmpeg
            try:
                import imageio_ffmpeg
                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                print("imageio-ffmpeg not available, video and audio saved separately")
                return
            
            import subprocess
            
            # Create merged output path
            merged_path = self.video_path.replace('.avi', '_with_audio.mp4')
            
            result = subprocess.run([
                ffmpeg_path, '-y',
                '-i', self.video_path,
                '-i', self.audio_path,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-shortest',
                merged_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                # Replace video path with merged file
                self.tutorial.video_path = merged_path
                self.tutorial.audio_path = None
                print(f"Merged video+audio saved to: {merged_path}")
                
                # Clean up original files
                try:
                    os.remove(self.video_path)
                    os.remove(self.audio_path)
                except:
                    pass
            else:
                print(f"FFmpeg merge failed: {result.stderr}")
                
        except Exception as e:
            print(f"Audio save/merge error: {e}")

    def _on_move(self, x, y):
        if self.middle_press_pos is not None:
            self.middle_last_pos = (x, y)

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording:
            return
        
        # Determine button type
        from pynput.mouse import Button
        if button == Button.left:
            button_name = "Left"
        elif button == Button.right:
            button_name = "Right"
        elif button == Button.middle:
            button_name = "Middle"
        else:
            button_name = "Click"

        if pressed:
            self._record_mouse_feedback(x, y, button_name.lower())

        if pressed and (self.key_buffer or self.pending_text_space):
            self._save_keyboard_step()

        current_video_time = self._get_current_video_time()

        if button == Button.middle:
            if pressed:
                self.middle_press_pos = (x, y)
                self.middle_last_pos = (x, y)
                self.middle_press_timestamp = current_video_time
                self.middle_press_modifier_keys = self._current_modifier_list()
                self._mark_modifier_keys_used(self.middle_press_modifier_keys)
            else:
                press_pos = self.middle_press_pos
                last_pos = self.middle_last_pos or (x, y)
                timestamp = self.middle_press_timestamp
                release_timestamp = current_video_time
                modifier_keys = list(self.middle_press_modifier_keys)
                self.middle_press_pos = None
                self.middle_last_pos = None
                self.middle_press_timestamp = 0.0
                self.middle_press_modifier_keys = []

                if not press_pos:
                    return

                distance = math.hypot(last_pos[0] - press_pos[0], last_pos[1] - press_pos[1])
                if distance >= self.middle_drag_threshold:
                    threading.Thread(
                        target=self._capture_drag_step,
                        args=(press_pos[0], press_pos[1], last_pos[0], last_pos[1], timestamp, release_timestamp, "middle", modifier_keys),
                    ).start()
                else:
                    threading.Thread(
                        target=self._capture_step,
                        args=(x, y, timestamp, button_name, modifier_keys),
                    ).start()
            return

        if not pressed:
            return

        # We can still capture a screenshot for the thumbnail/list view
        modifier_keys = self._current_modifier_list()
        self._mark_modifier_keys_used(modifier_keys)
        threading.Thread(target=self._capture_step, args=(x, y, current_video_time, button_name, modifier_keys)).start()

    def _record_mouse_feedback(self, x: int, y: int, button_name: str):
        if not self.highlight_clicks:
            return
        self.mouse_feedback_events.append(
            {
                "x": int(x),
                "y": int(y),
                "button": (button_name or "left").lower(),
                "timestamp": time.time(),
            }
        )
        if len(self.mouse_feedback_events) > 12:
            self.mouse_feedback_events = self.mouse_feedback_events[-12:]

    def _render_mouse_overlay(
        self,
        frame: np.ndarray,
        cursor_position: Optional[tuple[int, int]] = None,
        monitor_left: Optional[int] = None,
        monitor_top: Optional[int] = None,
        now: Optional[float] = None,
    ) -> np.ndarray:
        if not (self.show_cursor or self.highlight_clicks):
            return frame

        now = time.time() if now is None else now
        monitor_left = self.monitor_left if monitor_left is None else monitor_left
        monitor_top = self.monitor_top if monitor_top is None else monitor_top
        rendered = frame

        if self.highlight_clicks and self.mouse_feedback_events:
            active_events = []
            for event in self.mouse_feedback_events:
                age = now - float(event.get("timestamp", now))
                if age <= 0.45:
                    rendered = self._draw_click_feedback(rendered, event, age, monitor_left, monitor_top)
                    active_events.append(event)
            self.mouse_feedback_events = active_events

        if self.show_cursor and cursor_position:
            rel_x = int(cursor_position[0] - monitor_left)
            rel_y = int(cursor_position[1] - monitor_top)
            rendered = self._draw_mouse_cursor(rendered, rel_x, rel_y)

        return rendered

    def _draw_mouse_cursor(self, frame: np.ndarray, x: int, y: int) -> np.ndarray:
        h, w = frame.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return frame

        overlay = frame.copy()
        shadow = np.array(
            [
                (x + 3, y + 3),
                (x + 3, y + 28),
                (x + 10, y + 22),
                (x + 16, y + 36),
                (x + 22, y + 33),
                (x + 16, y + 19),
                (x + 25, y + 19),
            ],
            dtype=np.int32,
        )
        pointer = np.array(
            [
                (x, y),
                (x, y + 25),
                (x + 7, y + 19),
                (x + 13, y + 33),
                (x + 19, y + 30),
                (x + 13, y + 17),
                (x + 22, y + 17),
            ],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(overlay, shadow, (20, 20, 20, 255))
        cv2.fillConvexPoly(overlay, pointer, (255, 255, 255, 255))
        cv2.polylines(overlay, [pointer], True, (0, 0, 0, 255), 2, lineType=cv2.LINE_AA)
        return cv2.addWeighted(overlay, 0.96, frame, 0.04, 0)

    def _draw_click_feedback(
        self,
        frame: np.ndarray,
        event: dict,
        age: float,
        monitor_left: int,
        monitor_top: int,
    ) -> np.ndarray:
        rel_x = int(event.get("x", 0) - monitor_left)
        rel_y = int(event.get("y", 0) - monitor_top)
        h, w = frame.shape[:2]
        if not (0 <= rel_x < w and 0 <= rel_y < h):
            return frame

        progress = max(0.0, min(1.0, age / 0.45))
        radius = int(14 + (progress * 28))
        alpha = max(0.18, 0.65 * (1.0 - progress))
        button_name = (event.get("button") or "left").lower()
        colors = {
            "left": (80, 220, 255, 255),
            "right": (255, 120, 120, 255),
            "middle": (120, 255, 160, 255),
        }
        color = colors.get(button_name, (80, 220, 255, 255))

        overlay = frame.copy()
        cv2.circle(overlay, (rel_x, rel_y), radius, color, 3, lineType=cv2.LINE_AA)
        cv2.circle(overlay, (rel_x, rel_y), max(4, radius // 4), color, -1, lineType=cv2.LINE_AA)
        return cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0)

    def _capture_monitor_screenshot(self, x, y, action_label="Click"):
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"step_{ts_str}.png"
        output_dir = self.recording_dir or self.storage_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, filename)

        with mss.mss() as sct:
            if self.video_mode:
                monitor = {
                    "left": self.monitor_left,
                    "top": self.monitor_top,
                    "width": self.native_width,
                    "height": self.native_height,
                }

                in_recorded_monitor = (
                    monitor["left"] <= x < monitor["left"] + monitor["width"]
                    and monitor["top"] <= y < monitor["top"] + monitor["height"]
                )
                if not in_recorded_monitor:
                    print(
                        f"Ignoring {action_label} at {x}, {y}: "
                        "outside recorded monitor bounds"
                    )
                    return None, None, None
            else:
                monitor_idx = 1
                for i, m in enumerate(sct.monitors[1:], 1):
                    if (m["left"] <= x < m["left"] + m["width"]) and \
                       (m["top"] <= y < m["top"] + m["height"]):
                        monitor_idx = i
                        break
                monitor = sct.monitors[monitor_idx]

            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)

        return filepath, monitor["left"], monitor["top"]

    def _capture_step(self, x, y, timestamp, button_name="Click", modifier_keys=None):
        # We'll stick to full screen capture for the step image for now, 
        # but in video mode, we rely on the video mainly. 
        # The step image serves as a visual reference in the Editor.
        filepath, monitor_left, monitor_top = self._capture_monitor_screenshot(x, y, f"{button_name} click")
        if not filepath:
            return
        
        width = 50
        height = 50
        
        # Calculate relative coordinates based on the captured monitor
        rel_x = x - monitor_left
        rel_y = y - monitor_top
        
        modifier_keys = list(modifier_keys or [])
        step = Step(
            image_path=filepath,
            x=int(rel_x - width / 2),
            y=int(rel_y - height / 2),
            width=width,
            height=height,
            click_button=button_name.lower(),  # left, right, middle
            modifier_keys=modifier_keys,
            description=self._build_click_description(button_name, modifier_keys),
            instruction=self._build_click_instruction(button_name, modifier_keys),
            timestamp=timestamp
        )
        self._insert_step_sorted(step)
        print(f"Captured {button_name} click at {x}, {y} (timestamp={timestamp:.3f}s)")
        
        if self.on_step_callback:
            self.on_step_callback(step)

    def _capture_drag_step(self, start_x, start_y, end_x, end_y, timestamp, release_timestamp=None, button_name="middle", modifier_keys=None):
        filepath, monitor_left, monitor_top = self._capture_monitor_screenshot(start_x, start_y, f"{button_name} drag")
        if not filepath:
            return

        width = 50
        height = 50
        rel_start_x = start_x - monitor_left
        rel_start_y = start_y - monitor_top
        rel_end_x = end_x - monitor_left
        rel_end_y = end_y - monitor_top
        distance = math.hypot(rel_end_x - rel_start_x, rel_end_y - rel_start_y)
        modifier_keys = list(modifier_keys or [])
        end_timestamp = float(release_timestamp if release_timestamp is not None else timestamp)

        step = Step(
            image_path=filepath,
            action_type="mouse_drag",
            x=int(rel_start_x - width / 2),
            y=int(rel_start_y - height / 2),
            width=width,
            height=height,
            drag_button=button_name.lower(),
            drag_end_x=int(rel_end_x - width / 2),
            drag_end_y=int(rel_end_y - height / 2),
            drag_end_width=width,
            drag_end_height=height,
            drag_min_distance=max(int(distance * 0.35), self.middle_drag_threshold),
            drag_start_timestamp=float(timestamp),
            drag_end_timestamp=max(float(timestamp), end_timestamp),
            modifier_keys=modifier_keys,
            description=self._build_drag_description(button_name, modifier_keys),
            instruction=self._build_drag_instruction(rel_start_x, rel_start_y, rel_end_x, rel_end_y, button_name, modifier_keys),
            timestamp=timestamp
        )
        self._insert_step_sorted(step)
        print(
            f"Captured {button_name.title()} drag from {start_x}, {start_y} "
            f"to {end_x}, {end_y} (timestamp={timestamp:.3f}s)"
        )

        if self.on_step_callback:
            self.on_step_callback(step)

    def _build_drag_instruction(self, start_x, start_y, end_x, end_y, button_name="middle", modifier_keys=None):
        dx = end_x - start_x
        dy = end_y - start_y
        if abs(dx) >= abs(dy):
            direction = "right" if dx >= 0 else "left"
        else:
            direction = "down" if dy >= 0 else "up"
        modifier_prefix = self._build_modifier_phrase(modifier_keys)
        pointer_phrase = f"press the {button_name} mouse button and drag {direction}"
        return f"{modifier_prefix}{pointer_phrase}".capitalize()

    def _build_click_description(self, button_name, modifier_keys):
        modifier_prefix = self._build_modifier_phrase(modifier_keys, joiner="+")
        return f"{modifier_prefix}{button_name} click here" if modifier_prefix else f"{button_name} click here"

    def _build_click_instruction(self, button_name, modifier_keys):
        modifier_prefix = self._build_modifier_phrase(modifier_keys)
        return f"{modifier_prefix}click with the {button_name.lower()} mouse button".capitalize()

    def _build_drag_description(self, button_name, modifier_keys):
        modifier_prefix = self._build_modifier_phrase(modifier_keys, joiner="+")
        button_label = button_name.title()
        return f"{modifier_prefix}{button_label} drag here" if modifier_prefix else f"{button_label} drag here"

    def _build_modifier_phrase(self, modifier_keys, joiner=" + "):
        labels = [display_key_name(modifier) for modifier in modifier_keys or []]
        if not labels:
            return ""
        if joiner == "+":
            return f"{'+'.join(labels)} "
        return f"hold {' + '.join(labels)} and "

    def _current_modifier_list(self):
        order = ["ctrl", "shift", "alt", "cmd", "space"]
        return [key for key in order if key in self.current_modifier_keys]

    def _mark_modifier_keys_used(self, modifier_keys):
        if "space" in (modifier_keys or []):
            self.space_modifier_used = True

    def _should_insert_literal_space(self) -> bool:
        return "shift" in self.current_modifier_keys

    def _modifier_from_key(self, key):
        key_name = normalize_key_name(getattr(key, "name", "") or "")
        if key_name in {"ctrl", "shift", "alt", "cmd"}:
            return key_name
        return None

    def _normalize_char_key_for_combo(self, char: str) -> str:
        if not char:
            return ""
        if len(char) == 1 and 1 <= ord(char) <= 26:
            return chr(ord('a') + ord(char) - 1)
        return char.lower()

    def _key_code_from_event(self, key, fallback_name: str = "") -> str:
        vk = getattr(key, "vk", None)
        if hasattr(key, "char") and key.char:
            return key_code_from_char(key.char, vk)
        return key_code_from_key_name(fallback_name or getattr(key, "name", "") or "")

    def _insert_step_sorted(self, step: Step):
        insert_idx = 0
        for i, existing_step in enumerate(self.tutorial.steps):
            if existing_step.timestamp > step.timestamp:
                break
            insert_idx = i + 1
        self.tutorial.steps.insert(insert_idx, step)

    def _on_key_press(self, key):
        """Handle keyboard input during recording."""
        if not self.is_recording:
            return

        modifier_key = self._modifier_from_key(key)
        if modifier_key:
            self.current_modifier_keys.add(modifier_key)
            return
        if key == keyboard.Key.space and not self.key_buffer:
            self.current_modifier_keys.add("space")
            self.space_modifier_pending = True
            self.space_modifier_used = False
            return
            
        try:
            keypad_char = None
            vk = getattr(key, 'vk', None)
            if vk is not None:
                keypad_digit_map = {96 + i: str(i) for i in range(10)}
                keypad_symbol_map = {
                    106: '*',
                    107: '+',
                    109: '-',
                    110: '.',
                    111: '/',
                }
                keypad_char = keypad_digit_map.get(vk) or keypad_symbol_map.get(vk)

            # Get the character
            if (hasattr(key, 'char') and key.char) or keypad_char:
                char = key.char if hasattr(key, 'char') and key.char else keypad_char

                modifier_keys = self._current_modifier_list()
                if modifier_keys:
                    combo_char = self._normalize_char_key_for_combo(char)
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._mark_modifier_keys_used(modifier_keys)
                    self._save_key_combo_step(combo_char, modifier_keys, key_code_from_char(char, vk))
                    return
                
                # Start buffer timing if this is the first key
                if not self.key_buffer:
                    self.key_buffer_start_time = self._get_current_video_time()
                self._commit_pending_text_space()
                self.key_buffer += char
                print(f"Key buffer: '{self.key_buffer}'")
                
            elif key == keyboard.Key.space:
                if self.key_buffer:
                    if self._should_insert_literal_space():
                        self.pending_text_space = True
                    else:
                        self._save_keyboard_step()
                    
            elif key == keyboard.Key.enter:
                modifier_keys = self._current_modifier_list()
                if self.key_buffer or self.pending_text_space:
                    self._save_keyboard_step()
                    return
                if modifier_keys:
                    self._mark_modifier_keys_used(modifier_keys)
                    self._save_key_combo_step("enter", modifier_keys, self._key_code_from_event(key, "enter"))
                    return
                self._save_special_key_step("enter", self._key_code_from_event(key, "enter"))
                    
            elif key == keyboard.Key.backspace:
                # Allow backspace to correct input
                if self.pending_text_space:
                    self.pending_text_space = False
                elif self.key_buffer:
                    self.key_buffer = self.key_buffer[:-1]
                    
            # Handle special keys as separate steps
            elif key == keyboard.Key.delete:
                modifier_keys = self._current_modifier_list()
                if modifier_keys:
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._mark_modifier_keys_used(modifier_keys)
                    self._save_key_combo_step("delete", modifier_keys, self._key_code_from_event(key, "delete"))
                    return
                if self.key_buffer or self.pending_text_space:
                    self._save_keyboard_step()
                self._save_special_key_step("delete", self._key_code_from_event(key, "delete"))
            elif key == keyboard.Key.tab:
                modifier_keys = self._current_modifier_list()
                if modifier_keys:
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._mark_modifier_keys_used(modifier_keys)
                    self._save_key_combo_step("tab", modifier_keys, self._key_code_from_event(key, "tab"))
                    return
                if self.key_buffer or self.pending_text_space:
                    self._save_keyboard_step()
                self._save_special_key_step("tab", self._key_code_from_event(key, "tab"))
            elif key == keyboard.Key.esc:
                modifier_keys = self._current_modifier_list()
                if modifier_keys:
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._mark_modifier_keys_used(modifier_keys)
                    self._save_key_combo_step("esc", modifier_keys, self._key_code_from_event(key, "esc"))
                    return
                if self.key_buffer or self.pending_text_space:
                    self._save_keyboard_step()
                self._save_special_key_step("esc", self._key_code_from_event(key, "esc"))
            elif hasattr(key, 'name') and key.name:
                # Handle F-keys and arrow keys
                key_name = key.name
                if key_name.startswith('f') and key_name[1:].isdigit():
                    modifier_keys = self._current_modifier_list()
                    if modifier_keys:
                        if self.key_buffer or self.pending_text_space:
                            self._save_keyboard_step()
                        self._mark_modifier_keys_used(modifier_keys)
                        self._save_key_combo_step(key_name, modifier_keys, self._key_code_from_event(key, key_name))
                        return
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._save_special_key_step(key_name, self._key_code_from_event(key, key_name))
                elif key_name in ['up', 'down', 'left', 'right']:
                    modifier_keys = self._current_modifier_list()
                    if modifier_keys:
                        if self.key_buffer or self.pending_text_space:
                            self._save_keyboard_step()
                        self._mark_modifier_keys_used(modifier_keys)
                        self._save_key_combo_step(key_name, modifier_keys, self._key_code_from_event(key, key_name))
                        return
                    if self.key_buffer or self.pending_text_space:
                        self._save_keyboard_step()
                    self._save_special_key_step(key_name, self._key_code_from_event(key, key_name))
                    
        except AttributeError:
            pass  # Special keys we don't handle

    def _on_key_release(self, key):
        modifier_key = self._modifier_from_key(key)
        if modifier_key:
            self.current_modifier_keys.discard(modifier_key)
        elif key == keyboard.Key.space:
            should_emit_space = (
                self.space_modifier_pending
                and not self.space_modifier_used
                and not self.key_buffer
            )
            combo_modifiers = [name for name in self._current_modifier_list() if name != "space"]
            self.current_modifier_keys.discard("space")
            self.space_modifier_pending = False
            self.space_modifier_used = False
            if should_emit_space:
                if combo_modifiers:
                    self._save_key_combo_step("space", combo_modifiers, key_code_from_key_name("space"))
                else:
                    self._save_special_key_step("space", key_code_from_key_name("space"))
    
    def _get_current_video_time(self):
        """Get current video timestamp based on frame count."""
        if hasattr(self, 'frame_count') and hasattr(self, 'fps') and self.fps > 0:
            return self.frame_count / self.fps
        return time.time() - self.start_time

    def _commit_pending_text_space(self):
        if not self.pending_text_space:
            return
        if not self.key_buffer:
            self.key_buffer_start_time = self._get_current_video_time()
        self.key_buffer += " "
        self.pending_text_space = False
    
    def _save_keyboard_step(self):
        """Save the current keyboard buffer as a keyboard step."""
        submitted_with_space = self.pending_text_space and bool(self.key_buffer)
        if submitted_with_space:
            self.pending_text_space = False
        elif self.pending_text_space:
            self._commit_pending_text_space()

        if not self.key_buffer:
            return
            
        timestamp = self.key_buffer_start_time
        keyboard_input = self.key_buffer.rstrip() if submitted_with_space else self.key_buffer
        if not keyboard_input:
            self.key_buffer = ""
            self.key_buffer_start_time = 0.0
            return
        keyboard_space_behavior = "insert_space" if any(ch.isspace() for ch in keyboard_input) else "submit_step"
        
        step = Step(
            action_type="keyboard",
            x=100,  # Default position
            y=100,
            description="Type text",
            keyboard_input=keyboard_input,
            keyboard_mode="text",
            keyboard_space_behavior=keyboard_space_behavior,
            timestamp=timestamp
        )
        
        # Insert in sorted order by timestamp
        insert_idx = 0
        for i, existing_step in enumerate(self.tutorial.steps):
            if existing_step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self._insert_step_sorted(step)
        print(
            f"Captured keyboard step: '{keyboard_input}' "
            f"(space_behavior={keyboard_space_behavior}, timestamp={timestamp:.3f}s)"
        )
        
        # Clear buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0
        self.pending_text_space = False
        
        if self.on_step_callback:
            self.on_step_callback(step)
    
    def _save_special_key_step(self, key_name, key_code=""):
        """Save a special key press as a keyboard step."""
        timestamp = self._get_current_video_time()
        normalized_key_name = normalize_key_name(key_name)
        
        step = Step(
            action_type="keyboard",
            x=100,
            y=100,
            description=f"Press {display_key_name(normalized_key_name)}",
            keyboard_input=normalized_key_name,
            keyboard_code=key_code or key_code_from_key_name(normalized_key_name),
            keyboard_mode="key",
            timestamp=timestamp
        )
        
        # Insert in sorted order by timestamp
        insert_idx = 0
        for i, existing_step in enumerate(self.tutorial.steps):
            if existing_step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self._insert_step_sorted(step)
        print(f"Captured special key: {normalized_key_name} (timestamp={timestamp:.3f}s)")
        
        if self.on_step_callback:
            self.on_step_callback(step)

    def _save_key_combo_step(self, key_name, modifier_keys, key_code=""):
        timestamp = self._get_current_video_time()
        combo = normalize_key_combo("+".join([*modifier_keys, key_name]))

        step = Step(
            action_type="keyboard",
            x=100,
            y=100,
            description=f"Press {display_key_combo(combo)}",
            keyboard_input=combo,
            keyboard_code=key_code or key_code_from_key_name(key_name),
            keyboard_mode="key",
            timestamp=timestamp
        )

        self._insert_step_sorted(step)
        print(f"Captured key combo: {combo} (timestamp={timestamp:.3f}s)")

        if self.on_step_callback:
            self.on_step_callback(step)
