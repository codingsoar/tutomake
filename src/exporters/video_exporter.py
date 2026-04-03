"""
Video Exporter Module
Exports tutorials to MP4, GIF, WebM, AVI/MOV formats
"""
import os
import cv2
import numpy as np
from typing import Callable, Optional
from ..model import Tutorial, Step
from ..key_utils import display_key_combo, display_key_name


class VideoExporter:
    """Export tutorial with hitbox overlays to video formats."""
    
    def __init__(self, tutorial: Tutorial, progress_callback: Optional[Callable[[int], None]] = None):
        self.tutorial = tutorial
        self.progress_callback = progress_callback
    
    def export_mp4(self, output_path: str, fps: float = 24.0) -> bool:
        """Export as MP4 (H.264)."""
        return self._export_video(output_path, 'mp4v', fps)
    
    def export_webm(self, output_path: str, fps: float = 24.0) -> bool:
        """Export as WebM (VP8)."""
        return self._export_video(output_path, 'VP80', fps)
    
    def export_avi(self, output_path: str, fps: float = 24.0) -> bool:
        """Export as AVI (MJPG)."""
        return self._export_video(output_path, 'MJPG', fps)
    
    def _export_video(self, output_path: str, codec: str, fps: float) -> bool:
        """Internal method to export video with hitbox overlays."""
        if not self.tutorial.video_path or not os.path.exists(self.tutorial.video_path):
            print("No video file to export")
            return False
        
        # Open source video
        cap = cv2.VideoCapture(self.tutorial.video_path)
        if not cap.isOpened():
            print(f"Failed to open video: {self.tutorial.video_path}")
            return False
        
        # Get video properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        source_fps = cap.get(cv2.CAP_PROP_FPS) or fps
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*codec)
        out = cv2.VideoWriter(output_path, fourcc, source_fps, (width, height))
        
        if not out.isOpened():
            print(f"Failed to create output video: {output_path}")
            cap.release()
            return False
        
        # Build step timeline (frame -> step)
        step_frames = {}
        for i, step in enumerate(self.tutorial.steps):
            frame_num = int(step.timestamp * source_fps)
            step_frames[frame_num] = step
        
        current_step = None
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Check if we hit a step trigger
            if frame_count in step_frames:
                current_step = step_frames[frame_count]
            
            # Draw hitbox overlay if we have an active step
            if current_step:
                frame = self._draw_hitbox_overlay(frame, current_step)
            
            out.write(frame)
            frame_count += 1
            
            # Progress callback
            if self.progress_callback and total_frames > 0:
                progress = int((frame_count / total_frames) * 100)
                self.progress_callback(progress)
        
        cap.release()
        out.release()
        
        print(f"Exported video to: {output_path}")
        return True
    
    def _draw_hitbox_overlay(self, frame: np.ndarray, step: Step) -> np.ndarray:
        """Draw hitbox overlay on frame."""
        if step.action_type == "keyboard":
            # Draw text box for keyboard steps
            x, y = step.x, step.y
            w, h = 300, 50
            
            # Background
            overlay = frame.copy()
            cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 0), -1)
            frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
            
            # Border
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 150, 0), 2)
            
            # Text
            display_text = display_key_combo(step.keyboard_input) if "+" in (step.keyboard_input or "") else step.keyboard_input
            cv2.putText(frame, display_text, (x + 10, y + 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        elif step.action_type == "mouse_drag":
            frame = self._draw_drag_overlay(frame, step)
        else:
            # Draw hitbox for click steps
            x, y = step.x, step.y
            w, h = step.width, step.height
            
            # Semi-transparent overlay
            overlay = frame.copy()
            
            if step.shape == "circle":
                center = (x + w // 2, y + h // 2)
                radius = max(w, h) // 2
                cv2.circle(overlay, center, radius, (0, 0, 255), -1)
                frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
                cv2.circle(frame, center, radius, (0, 0, 255), 2)
            else:
                cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 255), -1)
                frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        
        return frame

    def _draw_drag_overlay(self, frame: np.ndarray, step: Step) -> np.ndarray:
        overlay = frame.copy()

        start_x, start_y = step.x, step.y
        start_w, start_h = step.width, step.height
        end_x = getattr(step, "drag_end_x", step.x)
        end_y = getattr(step, "drag_end_y", step.y)
        end_w = getattr(step, "drag_end_width", step.width)
        end_h = getattr(step, "drag_end_height", step.height)

        start_center = (start_x + start_w // 2, start_y + start_h // 2)
        end_center = (end_x + end_w // 2, end_y + end_h // 2)

        cv2.rectangle(overlay, (start_x, start_y), (start_x + start_w, start_y + start_h), (255, 140, 0), -1)
        cv2.rectangle(overlay, (end_x, end_y), (end_x + end_w, end_y + end_h), (0, 200, 0), -1)
        frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)

        cv2.rectangle(frame, (start_x, start_y), (start_x + start_w, start_y + start_h), (255, 140, 0), 3)
        cv2.rectangle(frame, (end_x, end_y), (end_x + end_w, end_y + end_h), (0, 200, 0), 3)
        cv2.arrowedLine(frame, start_center, end_center, (0, 220, 255), 4, tipLength=0.18)

        label = (step.instruction or step.description or "Drag").strip()
        text_x = min(start_x, end_x)
        text_y = max(min(start_y, end_y) - 18, 32)
        text_w = min(max(len(label) * 11, 260), 700)
        cv2.rectangle(frame, (text_x, text_y - 30), (text_x + text_w, text_y + 8), (0, 0, 0), -1)
        cv2.putText(frame, label, (text_x + 12, text_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        modifier_keys = getattr(step, "modifier_keys", []) or []
        if modifier_keys:
            modifier_text = " + ".join(display_key_name(key) for key in modifier_keys)
            badge_x = start_x
            badge_y = max(36, start_y - 18)
            badge_w = max(120, len(modifier_text) * 12 + 24)
            cv2.rectangle(frame, (badge_x, badge_y - 28), (badge_x + badge_w, badge_y + 4), (15, 23, 42), -1)
            cv2.putText(frame, modifier_text, (badge_x + 10, badge_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (226, 232, 240), 2)

        return frame
    
    def export_gif(self, output_path: str, fps: float = 10.0, scale: float = 0.5) -> bool:
        """Export as GIF (requires Pillow)."""
        try:
            from PIL import Image
        except ImportError:
            print("Pillow is required for GIF export. Install with: pip install Pillow")
            return False
        
        if not self.tutorial.video_path or not os.path.exists(self.tutorial.video_path):
            print("No video file to export")
            return False
        
        cap = cv2.VideoCapture(self.tutorial.video_path)
        if not cap.isOpened():
            return False
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * scale)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * scale)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        source_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        
        # Build step timeline
        step_frames = {}
        for step in self.tutorial.steps:
            frame_num = int(step.timestamp * source_fps)
            step_frames[frame_num] = step
        
        frames = []
        current_step = None
        frame_count = 0
        frame_skip = int(source_fps / fps)  # Skip frames to reduce GIF size
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count in step_frames:
                current_step = step_frames[frame_count]
            
            # Only capture every nth frame
            if frame_count % frame_skip == 0:
                if current_step:
                    frame = self._draw_hitbox_overlay(frame, current_step)
                
                # Resize
                frame = cv2.resize(frame, (width, height))
                
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(Image.fromarray(frame_rgb))
            
            frame_count += 1
            
            if self.progress_callback and total_frames > 0:
                self.progress_callback(int((frame_count / total_frames) * 100))
        
        cap.release()
        
        if frames:
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=int(1000 / fps),
                loop=0
            )
            print(f"Exported GIF to: {output_path}")
            return True
        
        return False
