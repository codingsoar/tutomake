import time
import threading
from typing import Callable, Optional
from pynput import mouse, keyboard
import mss
import mss.tools
from datetime import datetime
import os
import cv2
import numpy as np
from .key_utils import display_key_name, normalize_key_name
from .model import Step, Tutorial

# Audio recording support
try:
    import sounddevice as sd
    from scipy.io import wavfile
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: sounddevice/scipy not installed. Audio recording disabled.")

class Recorder:
    def __init__(self, tutorial: Tutorial, storage_dir: str, video_mode: bool = False, record_audio: bool = True):
        self.tutorial = tutorial
        self.storage_dir = storage_dir
        self.video_mode = video_mode
        self.record_audio = record_audio and AUDIO_AVAILABLE
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
        self.monitor_left = 0
        self.monitor_top = 0
        
        # Audio settings
        self.audio_sample_rate = 44100
        self.audio_channels = 2
        self.audio_data = []
        
        # Keyboard recording buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0

    def start(self):
        if self.is_recording:
            return
        self.is_recording = True
        self.stop_event.clear()
        
        self.start_time = time.time()
        
        if self.video_mode:
            # Initialize video writer
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = f"video_{timestamp}.avi"
            self.video_path = os.path.join(self.storage_dir, video_filename)
            self.tutorial.video_path = self.video_path
            
            # Audio file path
            if self.record_audio:
                audio_filename = f"audio_{timestamp}.wav"
                self.audio_path = os.path.join(self.storage_dir, audio_filename)
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
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()
        
        # Keyboard listener for text input recording
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self.keyboard_listener.start()
        
        # Reset keyboard buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0
        
        print("Recording started...")

    def stop(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.stop_event.set()
        
        # Save any pending keyboard buffer
        if self.key_buffer:
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
                
                # 2. Draw Cursor (disabled per user request)
                # mx, my = mouse_controller.position
                # rel_x = int(mx - monitor_left)
                # rel_y = int(my - monitor_top)
                # 
                # h, w = frame_np.shape[:2]
                # if 0 <= rel_x < w and 0 <= rel_y < h:
                #     cv2.circle(frame_np, (rel_x, rel_y), 5, (0, 0, 0, 255), -1) 
                #     cv2.circle(frame_np, (rel_x, rel_y), 3, (255, 255, 255, 255), -1) 
                
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
            self.audio_data.append(indata.copy())
        
        try:
            with sd.InputStream(samplerate=self.audio_sample_rate, 
                               channels=self.audio_channels, 
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
            
            # Save as WAV
            wavfile.write(self.audio_path, self.audio_sample_rate, audio_array)
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

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording or not pressed:
            return
        
        # Save any pending keyboard input first
        if self.key_buffer:
            self._save_keyboard_step()
            
        # Capture timestamp based on FRAMES, not time
        # This ensures sync even if recording lags
        if hasattr(self, 'frame_count') and hasattr(self, 'fps') and self.fps > 0:
            current_video_time = self.frame_count / self.fps
        else:
            current_video_time = 0.0
        
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
            
        # We can still capture a screenshot for the thumbnail/list view
        threading.Thread(target=self._capture_step, args=(x, y, current_video_time, button_name)).start()

    def _capture_step(self, x, y, timestamp, button_name="Click"):
        # We'll stick to full screen capture for the step image for now, 
        # but in video mode, we rely on the video mainly. 
        # The step image serves as a visual reference in the Editor.
        
        # Generate filename
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"step_{ts_str}.png"
        filepath = os.path.join(self.storage_dir, filename)

        with mss.mss() as sct:
            monitor_idx = 1
            for i, m in enumerate(sct.monitors[1:], 1):
                if (m["left"] <= x < m["left"] + m["width"]) and \
                   (m["top"] <= y < m["top"] + m["height"]):
                    monitor_idx = i
                    break
            
            monitor = sct.monitors[monitor_idx]
            
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)

            # Record offsets for coordinate calculation
            monitor_left = monitor["left"]
            monitor_top = monitor["top"]
        
        width = 50
        height = 50
        
        # Calculate relative coordinates based on the captured monitor
        rel_x = x - monitor_left
        rel_y = y - monitor_top
        
        step = Step(
            image_path=filepath,
            x=int(rel_x - width / 2),
            y=int(rel_y - height / 2),
            width=width,
            height=height,
            click_button=button_name.lower(),  # left, right, middle
            description=f"{button_name} click here",
            timestamp=timestamp
        )
        self.tutorial.steps.append(step)
        print(f"Captured {button_name} click at {x}, {y} (timestamp={timestamp:.3f}s)")
        
        if self.on_step_callback:
            self.on_step_callback(step)

    def _on_key_press(self, key):
        """Handle keyboard input during recording."""
        if not self.is_recording:
            return
            
        try:
            # Get the character
            if hasattr(key, 'char') and key.char:
                char = key.char
                
                # Start buffer timing if this is the first key
                if not self.key_buffer:
                    self.key_buffer_start_time = self._get_current_video_time()
                    
                self.key_buffer += char
                print(f"Key buffer: '{self.key_buffer}'")
                
            elif key == keyboard.Key.space:
                # Space ends keyboard input and adds a space
                if self.key_buffer:
                    self._save_keyboard_step()
                    
            elif key == keyboard.Key.enter:
                # Enter ends keyboard input
                if self.key_buffer:
                    self._save_keyboard_step()
                    
            elif key == keyboard.Key.backspace:
                # Allow backspace to correct input
                if self.key_buffer:
                    self.key_buffer = self.key_buffer[:-1]
                    
            # Handle special keys as separate steps
            elif key == keyboard.Key.delete:
                self._save_special_key_step("delete")
            elif key == keyboard.Key.tab:
                self._save_special_key_step("tab")
            elif key == keyboard.Key.esc:
                self._save_special_key_step("esc")
            elif hasattr(key, 'name') and key.name:
                # Handle F-keys and arrow keys
                key_name = key.name
                if key_name.startswith('f') and key_name[1:].isdigit():
                    self._save_special_key_step(key_name)
                elif key_name in ['up', 'down', 'left', 'right']:
                    self._save_special_key_step(key_name)
                    
        except AttributeError:
            pass  # Special keys we don't handle
    
    def _get_current_video_time(self):
        """Get current video timestamp based on frame count."""
        if hasattr(self, 'frame_count') and hasattr(self, 'fps') and self.fps > 0:
            return self.frame_count / self.fps
        return time.time() - self.start_time
    
    def _save_keyboard_step(self):
        """Save the current keyboard buffer as a keyboard step."""
        if not self.key_buffer:
            return
            
        timestamp = self.key_buffer_start_time
        
        step = Step(
            action_type="keyboard",
            x=100,  # Default position
            y=100,
            description="Type text",
            keyboard_input=self.key_buffer,
            keyboard_mode="text",
            timestamp=timestamp
        )
        
        # Insert in sorted order by timestamp
        insert_idx = 0
        for i, existing_step in enumerate(self.tutorial.steps):
            if existing_step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self.tutorial.steps.insert(insert_idx, step)
        print(f"Captured keyboard step: '{self.key_buffer}' (timestamp={timestamp:.3f}s)")
        
        # Clear buffer
        self.key_buffer = ""
        self.key_buffer_start_time = 0.0
        
        if self.on_step_callback:
            self.on_step_callback(step)
    
    def _save_special_key_step(self, key_name):
        """Save a special key press as a keyboard step."""
        timestamp = self._get_current_video_time()
        normalized_key_name = normalize_key_name(key_name)
        
        step = Step(
            action_type="keyboard",
            x=100,
            y=100,
            description=f"Press {display_key_name(normalized_key_name)}",
            keyboard_input=normalized_key_name,
            keyboard_mode="key",
            timestamp=timestamp
        )
        
        # Insert in sorted order by timestamp
        insert_idx = 0
        for i, existing_step in enumerate(self.tutorial.steps):
            if existing_step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self.tutorial.steps.insert(insert_idx, step)
        print(f"Captured special key: {normalized_key_name} (timestamp={timestamp:.3f}s)")
        
        if self.on_step_callback:
            self.on_step_callback(step)
