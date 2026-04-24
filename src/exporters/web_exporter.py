"""
Web Exporter Module
Exports tutorials to HTML, iframe embed, and Lottie animation formats
"""
import os
import json
import base64
import io
import cv2
import numpy as np
from typing import Callable, Optional
from ..model import Tutorial, Step


class WebExporter:
    """Export tutorial to web-friendly formats."""
    
    def __init__(self, tutorial: Tutorial, progress_callback: Optional[Callable[[int], None]] = None):
        self.tutorial = tutorial
        self.progress_callback = progress_callback

    def _serialize_step(self, step: Step, index: int) -> dict:
        guide_image = self._encode_file_as_data_uri(getattr(step, 'guide_image_path', ''))
        if not guide_image and step.action_type == "mouse_drag":
            guide_image = self._generate_drag_guide_gif_data_uri(step)
        return {
            'index': index + 1,
            'description': step.description,
            'instruction': step.instruction,
            'action_type': step.action_type,
            'timestamp': step.timestamp,
            'click_button': step.click_button,
            'drag_button': getattr(step, 'drag_button', 'left'),
            'x': step.x,
            'y': step.y,
            'width': step.width,
            'height': step.height,
            'drag_end_x': getattr(step, 'drag_end_x', step.x),
            'drag_end_y': getattr(step, 'drag_end_y', step.y),
            'drag_end_width': getattr(step, 'drag_end_width', step.width),
            'drag_end_height': getattr(step, 'drag_end_height', step.height),
            'drag_start_timestamp': getattr(step, 'drag_start_timestamp', step.timestamp),
            'drag_end_timestamp': getattr(step, 'drag_end_timestamp', step.timestamp),
            'drag_min_distance': getattr(step, 'drag_min_distance', 30),
            'drag_gif_fps': getattr(step, 'drag_gif_fps', 8.0),
            'drag_gif_preview_size': getattr(step, 'drag_gif_preview_size', 260),
            'drag_direction_arrow_enabled': bool(getattr(step, 'drag_direction_arrow_enabled', True)),
            'drag_direction_arrow_size': int(getattr(step, 'drag_direction_arrow_size', 16) or 16),
            'modifier_keys': list(getattr(step, 'modifier_keys', []) or []),
            'shape': step.shape,
            'keyboard_mode': step.keyboard_mode,
            'keyboard_input': step.keyboard_input,
            'keyboard_space_behavior': getattr(step, 'keyboard_space_behavior', 'submit_step'),
            'keyboard_code': getattr(step, 'keyboard_code', ''),
            'guide_image': guide_image,
        }

    def _encode_file_as_data_uri(self, path: str) -> str:
        if not path or not os.path.exists(path):
            return ""

        extension = os.path.splitext(path)[1].lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
        }.get(extension, "application/octet-stream")

        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode()
        return f"data:{mime_type};base64,{encoded}"

    def _generate_drag_guide_gif_bytes(self, step: Step) -> bytes:
        if step.action_type != "mouse_drag":
            return b""
        if not bool(getattr(step, "auto_drag_gif_enabled", True)):
            return b""
        video_path = getattr(self.tutorial, "video_path", "")
        if not video_path or not os.path.exists(video_path):
            return b""

        try:
            from PIL import Image
        except ImportError:
            return b""

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return b""

        try:
            source_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = (total_frames / source_fps) if total_frames > 0 else max(float(step.timestamp or 0.0), 0.0)

            lead_seconds = max(0.0, float(getattr(step, "drag_gif_lead_seconds", 0.6) or 0.0))
            tail_seconds = max(0.0, float(getattr(step, "drag_gif_tail_seconds", 0.15) or 0.0))
            drag_start_time = float(getattr(step, "drag_start_timestamp", step.timestamp) or 0.0)
            drag_end_time = float(getattr(step, "drag_end_timestamp", step.timestamp) or drag_start_time)
            drag_end_time = max(drag_start_time, drag_end_time)
            start_time = max(0.0, drag_start_time - lead_seconds)
            end_time = min(duration, drag_end_time + tail_seconds) if duration > 0 else drag_end_time + tail_seconds
            if end_time <= start_time:
                end_time = start_time + 0.4

            target_gif_fps = max(1.0, float(getattr(step, "drag_gif_fps", 8.0) or 8.0))
            frame_step = max(1, int(round(source_fps / target_gif_fps)))
            start_frame = max(0, int(start_time * source_fps))
            end_frame = max(start_frame, int(end_time * source_fps))

            start_left = int(step.x)
            start_top = int(step.y)
            start_right = int(step.x + step.width)
            start_bottom = int(step.y + step.height)
            end_left = int(getattr(step, "drag_end_x", step.x))
            end_top = int(getattr(step, "drag_end_y", step.y))
            end_right = int(end_left + getattr(step, "drag_end_width", step.width))
            end_bottom = int(end_top + getattr(step, "drag_end_height", step.height))

            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if frame_width <= 0 or frame_height <= 0:
                return b""

            padding = 36
            crop_left = max(0, min(start_left, end_left) - padding)
            crop_top = max(0, min(start_top, end_top) - padding)
            crop_right = min(frame_width, max(start_right, end_right) + padding)
            crop_bottom = min(frame_height, max(start_bottom, end_bottom) + padding)
            drag_dx = (end_left + end_right) - (start_left + start_right)
            drag_dy = (end_top + end_bottom) - (start_top + start_bottom)
            directional_padding = max(26, int(round(max(abs(drag_dx), abs(drag_dy)) * 0.12)))
            if drag_dx >= 0:
                crop_right = min(frame_width, crop_right + directional_padding)
            else:
                crop_left = max(0, crop_left - directional_padding)
            if drag_dy >= 0:
                crop_bottom = min(frame_height, crop_bottom + directional_padding)
            else:
                crop_top = max(0, crop_top - directional_padding)

            crop_width = crop_right - crop_left
            crop_height = crop_bottom - crop_top
            min_crop_width = min(frame_width, max(180, int(round(crop_height * 0.42))))
            min_crop_height = min(frame_height, max(180, int(round(crop_width * 0.42))))
            if crop_width < min_crop_width:
                extra_width = min_crop_width - crop_width
                crop_left = max(0, crop_left - (extra_width // 2))
                crop_right = min(frame_width, crop_right + (extra_width - (extra_width // 2)))
            if crop_height < min_crop_height:
                extra_height = min_crop_height - crop_height
                crop_top = max(0, crop_top - (extra_height // 2))
                crop_bottom = min(frame_height, crop_bottom + (extra_height - (extra_height // 2)))
            if crop_right <= crop_left or crop_bottom <= crop_top:
                return b""

            local_start_left = start_left - crop_left
            local_start_top = start_top - crop_top
            local_start_right = start_right - crop_left
            local_start_bottom = start_bottom - crop_top
            local_end_left = end_left - crop_left
            local_end_top = end_top - crop_top
            local_end_right = end_right - crop_left
            local_end_bottom = end_bottom - crop_top
            start_center = (
                int(round((local_start_left + local_start_right) / 2)),
                int(round((local_start_top + local_start_bottom) / 2)),
            )
            end_center = (
                int(round((local_end_left + local_end_right) / 2)),
                int(round((local_end_top + local_end_bottom) / 2)),
            )

            def draw_marker(target, left, top, right, bottom, color_bgr, label_text):
                overlay = target.copy()
                line_width = 3
                if getattr(step, "shape", "rect") == "circle":
                    center = (int((left + right) / 2), int((top + bottom) / 2))
                    axes = (max(6, int((right - left) / 2)), max(6, int((bottom - top) / 2)))
                    cv2.ellipse(overlay, center, axes, 0, 0, 360, color_bgr, -1)
                    cv2.addWeighted(overlay, 0.18, target, 0.82, 0, target)
                    cv2.ellipse(target, center, axes, 0, 0, 360, color_bgr, line_width)
                else:
                    cv2.rectangle(overlay, (left, top), (right, bottom), color_bgr, -1)
                    cv2.addWeighted(overlay, 0.18, target, 0.82, 0, target)
                    cv2.rectangle(target, (left, top), (right, bottom), color_bgr, line_width)

                label_w = max(44, len(label_text) * 11 + 12)
                label_h = 24
                label_x = max(4, min(left, target.shape[1] - label_w - 4))
                label_y = max(label_h + 4, top - 8)
                cv2.rectangle(target, (label_x, label_y - label_h), (label_x + label_w, label_y), color_bgr, -1)
                cv2.putText(
                    target,
                    label_text,
                    (label_x + 7, label_y - 7),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

            def draw_drag_direction(target, start_point, end_point):
                if not bool(getattr(step, "drag_direction_arrow_enabled", True)):
                    return
                dx = float(end_point[0] - start_point[0])
                dy = float(end_point[1] - start_point[1])
                length = float(np.hypot(dx, dy))
                if length < 10:
                    return

                arrow_size = max(10.0, min(40.0, float(getattr(step, "drag_direction_arrow_size", 16) or 16)))
                shadow_thickness = max(6, int(round(arrow_size * 0.5)))
                line_thickness = max(3, int(round(arrow_size * 0.25)))
                tip_ratio = max(0.12, min(0.42, arrow_size / max(length, 1.0)))
                unit_x = dx / length
                unit_y = dy / length
                inset = min(28.0, max(8.0, arrow_size * 0.9, length * 0.12))
                line_start = (
                    int(round(start_point[0] + (unit_x * inset))),
                    int(round(start_point[1] + (unit_y * inset))),
                )
                line_end = (
                    int(round(end_point[0] - (unit_x * inset))),
                    int(round(end_point[1] - (unit_y * inset))),
                )
                accent_color = (56, 189, 248)
                shadow_color = (14, 23, 41)
                cv2.arrowedLine(
                    target,
                    line_start,
                    line_end,
                    shadow_color,
                    shadow_thickness,
                    cv2.LINE_AA,
                    0,
                    tip_ratio,
                )
                cv2.arrowedLine(
                    target,
                    line_start,
                    line_end,
                    accent_color,
                    line_thickness,
                    cv2.LINE_AA,
                    0,
                    tip_ratio,
                )
                mid_point = (
                    int(round((line_start[0] + line_end[0]) / 2)),
                    int(round((line_start[1] + line_end[1]) / 2)),
                )
                tick_radius = max(6, int(round(arrow_size * 0.44)))
                tick_start = (
                    int(round(mid_point[0] - (unit_x * tick_radius) - (unit_y * tick_radius))),
                    int(round(mid_point[1] - (unit_y * tick_radius) + (unit_x * tick_radius))),
                )
                tick_end = (
                    int(round(mid_point[0] + (unit_x * tick_radius) + (unit_y * tick_radius))),
                    int(round(mid_point[1] + (unit_y * tick_radius) - (unit_x * tick_radius))),
                )
                cv2.line(target, tick_start, tick_end, shadow_color, max(4, int(round(arrow_size * 0.38))), cv2.LINE_AA)
                cv2.line(target, tick_start, tick_end, accent_color, max(2, int(round(arrow_size * 0.18))), cv2.LINE_AA)

            images = []
            for frame_num in range(start_frame, end_frame + 1, frame_step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                cropped = frame[crop_top:crop_bottom, crop_left:crop_right].copy()
                if cropped.size == 0:
                    continue

                draw_drag_direction(cropped, start_center, end_center)
                draw_marker(cropped, local_start_left, local_start_top, local_start_right, local_start_bottom, (48, 68, 255), "START")
                draw_marker(cropped, local_end_left, local_end_top, local_end_right, local_end_bottom, (34, 197, 94), "END")

                crop_h, crop_w = cropped.shape[:2]
                square_size = max(crop_w, crop_h)
                square_frame = np.full((square_size, square_size, 3), 12, dtype=np.uint8)
                offset_x = (square_size - crop_w) // 2
                offset_y = (square_size - crop_h) // 2
                square_frame[offset_y:offset_y + crop_h, offset_x:offset_x + crop_w] = cropped
                cropped = square_frame
                target_size = max(140, min(640, int(getattr(step, "drag_gif_preview_size", 260) or 260)))
                interpolation = cv2.INTER_AREA if cropped.shape[1] > target_size else cv2.INTER_CUBIC
                cropped = cv2.resize(cropped, (target_size, target_size), interpolation=interpolation)

                rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
                images.append(Image.fromarray(rgb))

            if not images:
                return b""

            output = io.BytesIO()
            images[0].save(
                output,
                format="GIF",
                save_all=True,
                append_images=images[1:],
                duration=max(40, int(round(1000 / target_gif_fps))),
                loop=0,
                optimize=False,
            )
            return output.getvalue()
        except Exception:
            return b""
        finally:
            cap.release()

    def _generate_drag_guide_gif_data_uri(self, step: Step) -> str:
        gif_bytes = self._generate_drag_guide_gif_bytes(step)
        if not gif_bytes:
            return ""
        return "data:image/gif;base64," + base64.b64encode(gif_bytes).decode()

    def _guide_card_config_json(self) -> str:
        config = {
            "language": getattr(self.tutorial, "guide_language", "ko") or "ko",
            "characterImage": self._encode_file_as_data_uri(getattr(self.tutorial, "guide_character_image_path", "")),
            "characterSize": int(getattr(self.tutorial, "guide_character_size", 112) or 112),
            "cardAnchor": getattr(self.tutorial, "guide_card_anchor", "top_fixed") or "top_fixed",
            "cardDirection": getattr(self.tutorial, "guide_card_direction", "auto") or "auto",
            "cardOffset": int(getattr(self.tutorial, "guide_card_offset", 16) or 16),
            "cardTop": int(getattr(self.tutorial, "guide_card_top", 0) or 0),
            "cardLeft": int(getattr(self.tutorial, "guide_card_left", 0) or 0),
            "cardWidth": int(getattr(self.tutorial, "guide_card_width", 680) or 680),
            "cardScale": int(getattr(self.tutorial, "guide_card_scale_percent", 100) or 100),
            "badgeSize": int(getattr(self.tutorial, "guide_step_badge_size", 96) or 96),
            "cardGap": int(getattr(self.tutorial, "guide_card_gap", 18) or 18),
            "cardPadding": int(getattr(self.tutorial, "guide_card_padding", 22) or 22),
            "cardOpacity": int(getattr(self.tutorial, "guide_card_opacity", 94) or 94),
        }
        return json.dumps(config, ensure_ascii=False)

    def _read_video_frame_at_time(self, timestamp: float):
        video_path = getattr(self.tutorial, "video_path", "")
        if not video_path or not os.path.exists(video_path):
            return None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(timestamp * fps)))
            ret, img = cap.read()
            return img if ret else None
        finally:
            cap.release()
    
    def export_html(self, output_path: str, embed_images: bool = True) -> bool:
        """Export as standalone HTML webpage with interactive tutorial."""
        # Prepare step data and images
        steps_data = []
        for i, step in enumerate(self.tutorial.steps):
            step_info = self._serialize_step(step, i)
            step_info['image'] = ''
            step_info['post_drag_image'] = ''
            
            # Get image
            img = None
            if step.image_path and os.path.exists(step.image_path):
                img = cv2.imread(step.image_path)
            elif self.tutorial.video_path and os.path.exists(self.tutorial.video_path):
                img = self._read_video_frame_at_time(float(step.timestamp or 0.0))
            
            if img is not None and embed_images:
                _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                step_info['image'] = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode()

            if step.action_type == "mouse_drag" and self.tutorial.video_path and os.path.exists(self.tutorial.video_path):
                post_drag_frame = self._read_video_frame_at_time(float(getattr(step, "drag_end_timestamp", step.timestamp) or step.timestamp))
                if post_drag_frame is not None and embed_images:
                    _, buffer = cv2.imencode('.jpg', post_drag_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    step_info['post_drag_image'] = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode()
            
            steps_data.append(step_info)
            
            if self.progress_callback:
                self.progress_callback(int((i + 1) / len(self.tutorial.steps) * 50))
        
        html_content = self._generate_html(steps_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        if self.progress_callback:
            self.progress_callback(100)
        
        print(f"Exported HTML to: {output_path}")
        return True
    
    def _generate_html(self, steps_data: list) -> str:
        """Generate interactive HTML content matching Play mode."""
        steps_json = json.dumps(steps_data)
        guide_config_json = self._guide_card_config_json()
        
        return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.tutorial.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            color: white;
            overflow: hidden;
        }}
        
        /* Progress Bar */
        .progress-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: rgba(255,255,255,0.1);
            z-index: 1000;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #9333ea);
            transition: width 0.5s ease;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.5);
        }}
        
        /* Main Canvas Area */
        .canvas-container {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            position: relative;
            cursor: grab;
        }}
        .canvas-container:active {{
            cursor: grabbing;
        }}
        .canvas-inner {{
            position: absolute;
            transform-origin: 0 0;
            transition: transform 0.1s ease-out;
        }}
        .step-image {{
            display: block;
            user-select: none;
            -webkit-user-drag: none;
        }}
        
        /* Hitbox Overlay */
        .hitbox {{
            position: absolute;
            border: 3px solid #ff4444;
            cursor: pointer;
            transition: all 0.3s ease;
            animation: pulse 1.5s infinite, glow 1.5s infinite;
        }}
        .hitbox:hover {{
            transform: scale(1.05);
            border-color: #ffff00;
        }}
        .hitbox.circle {{
            border-radius: 50%;
        }}
        .drag-target {{
            border-color: #22c55e;
            background: rgba(34, 197, 94, 0.25);
            pointer-events: none;
        }}
        .drag-line {{
            position: absolute;
            height: var(--drag-line-thickness, 4px);
            background: linear-gradient(90deg, #f59e0b, #38bdf8);
            transform-origin: 0 50%;
            display: none;
            pointer-events: none;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.45);
            border-radius: 999px;
            overflow: visible;
        }}
        .drag-line.no-arrow::after {{
            display: none;
        }}
        .drag-line::after {{
            content: '';
            position: absolute;
            right: -2px;
            top: 50%;
            width: 0;
            height: 0;
            transform: translateY(-50%);
            border-top: calc(var(--drag-arrow-size, 14px) * 0.57) solid transparent;
            border-bottom: calc(var(--drag-arrow-size, 14px) * 0.57) solid transparent;
            border-left: var(--drag-arrow-size, 14px) solid #38bdf8;
            filter: drop-shadow(0 0 8px rgba(56, 189, 248, 0.55));
        }}
        .modifier-badge {{
            position: absolute;
            display: none;
            padding: 7px 14px;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.9);
            color: #e2e8f0;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.02em;
            pointer-events: none;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.35);
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.03); }}
        }}
        
        @keyframes glow {{
            0%, 100% {{ 
                box-shadow: 0 0 10px rgba(255, 68, 68, 0.5), 
                            0 0 20px rgba(255, 68, 68, 0.3),
                            0 0 30px rgba(255, 68, 68, 0.2);
            }}
            50% {{ 
                box-shadow: 0 0 20px rgba(255, 68, 68, 0.8), 
                            0 0 40px rgba(255, 68, 68, 0.5),
                            0 0 60px rgba(255, 68, 68, 0.3);
            }}
        }}
        
        /* Keyboard Input Modal */
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 500;
        }}
        .modal-overlay.active {{
            display: flex;
        }}
        .modal-content {{
            width: auto;
            max-width: calc(100vw - 32px);
            background: transparent;
            padding: 0;
            border-radius: 0;
            box-shadow: none;
            border: none;
            pointer-events: auto;
            text-align: center;
        }}
        .modal-character {{
            display: none !important;
        }}
        .modal-copy {{
            min-width: 0;
            text-align: center;
        }}
        .modal-title {{
            font-size: clamp(1.55rem, 3vw, 2.45rem);
            font-weight: 800;
            line-height: 1.15;
            color: #ffffff;
            -webkit-text-stroke: 1px rgba(7, 10, 18, 0.82);
            text-shadow:
                0 0 2px rgba(7, 10, 18, 0.95),
                0 0 8px rgba(7, 10, 18, 0.88),
                0 0 20px rgba(56, 189, 248, 0.34),
                0 0 34px rgba(56, 189, 248, 0.22);
        }}
        .modal-hint {{
            color: rgba(255, 255, 255, 0.68);
            margin-top: 14px;
            margin-bottom: 24px;
            line-height: 1.45;
            font-size: 1.08rem;
            -webkit-text-stroke: 0.6px rgba(7, 10, 18, 0.78);
            text-shadow:
                0 0 2px rgba(7, 10, 18, 0.94),
                0 0 6px rgba(7, 10, 18, 0.84),
                0 0 16px rgba(56, 189, 248, 0.18);
        }}
        .modal-input {{
            width: min(360px, 100%);
            padding: 18px 22px;
            font-size: 1.28em;
            border: 2px solid rgba(255,255,255,0.12);
            border-radius: 18px;
            background: rgba(7, 12, 24, 0.20);
            color: white;
            text-align: center;
            outline: none;
            transition: border-color 0.3s;
            position: relative;
            z-index: 2;
        }}
        .modal-input-wrap {{
            position: relative;
            width: min(360px, 100%);
            margin: 0 auto;
        }}
        .modal-input-ghost {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.45);
            pointer-events: none;
            font-size: 1.2em;
            padding: 15px 20px;
            z-index: 3;
        }}
        .modal-input:focus {{
            border-color: #00d2ff;
        }}
        .modal-input.error {{
            border-color: #ff4444;
            animation: shake 0.3s;
        }}
        .modal-input.success {{
            border-color: #4CAF50;
        }}

        .guide-overlay {{
            position: fixed;
            left: 24px;
            top: 24px;
            width: min(680px, calc(100vw - 40px));
            z-index: 420;
            pointer-events: none;
            transition: opacity 0.16s ease;
        }}
        .guide-overlay.hidden {{
            opacity: 0;
            transform: none;
        }}
        .drag-guide-overlay {{
            position: fixed;
            left: 20px;
            top: 20px;
            z-index: 425;
            pointer-events: none;
            opacity: 1;
            transition: opacity 0.16s ease;
        }}
        .drag-guide-overlay.hidden {{
            opacity: 0;
        }}
        .drag-guide-media {{
            display: block;
            width: min(220px, calc(100vw - 32px));
            height: min(220px, calc(100vw - 32px));
            aspect-ratio: 1 / 1;
            object-fit: contain;
            border-radius: 16px;
            border: 1px solid rgba(120, 198, 255, 0.35);
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.34);
            background: rgba(7, 12, 24, 0.82);
        }}
        .guide-card {{
            background: rgba(6, 7, 16, 0.96);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 42px;
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.42);
            backdrop-filter: blur(18px);
            padding: 22px 28px;
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .guide-step-badge {{
            width: 96px;
            height: 96px;
            border-radius: 50%;
            background: linear-gradient(180deg, #ff8e66, #ff6f61);
            color: #ffffff;
            font-size: 2.5rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.24);
        }}
        .guide-character {{
            width: 112px;
            height: 112px;
            border-radius: 26px;
            object-fit: contain;
            object-position: center bottom;
            flex: 0 0 auto;
            display: none;
            background: rgba(255,255,255,0.04);
            padding: 8px;
        }}
        .guide-card.has-character .guide-character {{
            display: block;
        }}
        .guide-copy {{
            min-width: 0;
            flex: 1 1 auto;
        }}
        .guide-title {{
            font-size: clamp(1.85rem, 3vw, 2.4rem);
            font-weight: 700;
            line-height: 1.2;
            color: #f4f5f8;
        }}
        .guide-body {{
            margin-top: 10px;
            font-size: clamp(1.2rem, 2vw, 1.55rem);
            line-height: 1.35;
            color: rgba(255, 255, 255, 0.62);
        }}
        .guide-accent {{
            color: #ffffff;
            font-weight: 800;
        }}
        @media (max-width: 640px) {{
            .guide-overlay {{
                width: calc(100vw - 20px);
                left: 10px;
                top: 10px;
            }}
            .drag-guide-media {{
                width: min(160px, calc(100vw - 20px));
                height: min(160px, calc(100vw - 20px));
            }}
            .guide-card {{
                padding: 14px 16px;
                border-radius: 28px;
                gap: 12px;
            }}
            .guide-step-badge {{
                width: 62px;
                height: 62px;
                font-size: 1.6rem;
            }}
            .guide-character {{
                width: 72px;
                height: 72px;
                border-radius: 18px;
            }}
            .guide-title {{
                font-size: 1.15rem;
            }}
            .guide-body {{
                font-size: 0.95rem;
            }}
        }}
        
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            25% {{ transform: translateX(-10px); }}
            75% {{ transform: translateX(10px); }}
        }}
        
        /* Zoom Controls */
        .zoom-controls {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 100;
        }}
        .zoom-btn {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            border: none;
            background: rgba(0,0,0,0.7);
            color: white;
            font-size: 1.5em;
            cursor: pointer;
            transition: all 0.2s;
            backdrop-filter: blur(10px);
        }}
        .zoom-btn:hover {{
            background: rgba(0,150,255,0.7);
            transform: scale(1.1);
        }}
        
        /* Start/Completion Screen */
        .screen-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            transition: opacity 0.5s;
        }}
        .screen-overlay.hidden {{
            opacity: 0;
            pointer-events: none;
        }}
        .screen-title {{
            font-size: 3em;
            margin-bottom: 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .screen-subtitle {{
            font-size: 1.3em;
            color: #888;
            margin-bottom: 40px;
        }}
        .screen-btn {{
            padding: 20px 60px;
            font-size: 1.3em;
            border: none;
            border-radius: 50px;
            background: linear-gradient(135deg, #00d2ff, #3a7bd5);
            color: white;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(0, 210, 255, 0.3);
        }}
        .screen-btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(0, 210, 255, 0.4);
        }}
        .completion-icon {{
            font-size: 5em;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <!-- Progress Bar -->
    <div class="progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>
    
    <!-- Main Canvas -->
    <div class="canvas-container" id="canvasContainer">
        <div class="canvas-inner" id="canvasInner">
            <img class="step-image" id="stepImage" src="" alt="">
            <div class="hitbox" id="hitbox"></div>
            <div class="hitbox drag-target" id="dragTarget"></div>
            <div class="drag-line" id="dragLine"></div>
            <div class="modifier-badge" id="modifierBadge"></div>
        </div>
    </div>

    <div class="guide-overlay hidden" id="guideOverlay">
        <div class="guide-card">
            <div class="guide-step-badge" id="stepBadge"></div>
            <div class="guide-copy">
                <div class="guide-title" id="stepDesc"></div>
                <div class="guide-body" id="stepInstruction"></div>
            </div>
            <img class="guide-character" id="guideCharacter" alt="">
        </div>
    </div>

    <div class="drag-guide-overlay hidden" id="dragGuideOverlay">
        <img class="drag-guide-media" id="dragGuideMedia" alt="">
    </div>
    
    <!-- Keyboard Modal -->
    <div class="modal-overlay" id="keyboardModal">
        <div class="modal-content">
            <div class="modal-copy">
                <div class="modal-title" id="modalTitle"></div>
                <div class="modal-hint" id="modalHint"></div>
                <div class="modal-input-wrap" id="modalInputWrap">
                    <input type="text" class="modal-input" id="modalInput" autocomplete="off">
                    <div class="modal-input-ghost" id="modalInputGhost"></div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Zoom Controls -->
    <div class="zoom-controls">
        <button class="zoom-btn" onclick="zoomIn()">+</button>
        <button class="zoom-btn" onclick="zoomOut()">−</button>
        <button class="zoom-btn" onclick="resetZoom()">⟲</button>
    </div>
    
    <!-- Start Screen -->
    <div class="screen-overlay" id="startScreen">
        <div class="screen-title">{self.tutorial.title}</div>
        <div class="screen-subtitle">{self.tutorial.start_subtitle}</div>
        <button class="screen-btn" id="startBtn" onclick="startTutorial()">{self.tutorial.start_button_text}</button>
    </div>
    
    <!-- Completion Screen -->
    <div class="screen-overlay hidden" id="completionScreen">
        <div class="completion-icon">🎉</div>
        <div class="screen-title">{self.tutorial.completion_title}</div>
        <div class="screen-subtitle">{self.tutorial.completion_subtitle}</div>
        <button class="screen-btn" onclick="restartTutorial()">{self.tutorial.restart_button_text}</button>
    </div>
    
    <script>
        const steps = {steps_json};
        const guideConfig = {guide_config_json};
        let currentStep = 0;
        let scale = 1;
        let panX = 0, panY = 0;
        let isDragging = false;
        let dragStart = {{x: 0, y: 0}};
        let hasStarted = false;
        
        const canvasContainer = document.getElementById('canvasContainer');
        const canvasInner = document.getElementById('canvasInner');
        const stepImage = document.getElementById('stepImage');
        const hitbox = document.getElementById('hitbox');
        const dragTarget = document.getElementById('dragTarget');
        const dragLine = document.getElementById('dragLine');
        const modifierBadge = document.getElementById('modifierBadge');
        const keyboardModal = document.getElementById('keyboardModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalInput = document.getElementById('modalInput');
        const modalHint = document.getElementById('modalHint');
        const modalInputGhost = document.getElementById('modalInputGhost');
        const modalInputWrap = document.getElementById('modalInputWrap');
        const guideOverlay = document.getElementById('guideOverlay');
        const dragGuideOverlay = document.getElementById('dragGuideOverlay');
        const dragGuideMedia = document.getElementById('dragGuideMedia');
        const guideCharacter = document.getElementById('guideCharacter');
        const stepBadge = document.getElementById('stepBadge');
        const stepDesc = document.getElementById('stepDesc');
        const stepInstruction = document.getElementById('stepInstruction');
        let tutorialDrag = null;
        const pressedModifierKeys = new Set();
        
        // Initialize
        function init() {{
            setupPanZoom();
            preloadImages();
        }}
        
        function preloadImages() {{
            steps.forEach(step => {{
                const img = new Image();
                img.src = step.image;
            }});
        }}
        
        function startTutorial() {{
            hasStarted = true;
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('startBtn').textContent = {json.dumps(self.tutorial.restart_button_text)};
            renderStep(0);
        }}
        
        function restartTutorial() {{
            currentStep = 0;
            document.getElementById('completionScreen').classList.add('hidden');
            renderStep(0);
        }}
        
        function renderStep(index) {{
            if (index >= steps.length) {{
                showCompletion();
                return;
            }}
            
            const step = steps[index];
            currentStep = index;
            
            // Update progress
            document.getElementById('progressBar').style.width = ((index + 1) / steps.length * 100) + '%';
            
            // Update image with onload handler for fit
            stepImage.onload = function() {{
                fitToWindow();
                updateHitbox(step);
            }};
            stepImage.src = step.image;
        }}
        
        function updateHitbox(step) {{
            // Update hitbox after image is loaded and fitted
            // Hitbox is INSIDE canvasInner which has CSS transform, so use ORIGINAL coordinates
            hidePointerOverlays();
            showGuide(step);
            if (step.action_type === 'keyboard') {{
                showKeyboardModal(step);
            }} else if (step.action_type === 'mouse_drag') {{
                hideKeyboardModal();
                positionDragOverlay(step);
            }} else {{
                hideKeyboardModal();
                positionClickHitbox(step);
            }}
        }}

        function hidePointerOverlays() {{
            tutorialDrag = null;
            hitbox.style.display = 'none';
            dragTarget.style.display = 'none';
            dragLine.style.display = 'none';
            modifierBadge.style.display = 'none';
        }}

        function positionClickHitbox(step) {{
            hitbox.style.display = 'block';
            hitbox.style.left = step.x + 'px';
            hitbox.style.top = step.y + 'px';
            hitbox.style.width = step.width + 'px';
            hitbox.style.height = step.height + 'px';
            hitbox.className = 'hitbox' + (step.shape === 'circle' ? ' circle' : '');
            hitbox.style.background = 'rgba(255, 68, 68, 0.3)';
        }}

        function positionDragOverlay(step) {{
            positionClickHitbox(step);
            dragTarget.style.display = 'block';
            dragTarget.style.left = step.drag_end_x + 'px';
            dragTarget.style.top = step.drag_end_y + 'px';
            dragTarget.style.width = step.drag_end_width + 'px';
            dragTarget.style.height = step.drag_end_height + 'px';
            dragTarget.className = 'hitbox drag-target' + (step.shape === 'circle' ? ' circle' : '');

            const startCenter = {{
                x: step.x + (step.width / 2),
                y: step.y + (step.height / 2)
            }};
            const endCenter = {{
                x: step.drag_end_x + (step.drag_end_width / 2),
                y: step.drag_end_y + (step.drag_end_height / 2)
            }};
            const dx = endCenter.x - startCenter.x;
            const dy = endCenter.y - startCenter.y;
            const arrowEnabled = step.drag_direction_arrow_enabled !== false;
            const arrowSize = Math.max(10, Math.min(40, Number(step.drag_direction_arrow_size || 16)));
            const lineThickness = Math.max(3, Math.round(arrowSize * 0.25));

            dragLine.style.display = 'block';
            dragLine.style.left = startCenter.x + 'px';
            dragLine.style.top = startCenter.y + 'px';
            dragLine.style.width = Math.max(18, Math.hypot(dx, dy) - 8) + 'px';
            dragLine.style.transform = `rotate(${{Math.atan2(dy, dx)}}rad)`;
            dragLine.style.setProperty('--drag-arrow-size', `${{arrowSize}}px`);
            dragLine.style.setProperty('--drag-line-thickness', `${{lineThickness}}px`);
            dragLine.classList.toggle('no-arrow', !arrowEnabled);
            const modifierText = (step.modifier_keys || []).join(' + ').replace(/\\b\\w/g, ch => ch.toUpperCase());
            if (modifierText) {{
                modifierBadge.style.display = 'block';
                modifierBadge.textContent = modifierText;
                modifierBadge.style.left = step.x + 'px';
                modifierBadge.style.top = Math.max(12, step.y - 42) + 'px';
            }}
            tutorialDrag = {{
                active: false,
                validDistance: false,
                startPoint: null
            }};
        }}

        function pointInStepArea(step, x, y, useDragEnd = false) {{
            const left = useDragEnd ? step.drag_end_x : step.x;
            const top = useDragEnd ? step.drag_end_y : step.y;
            const width = useDragEnd ? step.drag_end_width : step.width;
            const height = useDragEnd ? step.drag_end_height : step.height;

            if (step.shape === 'circle') {{
                const rx = width / 2;
                const ry = height / 2;
                if (rx <= 0 || ry <= 0) return false;
                const cx = left + rx;
                const cy = top + ry;
                const dx = (x - cx) / rx;
                const dy = (y - cy) / ry;
                return (dx * dx) + (dy * dy) <= 1;
            }}

            return x >= left && x <= left + width && y >= top && y <= top + height;
        }}

        function clientToImagePoint(clientX, clientY) {{
            const rect = canvasInner.getBoundingClientRect();
            return {{
                x: (clientX - rect.left) / scale,
                y: (clientY - rect.top) / scale
            }};
        }}

        function mouseButtonName(button) {{
            if (button === 1) return 'middle';
            if (button === 2) return 'right';
            return 'left';
        }}

        function normalizeModifierKey(key) {{
            const value = (key || '').toLowerCase();
            if (value === 'control') return 'ctrl';
            if (value === 'shift') return 'shift';
            if (value === 'alt') return 'alt';
            if (value === 'meta' || value === 'os') return 'cmd';
            if (value === ' ' || value === 'spacebar' || value === 'space') return 'space';
            return '';
        }}

        function eventKeyName(e) {{
            if ((e.code || '') === 'Space') return 'space';
            const rawKey = e.key === 'Spacebar' ? 'space' : e.key;
            return normalizeKeyName(rawKey);
        }}

        function requiredModifiersMatch(step) {{
            const required = step.modifier_keys || [];
            return required.every(key => pressedModifierKeys.has(key));
        }}

        function normalizeKeyName(value) {{
            const input = (value || '').toLowerCase().trim();
            if (input.length === 1) {{
                const code = input.charCodeAt(0);
                if (code >= 1 && code <= 26) {{
                    return String.fromCharCode(96 + code);
                }}
            }}
            if (input.startsWith('key.')) return normalizeKeyName(input.substring(4));
            const aliases = {{
                'escape': 'esc',
                'return': 'enter',
                'del': 'delete',
                'arrowup': 'up',
                'arrowdown': 'down',
                'arrowleft': 'left',
                'arrowright': 'right',
                'page_up': 'pageup',
                'page_down': 'pagedown',
                'control': 'ctrl',
                'meta': 'cmd',
                ' ': 'space',
                'spacebar': 'space'
            }};
            return aliases[input] || input;
        }}

        function normalizeKeyCombo(value) {{
            const parts = (value || '').split('+').map(part => normalizeKeyName(part)).filter(Boolean);
            const modifierOrder = ['ctrl', 'shift', 'alt', 'cmd', 'space'];
            const modifiers = [];
            let mainKey = '';

            for (const part of parts) {{
                if (modifierOrder.includes(part)) {{
                    if (!modifiers.includes(part)) modifiers.push(part);
                }} else if (!mainKey) {{
                    mainKey = part;
                }}
            }}

            modifiers.sort((a, b) => modifierOrder.indexOf(a) - modifierOrder.indexOf(b));
            if (mainKey) modifiers.push(mainKey);
            return modifiers.join('+');
        }}

        function formatKeyPart(value) {{
            const normalized = normalizeKeyName(value);
            if (/^f\\d+$/.test(normalized)) return normalized.toUpperCase();
            if (/^[a-z]$/.test(normalized)) return normalized.toUpperCase();
            return normalized.replace(/\\b\\w/g, ch => ch.toUpperCase());
        }}

        function formatKeyCombo(value) {{
            const normalized = normalizeKeyCombo(value);
            if (!normalized) return '';
            return normalized.split('+').map(formatKeyPart).join(' + ');
        }}

        function formatMouseButton(value) {{
            const button = (value || 'left').toLowerCase();
            if (button === 'right') return 'Right click';
            if (button === 'middle') return 'Middle click';
            return 'Left click';
        }}

        function escapeHtml(value) {{
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function guideStrings() {{
            const language = (guideConfig.language || 'ko').toLowerCase();
            if (language === 'en') {{
                return {{
                    keyboardStep: 'Keyboard Step',
                    typingStep: 'Typing Step',
                    dragStep: 'Drag Step',
                    clickStep: 'Click Step',
                    press: 'Press',
                    type: 'Type',
                    leftClick: 'Left click',
                    rightClick: 'Right click',
                    middleClick: 'Middle click',
                    highlightedArea: 'the highlighted area',
                    dragWith: 'Drag with',
                    fromRedToBlue: 'from the red area to the blue target',
                    pressComboBody: 'Press the highlighted key combination to continue.',
                    typeBody: 'Type the requested text, then press Enter to submit.',
                    typeBodySubmit: 'Type the requested text, then press Enter or Space to submit.',
                    dragBody: 'Start inside the red area and finish inside the blue target.',
                    clickBody: 'Click the highlighted area to continue.',
                    holdPrefix: 'Hold',
                    holdWhileDragging: 'while dragging.',
                    holdWhileClicking: 'while clicking.',
                }};
            }}
            return {{
                keyboardStep: '키보드 단계',
                typingStep: '텍스트 입력 단계',
                dragStep: '드래그 단계',
                clickStep: '클릭 단계',
                press: '누르기',
                type: '입력하기',
                leftClick: '왼쪽 클릭',
                rightClick: '오른쪽 클릭',
                middleClick: '가운데 클릭',
                highlightedArea: '강조된 영역',
                dragWith: '',
                fromRedToBlue: '빨간 영역에서 파란 대상까지 이동하세요',
                pressComboBody: '표시된 키 또는 조합 키를 눌러 다음 단계로 진행하세요.',
                typeBody: '요청된 텍스트를 입력한 뒤 Enter를 눌러 제출하세요.',
                typeBodySubmit: '요청된 텍스트를 입력한 뒤 Enter 또는 Space를 눌러 제출하세요.',
                dragBody: '빨간 영역에서 시작해서 파란 대상 안에서 드래그를 마치세요.',
                clickBody: '강조된 영역을 클릭해 다음 단계로 진행하세요.',
                holdPrefix: '',
                holdWhileDragging: ' 키를 누른 상태로 드래그하세요.',
                holdWhileClicking: ' 키를 누른 상태로 클릭하세요.',
            }};
        }}
        function getStepGuide(step) {{
            const strings = guideStrings();
            const customInstruction = (step.instruction || '').trim();
            const customTitle = (step.description || '').trim();
            if (step.action_type === 'keyboard') {{
                const expectedInput = normalizeKeyCombo(step.keyboard_input);
                const comboParts = expectedInput.split('+').filter(Boolean);
                const comboMainKey = comboParts.length ? comboParts[comboParts.length - 1] : '';
                const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter', 'space',
                    'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                    'insert', 'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen',
                    'ctrl', 'alt', 'shift', 'cmd'];
                const isFkey = comboMainKey.startsWith('f') && comboMainKey.length > 1 && !isNaN(comboMainKey.substring(1));
                const inferredSpecial = comboParts.length > 1 || specialKeys.includes(comboMainKey) || isFkey;
                const usesLegacyInference = !step.keyboard_mode;
                const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);
                if (isSpecial) {{
                    const comboLabel = formatKeyCombo(expectedInput || step.keyboard_input);
                    return {{
                        eyebrow: strings.keyboardStep,
                        title: customTitle ? escapeHtml(customTitle) : `${{strings.press}} <span class="guide-accent">${{escapeHtml(comboLabel)}}</span>`,
                        body: customInstruction ? escapeHtml(customInstruction) : strings.pressComboBody
                    }};
                }}
                const typeBody = (step.keyboard_space_behavior || 'submit_step') === 'submit_step'
                    ? strings.typeBodySubmit
                    : strings.typeBody;
                return {{
                    eyebrow: strings.typingStep,
                    title: customTitle ? escapeHtml(customTitle) : `${{strings.type}} <span class="guide-accent">${{escapeHtml(step.keyboard_input || '')}}</span>`,
                    body: customInstruction ? escapeHtml(customInstruction) : typeBody
                }};
            }}

            if (step.action_type === 'mouse_drag') {{
                const modifierText = (step.modifier_keys || []).map(formatKeyPart).join(' + ');
                const actionText = formatMouseButton(step.drag_button).replace(' click', '');
                const translatedAction = translateMouseButton(step.drag_button);
                const fallbackTitle = strings.dragWith
                    ? `${{strings.dragWith}} <span class="guide-accent">${{escapeHtml(translatedAction || actionText)}}</span> ${{strings.fromRedToBlue}}`
                    : `<span class="guide-accent">${{escapeHtml(translatedAction || actionText)}}</span> ${{strings.fromRedToBlue}}`;
                return {{
                    eyebrow: strings.dragStep,
                    title: customTitle ? escapeHtml(customTitle) : fallbackTitle,
                    body: customInstruction ? escapeHtml(customInstruction) : ''
                }};
            }}

            const modifierText = (step.modifier_keys || []).map(formatKeyPart).join(' + ');
            const fallbackClickTitle = `${{translateMouseButton(step.click_button)}} ${{strings.highlightedArea}}`;
            return {{
                eyebrow: strings.clickStep,
                title: customTitle ? escapeHtml(customTitle) : fallbackClickTitle,
                body: customInstruction ? escapeHtml(customInstruction) : ''
            }};
        }}


        function translateMouseButton(value) {{
            const strings = guideStrings();
            const button = (value || 'left').toLowerCase();
            if (button === 'right') return strings.rightClick;
            if (button === 'middle') return strings.middleClick;
            return strings.leftClick;
        }}

        function resolveGuideCharacter(step) {{
            return step.guide_image || guideConfig.characterImage || '';
        }}

        function stepUsesDragGuideGif(step) {{
            return step.action_type === 'mouse_drag' && /^data:image\\/gif;base64,/i.test(step.guide_image || '');
        }}

        function clampToViewport(value, size, minValue, maxValue) {{
            return Math.min(Math.max(minValue, value), Math.max(minValue, maxValue - size));
        }}

        function candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin) {{
            const clampedLeft = clampToViewport(candidate.left, overlayWidth, margin, window.innerWidth - margin);
            const clampedTop = clampToViewport(candidate.top, overlayHeight, margin, window.innerHeight - margin);
            const overlapWidth = Math.max(0, Math.min(clampedLeft + overlayWidth, actionRight + margin) - Math.max(clampedLeft, actionLeft - margin));
            const overlapHeight = Math.max(0, Math.min(clampedTop + overlayHeight, actionBottom + margin) - Math.max(clampedTop, actionTop - margin));
            const visibleWidth = Math.max(0, Math.min(window.innerWidth - margin, clampedLeft + overlayWidth) - Math.max(margin, clampedLeft));
            const visibleHeight = Math.max(0, Math.min(window.innerHeight - margin, clampedTop + overlayHeight) - Math.max(margin, clampedTop));
            return {{
                left: clampedLeft,
                top: clampedTop,
                overlapArea: overlapWidth * overlapHeight,
                visibleArea: visibleWidth * visibleHeight,
                score: candidate.score || 0,
            }};
        }}

        function positionDragGuideNearAction(step) {{
            const margin = 12;
            const overlayWidth = dragGuideOverlay.offsetWidth || 220;
            const overlayHeight = dragGuideOverlay.offsetHeight || 160;
            const canvasRect = canvasInner.getBoundingClientRect();
            const offset = Math.max(28, Number(guideConfig.cardOffset || 16));
            const actionLeft = canvasRect.left + (Math.min(step.x, step.drag_end_x) * scale);
            const actionTop = canvasRect.top + (Math.min(step.y, step.drag_end_y) * scale);
            const actionRight = canvasRect.left + (Math.max(step.x + step.width, step.drag_end_x + step.drag_end_width) * scale);
            const actionBottom = canvasRect.top + (Math.max(step.y + step.height, step.drag_end_y + step.drag_end_height) * scale);
            const actionCenterX = (actionLeft + actionRight) / 2;
            const actionCenterY = (actionTop + actionBottom) / 2;
            const dragDx = (step.drag_end_x + (step.drag_end_width / 2)) - (step.x + (step.width / 2));
            const dragDy = (step.drag_end_y + (step.drag_end_height / 2)) - (step.y + (step.height / 2));

            const sideCandidates = [
                {{
                    left: actionRight + offset,
                    top: actionCenterY - (overlayHeight / 2),
                    score: window.innerWidth - actionRight,
                }},
                {{
                    left: actionLeft - overlayWidth - offset,
                    top: actionCenterY - (overlayHeight / 2),
                    score: actionLeft,
                }},
            ];
            const verticalCandidates = [
                {{
                    left: actionCenterX - (overlayWidth / 2),
                    top: actionBottom + offset,
                    score: window.innerHeight - actionBottom,
                }},
                {{
                    left: actionCenterX - (overlayWidth / 2),
                    top: actionTop - overlayHeight - offset,
                    score: actionTop,
                }},
            ];
            const candidates = Math.abs(dragDx) >= Math.abs(dragDy) ? [...verticalCandidates, ...sideCandidates] : [...sideCandidates, ...verticalCandidates];

            const rankedCandidates = candidates
                .map((candidate) => candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin))
                .sort((a, b) => {{
                    if (a.overlapArea !== b.overlapArea) return a.overlapArea - b.overlapArea;
                    if (a.visibleArea !== b.visibleArea) return b.visibleArea - a.visibleArea;
                    return b.score - a.score;
                }});

            const bestCandidate = rankedCandidates[0] || {{ left: margin, top: margin }};
            const left = bestCandidate.left;
            const top = bestCandidate.top;

            dragGuideOverlay.style.left = `${{left}}px`;
            dragGuideOverlay.style.top = `${{top}}px`;
        }}

        function positionGuideNearAction(step) {{
            const margin = 12;
            const anchorMode = (guideConfig.cardAnchor || 'top_fixed').toLowerCase();
            const horizontalOffset = Number(guideConfig.cardLeft || 0);
            const verticalOffset = Number(guideConfig.cardTop || 0);
            const cardScale = Math.min(200, Math.max(50, Number(guideConfig.cardScale || 100))) / 100;
            const fixedWidth = Math.max(280, Number(guideConfig.cardWidth || 680));
            const availableWidth = Math.max(220, window.innerWidth - 40);
            const baseWidth = Math.max(220, Math.min(fixedWidth, Math.round(availableWidth / Math.max(cardScale, 0.01))));
            guideOverlay.style.width = `${{baseWidth}}px`;
            guideOverlay.style.transformOrigin = 'top left';
            guideOverlay.style.transform = `scale(${{cardScale}})`;
            const overlayWidth = baseWidth * cardScale;
            const overlayHeight = (guideOverlay.offsetHeight || 140) * cardScale;
            if (anchorMode === 'top_fixed') {{
                const centeredLeft = Math.round((window.innerWidth - overlayWidth) / 2);
                const baseTop = 24;
                guideOverlay.style.left = `${{Math.max(margin, Math.min(centeredLeft + horizontalOffset, window.innerWidth - overlayWidth - margin))}}px`;
                guideOverlay.style.top = `${{Math.max(margin, Math.min(baseTop + verticalOffset, window.innerHeight - overlayHeight - margin))}}px`;
                guideOverlay.style.bottom = 'auto';
                return;
            }}
            const canvasRect = canvasInner.getBoundingClientRect();
            let anchorX = canvasRect.left + ((step.x + (step.width / 2)) * scale);
            let anchorY = canvasRect.top + ((step.y + (step.height / 2)) * scale);

            if (step.action_type === 'mouse_drag') {{
                anchorX = canvasRect.left + ((step.drag_end_x + (step.drag_end_width / 2)) * scale);
                anchorY = canvasRect.top + ((step.drag_end_y + (step.drag_end_height / 2)) * scale);
            }}

            const preferredDirection = (guideConfig.cardDirection || 'auto').toLowerCase();
            const offset = Math.max(28, Number(guideConfig.cardOffset || 16));
            let left = anchorX + offset;
            let top = anchorY - (overlayHeight / 2);

            if (preferredDirection === 'left') {{
                left = anchorX - overlayWidth - offset;
            }} else if (preferredDirection === 'top') {{
                left = anchorX - (overlayWidth / 2);
                top = anchorY - overlayHeight - offset;
            }} else if (preferredDirection === 'bottom') {{
                left = anchorX - (overlayWidth / 2);
                top = anchorY + offset;
            }} else if (preferredDirection === 'right') {{
                left = anchorX + offset;
            }} else if (left + overlayWidth > window.innerWidth - margin) {{
                left = anchorX - overlayWidth - offset;
            }}
            if (left < margin) left = margin;
            if (top < margin) top = margin;
            if (top + overlayHeight > window.innerHeight - margin) {{
                top = Math.max(margin, window.innerHeight - overlayHeight - margin);
            }}

            guideOverlay.style.left = `${{left}}px`;
            guideOverlay.style.top = `${{top}}px`;
            guideOverlay.style.bottom = 'auto';
        }}

        function showGuide(step) {{
            if (stepUsesDragGuideGif(step)) {{
                const gifWidth = Math.max(140, Math.min(520, Number(step.drag_gif_preview_size || 260)));
                dragGuideMedia.src = step.guide_image;
                dragGuideMedia.alt = guideConfig.language === 'en' ? 'Drag guide animation' : '드래그 가이드 애니메이션';
                dragGuideMedia.style.width = `${{gifWidth}}px`;
                dragGuideMedia.style.height = `${{gifWidth}}px`;
                positionDragGuideNearAction(step);
                dragGuideOverlay.classList.remove('hidden');
            }} else {{
                dragGuideMedia.removeAttribute('src');
                dragGuideMedia.alt = '';
                dragGuideOverlay.classList.add('hidden');
            }}
            const guide = getStepGuide(step);
            const guideCard = guideOverlay.querySelector('.guide-card');
            const characterSize = Math.max(48, Number(guideConfig.characterSize || 112));
            const cardGap = Math.max(0, Number(guideConfig.cardGap || 18));
            const cardPadding = Math.max(10, Number(guideConfig.cardPadding || 22));
            const cardOpacity = Math.min(100, Math.max(0, Number(guideConfig.cardOpacity ?? 94))) / 100;
            const cardBlur = 18 * cardOpacity;
            const outlineAlpha = 0.16;
            const badgeSize = Math.max(52, Number(guideConfig.badgeSize || 96));
            guideCard.style.gap = `${{cardGap}}px`;
            guideCard.style.padding = `${{Math.max(14, Math.round(cardPadding))}}px ${{Math.max(18, Math.round(cardPadding * 1.25))}}px`;
            guideCard.style.background = `rgba(6, 7, 16, ${{(cardOpacity * 0.98).toFixed(3)}})`;
            guideCard.style.borderColor = `rgba(255, 255, 255, ${{outlineAlpha.toFixed(3)}})`;
            guideCard.style.boxShadow = `0 18px 48px rgba(0, 0, 0, ${{(cardOpacity * 0.5).toFixed(3)}})`;
            guideCard.style.backdropFilter = cardBlur > 0 ? `blur(${{cardBlur.toFixed(2)}}px)` : 'none';
            guideCard.style.webkitBackdropFilter = cardBlur > 0 ? `blur(${{cardBlur.toFixed(2)}}px)` : 'none';
            guideCard.style.transform = 'none';
            guideCharacter.style.width = `${{characterSize}}px`;
            guideCharacter.style.height = `${{characterSize}}px`;
            stepBadge.style.width = `${{badgeSize}}px`;
            stepBadge.style.height = `${{badgeSize}}px`;
            stepBadge.style.fontSize = `${{Math.max(22, Math.round(badgeSize * 0.42))}}px`;
            stepBadge.textContent = String(step.index || '');
            stepDesc.innerHTML = guide.title;
            stepInstruction.innerHTML = guide.body;
            stepInstruction.style.display = guide.body ? 'block' : 'none';
            const characterImage = resolveGuideCharacter(step);
            if (characterImage) {{
                guideCharacter.src = characterImage;
                guideCharacter.alt = guideConfig.language === 'en' ? 'Guide character' : '가이드 캐릭터';
                guideCard.classList.add('has-character');
            }} else {{
                guideCharacter.removeAttribute('src');
                guideCharacter.alt = '';
                guideCard.classList.remove('has-character');
            }}
            positionGuideNearAction(step);
            guideOverlay.classList.remove('hidden');
        }}

        function hideGuide() {{
            guideOverlay.classList.add('hidden');
            dragGuideOverlay.classList.add('hidden');
            dragGuideMedia.removeAttribute('src');
            dragGuideMedia.alt = '';
        }}

        function normalizeKeyCode(value) {{
            return (value || '').trim();
        }}

        function eventKeyCode(e) {{
            return normalizeKeyCode(e.code);
        }}

        function normalizeTextInput(value) {{
            return (value || '')
                .trim()
                .toLowerCase()
                .replace(/\\s*,\\s*/g, ',')
                .replace(/\\s+/g, ' ');
        }}

        function eventMatchesExpectedInput(e, expectedInput, expectedCode) {{
            const normalizedExpected = normalizeKeyCombo(expectedInput);
            const normalizedCode = normalizeKeyCode(expectedCode);
            if (!normalizedExpected.includes('+')) {{
                if (normalizedCode) return eventKeyCode(e) === normalizedCode;
                return eventKeyName(e) === normalizedExpected;
            }}

            const parts = normalizedExpected.split('+');
            const expectedMain = parts[parts.length - 1];
            const requiredModifiers = new Set(parts.slice(0, -1));
            const actualMainName = eventKeyName(e);
            const activeModifiers = new Set([
                e.ctrlKey ? 'ctrl' : '',
                e.shiftKey ? 'shift' : '',
                e.altKey ? 'alt' : '',
                e.metaKey ? 'cmd' : '',
                actualMainName === 'space' ? 'space' : ''
            ].filter(Boolean));

            if (activeModifiers.has(actualMainName)) {{
                activeModifiers.delete(actualMainName);
            }}

            const mainMatches = normalizedCode
                ? eventKeyCode(e) === normalizedCode
                : actualMainName === expectedMain;

            return mainMatches &&
                requiredModifiers.size === activeModifiers.size &&
                Array.from(requiredModifiers).every(key => activeModifiers.has(key));
        }}

        function showKeyboardModal(step) {{
            keyboardModal.classList.add('active');
            keyboardModal.tabIndex = -1;
            keyboardModal.focus();
            modalInput.value = '';
            modalInput.className = 'modal-input';
            document.onkeydown = null;
            let expectedInput = normalizeKeyCombo(step.keyboard_input);
            const expectedCode = normalizeKeyCode(step.keyboard_code);
            const expectedText = normalizeTextInput(step.keyboard_input);
            const spaceSubmits = (step.keyboard_space_behavior || 'submit_step') === 'submit_step';
            
            const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter', 'space',
                'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                'insert', 'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen',
                'ctrl', 'alt', 'shift', 'cmd'];
            const comboParts = expectedInput.split('+').filter(Boolean);
            const comboMainKey = comboParts.length ? comboParts[comboParts.length - 1] : '';
            const isFkey = comboMainKey.startsWith('f') && comboMainKey.length > 1 && !isNaN(comboMainKey.substring(1));
            const inferredSpecial = comboParts.length > 1 || specialKeys.includes(comboMainKey) || isFkey;
            const usesLegacyInference = !step.keyboard_mode;
            const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);
            const customInstruction = (step.instruction || '').trim();
            const defaultSpecialInstruction = isSpecial
                ? (guideConfig.language === 'en'
                    ? `Press ${{formatKeyCombo(expectedInput)}} to continue.`
                    : `${{formatKeyCombo(expectedInput)}} 키를 눌러 다음 단계로 진행하세요.`)
                : '';
            const titleMessage = isSpecial
                ? ((step.description || '').trim() || `Press ${{formatKeyCombo(expectedInput)}}`)
                : '';
            const hintMessage = isSpecial
                ? (customInstruction || defaultSpecialInstruction)
                : '';
            modalTitle.textContent = titleMessage;
            modalTitle.style.display = titleMessage ? 'block' : 'none';
            modalHint.textContent = hintMessage;
            modalHint.style.display = hintMessage ? 'block' : 'none';
            
            if (isSpecial) {{
                modalInput.style.display = 'none';
                modalInputWrap.style.display = 'none';
                modalInputGhost.textContent = '';
                modalInputGhost.style.display = 'none';
            }} else {{
                modalInput.style.display = 'block';
                modalInputWrap.style.display = 'block';
                modalInputGhost.textContent = step.keyboard_input || '';
                modalInputGhost.style.display = 'flex';
                modalInput.focus();
            }}
            
            document.onkeydown = function(e) {{
                if (isSpecial && eventMatchesExpectedInput(e, expectedInput, expectedCode)) {{
                    e.preventDefault();
                    modalInput.className = 'modal-input success';
                    setTimeout(() => {{
                        hideKeyboardModal();
                        nextStep();
                    }}, 200);
                    return;
                }}
                let keyName = e.key.toLowerCase();
                
                if (e.key === 'Delete') keyName = 'delete';
                else if (e.key === 'Backspace') keyName = 'backspace';
                else if (e.key === 'Tab') keyName = 'tab';
                else if (e.key === 'Escape') keyName = 'esc';
                else if (e.key === 'Enter') keyName = 'enter';
                else if (e.key === ' ') keyName = 'space';
                else if (e.key === 'ArrowUp') keyName = 'up';
                else if (e.key === 'ArrowDown') keyName = 'down';
                else if (e.key === 'ArrowLeft') keyName = 'left';
                else if (e.key === 'ArrowRight') keyName = 'right';
                else if (e.key === 'Home') keyName = 'home';
                else if (e.key === 'End') keyName = 'end';
                else if (e.key === 'PageUp') keyName = 'pageup';
                else if (e.key === 'PageDown') keyName = 'pagedown';
                else if (e.key === 'Insert') keyName = 'insert';
                else if (e.key.startsWith('F') && e.key.length > 1) keyName = e.key.toLowerCase();

                if (isSpecial) {{
                    if (eventMatchesExpectedInput(e, expectedInput, expectedCode)) {{
                        e.preventDefault();
                        modalInput.className = 'modal-input success';
                        setTimeout(() => {{
                            hideKeyboardModal();
                            nextStep();
                        }}, 200);
                    }}
                    return;
                }}
                
                if (e.key === 'Enter' || (spaceSubmits && e.key === ' ')) {{
                    e.preventDefault();
                    if (normalizeTextInput(modalInput.value) === expectedText) {{
                        modalInput.className = 'modal-input success';
                        document.onkeydown = null;
                        setTimeout(() => {{
                            hideKeyboardModal();
                            nextStep();
                        }}, 300);
                    }} else {{
                        modalInput.className = 'modal-input error';
                        setTimeout(() => modalInput.className = 'modal-input', 300);
                    }}
                }}
            }};
        }}
        
        function hideKeyboardModal() {{
            document.onkeydown = null;
            keyboardModal.classList.remove('active');
        }}

        modalInput.addEventListener('input', function() {{
            modalInputGhost.style.display = modalInput.value ? 'none' : 'flex';
        }});
        
        function nextStep() {{
            renderStep(currentStep + 1);
        }}

        function showPostDragState(step, onDone) {{
            if (step.post_drag_image) {{
                stepImage.src = step.post_drag_image;
                hidePointerOverlays();
                hideGuide();
                setTimeout(onDone, 240);
                return;
            }}
            setTimeout(onDone, 200);
        }}
        
        function showCompletion() {{
            hideGuide();
            document.getElementById('completionScreen').classList.remove('hidden');
            document.getElementById('progressBar').style.width = '100%';
        }}
        
        // Hitbox click
        hitbox.addEventListener('click', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'click') return;
            if ((step.click_button || 'left') !== 'left') return;
            if (!requiredModifiersMatch(step)) return;
            e.stopPropagation();
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            setTimeout(() => nextStep(), 200);
        }});

        hitbox.addEventListener('auxclick', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'click') return;
            const required = step.click_button || 'left';
            const clicked = e.button === 1 ? 'middle' : (e.button === 2 ? 'right' : 'left');
            if (required !== clicked) return;
            if (!requiredModifiersMatch(step)) return;
            e.preventDefault();
            e.stopPropagation();
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            setTimeout(() => nextStep(), 200);
        }});
        
        // Pan & Zoom
        function setupPanZoom() {{
            canvasContainer.addEventListener('wheel', function(e) {{
                e.preventDefault();
                const delta = e.deltaY > 0 ? -0.1 : 0.1;
                scale = Math.min(Math.max(0.3, scale + delta), 3);
                updateTransform();
            }});
            
            canvasContainer.addEventListener('mousedown', function(e) {{
                const step = steps[currentStep];
                if (step && step.action_type === 'mouse_drag') {{
                    const requiredButton = step.drag_button || 'left';
                    if (mouseButtonName(e.button) !== requiredButton) return;
                    if (!requiredModifiersMatch(step)) return;
                    const point = clientToImagePoint(e.clientX, e.clientY);
                    if (pointInStepArea(step, point.x, point.y, false)) {{
                        tutorialDrag = {{
                            active: true,
                            validDistance: false,
                            startPoint: point,
                            startButton: requiredButton
                        }};
                        e.preventDefault();
                        return;
                    }}
                }}
                if (e.target === hitbox) return;
                isDragging = true;
                dragStart = {{x: e.clientX - panX, y: e.clientY - panY}};
                canvasContainer.style.cursor = 'grabbing';
            }});
            
            document.addEventListener('mousemove', function(e) {{
                if (tutorialDrag && tutorialDrag.active) {{
                    const point = clientToImagePoint(e.clientX, e.clientY);
                    const step = steps[currentStep];
                    tutorialDrag.validDistance = Math.hypot(
                        point.x - tutorialDrag.startPoint.x,
                        point.y - tutorialDrag.startPoint.y
                    ) >= (step.drag_min_distance || 30);
                    return;
                }}
                if (!isDragging) return;
                panX = e.clientX - dragStart.x;
                panY = e.clientY - dragStart.y;
                updateTransform();
            }});
            
            document.addEventListener('mouseup', function(e) {{
                const step = steps[currentStep];
                if (step && step.action_type === 'mouse_drag' && tutorialDrag && tutorialDrag.active) {{
                    const requiredButton = step.drag_button || 'left';
                    if ((tutorialDrag.startButton || requiredButton) !== requiredButton) {{
                        tutorialDrag.active = false;
                        return;
                    }}
                    if (!requiredModifiersMatch(step)) {{
                        tutorialDrag.active = false;
                        return;
                    }}
                    const point = clientToImagePoint(e.clientX, e.clientY);
                    const completed = tutorialDrag.validDistance && pointInStepArea(step, point.x, point.y, true);
                    tutorialDrag.active = false;
                    if (completed) {{
                        hitbox.style.background = 'rgba(0, 255, 0, 0.5)';
                        dragTarget.style.background = 'rgba(0, 255, 0, 0.45)';
                        showPostDragState(step, () => nextStep());
                    }}
                    return;
                }}
                isDragging = false;
                canvasContainer.style.cursor = 'grab';
            }});
            
            window.addEventListener('resize', fitToWindow);
        }}

        window.addEventListener('keydown', function(e) {{
            const modifierKey = normalizeModifierKey(e.key);
            if (modifierKey) {{
                pressedModifierKeys.add(modifierKey);
            }}
        }});

        window.addEventListener('keyup', function(e) {{
            const modifierKey = normalizeModifierKey(e.key);
            if (modifierKey) {{
                pressedModifierKeys.delete(modifierKey);
            }}
        }});

        window.addEventListener('blur', function() {{
            pressedModifierKeys.clear();
        }});
        
        function updateTransform() {{
            canvasInner.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
        }}
        
        function fitToWindow() {{
            // Get viewport dimensions
            const viewW = window.innerWidth;
            const viewH = window.innerHeight - 80; // Account for header
            
            // Get image native dimensions
            const imgW = stepImage.naturalWidth || 1920;
            const imgH = stepImage.naturalHeight || 1080;
            
            // Calculate scale to fit
            const scaleX = viewW / imgW;
            const scaleY = viewH / imgH;
            scale = Math.min(scaleX, scaleY, 1); // Don't scale above 100%
            
            // Center the image
            const scaledW = imgW * scale;
            const scaledH = imgH * scale;
            panX = (viewW - scaledW) / 2;
            panY = (viewH - scaledH) / 2 + 40; // Offset for header
            
            updateTransform();
        }}
        
        function zoomIn() {{
            scale = Math.min(scale * 1.25, 3);
            updateTransform();
        }}
        
        function zoomOut() {{
            scale = Math.max(scale / 1.25, 0.3);
            updateTransform();
        }}
        
        function resetZoom() {{
            fitToWindow();
        }}
        
        init();
    </script>
</body>
</html>'''

    
    def export_iframe_embed(self, output_path: str) -> bool:
        """Export as embeddable iframe/JavaScript widget."""
        # First export HTML
        html_path = output_path.replace('.js', '.html')
        self.export_html(html_path, embed_images=True)
        
        # Create JavaScript embed code
        js_content = f'''// TutoMake Embed Widget
// Usage: <div id="tutomake-widget"></div><script src="{os.path.basename(output_path)}"></script>
(function() {{
    var container = document.getElementById('tutomake-widget');
    if (!container) {{
        console.error('TutoMake: Container element #tutomake-widget not found');
        return;
    }}
    
    var iframe = document.createElement('iframe');
    iframe.src = '{os.path.basename(html_path)}';
    iframe.style.width = '100%';
    iframe.style.height = '600px';
    iframe.style.border = 'none';
    iframe.style.borderRadius = '10px';
    iframe.style.boxShadow = '0 10px 40px rgba(0,0,0,0.2)';
    
    container.appendChild(iframe);
}})();
'''
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        
        print(f"Exported iframe embed to: {output_path}")
        return True
    
    def export_lottie(self, output_path: str) -> bool:
        """Export as Lottie JSON animation (simplified version)."""
        # Create a simplified Lottie animation
        animation = {
            "v": "5.7.4",
            "fr": 24,
            "ip": 0,
            "op": len(self.tutorial.steps) * 48,  # 2 seconds per step
            "w": 1920,
            "h": 1080,
            "nm": self.tutorial.title,
            "ddd": 0,
            "assets": [],
            "layers": []
        }
        
        # Add a simple marker layer for each step
        for i, step in enumerate(self.tutorial.steps):
            layer = {
                "ddd": 0,
                "ind": i + 1,
                "ty": 4,  # Shape layer
                "nm": f"Step {i + 1}",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "p": {"a": 0, "k": [step.x + step.width/2, step.y + step.height/2, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "ip": i * 48,
                "op": (i + 1) * 48,
                "st": i * 48
            }
            animation["layers"].append(layer)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(animation, f, indent=2)
        
        print(f"Exported Lottie to: {output_path}")
        return True
    
    def export_video_html(self, output_path: str) -> bool:
        """Export as HTML with embedded video playback and interactive hitboxes."""
        import shutil
        
        if not self.tutorial.video_path or not os.path.exists(self.tutorial.video_path):
            print("No video file found for video HTML export")
            return False
        
        # Get output directory - use current directory if none specified
        output_dir = os.path.dirname(output_path)
        if not output_dir:
            output_dir = os.getcwd()
        
        video_basename = "tutorial_video.mp4"
        video_output = os.path.join(output_dir, video_basename)
        
        print(f"Video source: {self.tutorial.video_path}")
        print(f"Video output: {video_output}")
        
        try:
            # Try to convert with imageio-ffmpeg for H.264 compatibility
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            import subprocess
            
            print("Converting video to H.264...")
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', self.tutorial.video_path,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                video_output
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                # Fallback: just copy the file
                shutil.copy2(self.tutorial.video_path, video_output)
                print("Copied original video instead")
        except Exception as e:
            print(f"Video conversion failed, copying original: {e}")
            shutil.copy2(self.tutorial.video_path, video_output)
        
        # Prepare step data
        steps_data = []
        for i, step in enumerate(self.tutorial.steps):
            step_info = self._serialize_step(step, i)
            steps_data.append(step_info)
        
        # Copy audio file if exists
        audio_basename = ""
        if self.tutorial.audio_path and os.path.exists(self.tutorial.audio_path):
            audio_basename = "tutorial_audio" + os.path.splitext(self.tutorial.audio_path)[1]
            audio_output = os.path.join(output_dir, audio_basename)
            shutil.copy2(self.tutorial.audio_path, audio_output)
            print(f"Copied audio to: {audio_output}")
        
        html_content = self._generate_video_html(steps_data, video_basename, audio_basename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Exported Video HTML to: {output_path}")
        return True
    
    def _generate_video_html(self, steps_data: list, video_file: str, audio_file: str = "") -> str:
        """Generate HTML with video player and interactive hitbox overlay."""
        steps_json = json.dumps(steps_data)
        guide_config_json = self._guide_card_config_json()
        
        return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.tutorial.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            min-height: 100vh;
            color: white;
            overflow: hidden;
        }}
        
        .progress-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: rgba(255,255,255,0.1);
            z-index: 1000;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #9333ea);
            transition: width 0.3s ease;
        }}
        
        .header {{
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 12px 30px;
            border-radius: 30px;
            backdrop-filter: blur(10px);
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .step-badge {{
            background: linear-gradient(135deg, #ff6b6b, #ff8e53);
            width: 35px;
            height: 35px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}
        .video-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: black;
        }}
        
        .video-wrapper {{
            position: relative;
            max-width: 100%;
            max-height: 100%;
        }}
        
        video {{
            max-width: 100vw;
            max-height: 100vh;
            display: block;
        }}
        
        .hitbox {{
            position: absolute;
            border: 3px solid #ff4444;
            cursor: pointer;
            display: none;
            animation: pulse 1.5s infinite, glow 1.5s infinite;
        }}
        .hitbox:hover {{
            border-color: #ffff00;
        }}
        .hitbox.circle {{
            border-radius: 50%;
        }}
        .drag-target {{
            border-color: #22c55e;
            background: rgba(34, 197, 94, 0.25);
            pointer-events: none;
        }}
        .drag-line {{
            position: absolute;
            height: var(--drag-line-thickness, 4px);
            background: linear-gradient(90deg, #f59e0b, #38bdf8);
            transform-origin: 0 50%;
            display: none;
            pointer-events: none;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.45);
            border-radius: 999px;
            overflow: visible;
        }}
        .drag-line.no-arrow::after {{
            display: none;
        }}
        .drag-line::after {{
            content: '';
            position: absolute;
            right: -2px;
            top: 50%;
            width: 0;
            height: 0;
            transform: translateY(-50%);
            border-top: calc(var(--drag-arrow-size, 14px) * 0.57) solid transparent;
            border-bottom: calc(var(--drag-arrow-size, 14px) * 0.57) solid transparent;
            border-left: var(--drag-arrow-size, 14px) solid #38bdf8;
            filter: drop-shadow(0 0 8px rgba(56, 189, 248, 0.55));
        }}
        .modifier-badge {{
            position: absolute;
            display: none;
            padding: 7px 14px;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.9);
            color: #e2e8f0;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.02em;
            pointer-events: none;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.35);
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.03); }}
        }}
        
        @keyframes glow {{
            0%, 100% {{ 
                box-shadow: 0 0 10px rgba(255, 68, 68, 0.5), 
                            0 0 20px rgba(255, 68, 68, 0.3);
            }}
            50% {{ 
                box-shadow: 0 0 20px rgba(255, 68, 68, 0.8), 
                            0 0 40px rgba(255, 68, 68, 0.5);
            }}
        }}
        
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 500;
        }}
        .modal-overlay.active {{ display: flex; }}
        .modal-content {{
            width: auto;
            max-width: calc(100vw - 32px);
            background: transparent;
            padding: 0;
            border-radius: 0;
            box-shadow: none;
            border: none;
            pointer-events: auto;
            text-align: center;
        }}
        .modal-character {{
            display: none !important;
        }}
        .modal-content.has-character .modal-character {{ display: none !important; }}
        .modal-copy {{
            min-width: 0;
            text-align: center;
        }}
        .modal-title {{ font-size: clamp(1.55rem, 3vw, 2.45rem); font-weight: 800; line-height: 1.15; color: #ffffff; -webkit-text-stroke: 1px rgba(7, 10, 18, 0.82); text-shadow: 0 0 2px rgba(7, 10, 18, 0.95), 0 0 8px rgba(7, 10, 18, 0.88), 0 0 20px rgba(56, 189, 248, 0.34), 0 0 34px rgba(56, 189, 248, 0.22); }}
        .modal-hint {{ color: rgba(255, 255, 255, 0.68); margin-top: 14px; margin-bottom: 24px; line-height: 1.45; font-size: 1.08rem; -webkit-text-stroke: 0.6px rgba(7, 10, 18, 0.78); text-shadow: 0 0 2px rgba(7, 10, 18, 0.94), 0 0 6px rgba(7, 10, 18, 0.84), 0 0 16px rgba(56, 189, 248, 0.18); }}
        .modal-input {{
            width: min(360px, 100%);
            padding: 18px 22px;
            font-size: 1.28em;
            border: 2px solid rgba(255,255,255,0.12);
            border-radius: 18px;
            background: rgba(7, 12, 24, 0.20);
            color: white;
            text-align: center;
            position: relative;
            z-index: 2;
        }}
        .modal-input-wrap {{
            position: relative;
            width: min(360px, 100%);
            margin: 0 auto;
        }}
        .modal-input-ghost {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.45);
            pointer-events: none;
            font-size: 1.2em;
            padding: 15px;
            z-index: 3;
        }}
        .modal-input:focus {{ border-color: #00d2ff; outline: none; }}
        .modal-input.success {{ border-color: #4CAF50; }}
        .modal-input.error {{ border-color: #ff4444; animation: shake 0.3s; }}

        .guide-overlay {{
            position: fixed;
            left: 24px;
            top: 24px;
            width: min(680px, calc(100vw - 40px));
            z-index: 420;
            pointer-events: none;
            transition: opacity 0.16s ease;
        }}
        .guide-overlay.hidden {{
            opacity: 0;
            transform: none;
        }}
        .drag-guide-overlay {{
            position: fixed;
            left: 20px;
            top: 20px;
            z-index: 425;
            pointer-events: none;
            opacity: 1;
            transition: opacity 0.16s ease;
        }}
        .drag-guide-overlay.hidden {{
            opacity: 0;
        }}
        .drag-guide-media {{
            display: block;
            width: min(220px, calc(100vw - 32px));
            height: min(220px, calc(100vw - 32px));
            aspect-ratio: 1 / 1;
            object-fit: contain;
            border-radius: 16px;
            border: 1px solid rgba(120, 198, 255, 0.35);
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.34);
            background: rgba(7, 12, 24, 0.82);
        }}
        .guide-card {{
            background: rgba(6, 7, 16, 0.96);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 42px;
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.42);
            backdrop-filter: blur(18px);
            padding: 22px 28px;
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .guide-step-badge {{
            width: 96px;
            height: 96px;
            border-radius: 50%;
            background: linear-gradient(180deg, #ff8e66, #ff6f61);
            color: #ffffff;
            font-size: 2.5rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.24);
        }}
        .guide-character {{
            width: 112px;
            height: 112px;
            border-radius: 26px;
            object-fit: contain;
            object-position: center bottom;
            flex: 0 0 auto;
            display: none;
            background: rgba(255,255,255,0.04);
            padding: 8px;
        }}
        .guide-card.has-character .guide-character {{
            display: block;
        }}
        .guide-copy {{
            min-width: 0;
            flex: 1 1 auto;
        }}
        .guide-title {{
            font-size: clamp(1.85rem, 3vw, 2.4rem);
            font-weight: 700;
            line-height: 1.2;
            color: #f4f5f8;
        }}
        .guide-body {{
            margin-top: 10px;
            font-size: clamp(1.2rem, 2vw, 1.55rem);
            line-height: 1.35;
            color: rgba(255, 255, 255, 0.62);
        }}
        .guide-accent {{
            color: #ffffff;
            font-weight: 800;
        }}
        @media (max-width: 640px) {{
            .guide-overlay {{
                width: calc(100vw - 20px);
                left: 10px;
                top: 10px;
            }}
            .drag-guide-media {{
                width: min(160px, calc(100vw - 20px));
                height: min(160px, calc(100vw - 20px));
            }}
            .guide-card {{
                padding: 14px 16px;
                border-radius: 28px;
                gap: 12px;
            }}
            .guide-step-badge {{
                width: 62px;
                height: 62px;
                font-size: 1.6rem;
            }}
            .guide-character {{
                width: 72px;
                height: 72px;
                border-radius: 18px;
            }}
            .modal-content {{
                max-width: calc(100vw - 20px);
            }}
            .guide-title {{
                font-size: 1.15rem;
            }}
            .guide-body {{
                font-size: 0.95rem;
            }}
        }}
        
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            25% {{ transform: translateX(-10px); }}
            75% {{ transform: translateX(10px); }}
        }}
        
        .screen-overlay {{
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            transition: opacity 0.5s;
        }}
        .screen-overlay.hidden {{ opacity: 0; pointer-events: none; }}
        .screen-title {{
            font-size: 3em;
            margin-bottom: 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .screen-subtitle {{ font-size: 1.3em; color: #888; margin-bottom: 40px; }}
        .screen-btn {{
            padding: 20px 60px;
            font-size: 1.3em;
            border: none;
            border-radius: 50px;
            background: linear-gradient(135deg, #00d2ff, #3a7bd5);
            color: white;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .screen-btn:hover {{ transform: translateY(-3px); }}
        .completion-icon {{ font-size: 5em; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>
    
        <div class="video-container">
        <div class="video-wrapper" id="videoWrapper">
            <video id="video" src="{video_file}" preload="auto"></video>
            <div class="hitbox" id="hitbox"></div>
            <div class="hitbox drag-target" id="dragTarget"></div>
            <div class="drag-line" id="dragLine"></div>
            <div class="modifier-badge" id="modifierBadge"></div>
        </div>
    </div>
    
    <!-- Audio element for narration sync -->
    <audio id="audio" src="{audio_file}" preload="auto"></audio>

    <div class="guide-overlay hidden" id="guideOverlay">
        <div class="guide-card">
            <div class="guide-step-badge" id="stepBadge"></div>
            <div class="guide-copy">
                <div class="guide-title" id="stepDesc"></div>
                <div class="guide-body" id="stepInstruction"></div>
            </div>
            <img class="guide-character" id="guideCharacter" alt="">
        </div>
    </div>

    <div class="drag-guide-overlay hidden" id="dragGuideOverlay">
        <img class="drag-guide-media" id="dragGuideMedia" alt="">
    </div>
    
    <div class="modal-overlay" id="keyboardModal">
        <div class="modal-content">
            <div class="modal-copy">
                <div class="modal-title" id="modalTitle"></div>
                <div class="modal-hint" id="modalHint"></div>
                <div class="modal-input-wrap" id="modalInputWrap">
                    <input type="text" class="modal-input" id="modalInput" autocomplete="off">
                    <div class="modal-input-ghost" id="modalInputGhost"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="screen-overlay" id="startScreen">
        <div class="screen-title">{self.tutorial.title}</div>
        <div class="screen-subtitle">{self.tutorial.start_subtitle}</div>
        <button class="screen-btn" id="startBtn" onclick="startTutorial()">{self.tutorial.start_button_text}</button>
    </div>
    
    <div class="screen-overlay hidden" id="completionScreen">
        <div class="completion-icon">🎉</div>
        <div class="screen-title">{self.tutorial.completion_title}</div>
        <div class="screen-subtitle">{self.tutorial.completion_subtitle}</div>
        <button class="screen-btn" onclick="restartTutorial()">{self.tutorial.restart_button_text}</button>
    </div>
    
    <script>
        const steps = {steps_json};
        const guideConfig = {guide_config_json};
        let currentStep = 0;
        let isPaused = false;
        
        const video = document.getElementById('video');
        const videoWrapper = document.getElementById('videoWrapper');
        const hitbox = document.getElementById('hitbox');
        const dragTarget = document.getElementById('dragTarget');
        const dragLine = document.getElementById('dragLine');
        const modifierBadge = document.getElementById('modifierBadge');
        const keyboardModal = document.getElementById('keyboardModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalInput = document.getElementById('modalInput');
        const modalHint = document.getElementById('modalHint');
        const modalInputGhost = document.getElementById('modalInputGhost');
        const modalInputWrap = document.getElementById('modalInputWrap');
        const guideOverlay = document.getElementById('guideOverlay');
        const dragGuideOverlay = document.getElementById('dragGuideOverlay');
        const dragGuideMedia = document.getElementById('dragGuideMedia');
        const guideCharacter = document.getElementById('guideCharacter');
        const stepBadge = document.getElementById('stepBadge');
        const stepDesc = document.getElementById('stepDesc');
        const stepInstruction = document.getElementById('stepInstruction');
        const audio = document.getElementById('audio');
        const audioOffset = {self.tutorial.audio_offset};  // Audio sync offset in seconds
        let tutorialDrag = null;
        const pressedModifierKeys = new Set();
        
        function startTutorial() {{
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('startBtn').textContent = {json.dumps(self.tutorial.restart_button_text)};
            currentStep = 0;
            isPaused = false;
            video.currentTime = 0;
            safePlayMedia();
            
            // Start audio with offset
            if (audio.src) {{
                if (audioOffset >= 0) {{
                    setTimeout(() => {{
                        if (!isPaused && currentStep < steps.length) {{
                            audio.currentTime = 0;
                            const audioPlayPromise = audio.play();
                            if (audioPlayPromise && typeof audioPlayPromise.catch === 'function') {{
                                audioPlayPromise.catch(() => {{}});
                            }}
                        }}
                    }}, audioOffset * 1000);
                }} else {{
                    audio.currentTime = -audioOffset;
                    const audioPlayPromise = audio.play();
                    if (audioPlayPromise && typeof audioPlayPromise.catch === 'function') {{
                        audioPlayPromise.catch(() => {{}});
                    }}
                }}
            }}
        }}
        
        function restartTutorial() {{
            document.getElementById('completionScreen').classList.add('hidden');
            startTutorial();
        }}
        
        video.addEventListener('timeupdate', function() {{
            if (isPaused || currentStep >= steps.length) return;
            
            const step = steps[currentStep];
            if (video.currentTime >= step.timestamp) {{
                pauseAndShowHitbox(step);
            }}
        }});
        
        function pauseAndShowHitbox(step) {{
            video.pause();
            if (audio.src) audio.pause();  // Pause audio in sync
            isPaused = true;
            
            document.getElementById('progressBar').style.width = ((currentStep + 1) / steps.length * 100) + '%';
            hidePointerOverlays();
            showGuide(step);
            if (step.action_type === 'keyboard') {{
                showKeyboardModal(step);
            }} else if (step.action_type === 'mouse_drag') {{
                hideKeyboardModal();
                positionDragOverlay(step);
            }} else {{
                hideKeyboardModal();
                positionHitbox(step);
            }}
        }}

        function safePlayMedia() {{
            const videoPlayPromise = video.play();
            if (videoPlayPromise && typeof videoPlayPromise.catch === 'function') {{
                videoPlayPromise.catch(() => {{}});
            }}

            if (audio.src && audioOffset <= 0) {{
                const audioPlayPromise = audio.play();
                if (audioPlayPromise && typeof audioPlayPromise.catch === 'function') {{
                    audioPlayPromise.catch(() => {{}});
                }}
            }}
        }}
        
        function positionHitbox(step) {{
            const videoRect = video.getBoundingClientRect();
            const scaleX = videoRect.width / video.videoWidth;
            const scaleY = videoRect.height / video.videoHeight;
            
            hitbox.style.display = 'block';
            hitbox.style.left = (step.x * scaleX) + 'px';
            hitbox.style.top = (step.y * scaleY) + 'px';
            hitbox.style.width = (step.width * scaleX) + 'px';
            hitbox.style.height = (step.height * scaleY) + 'px';
            hitbox.className = 'hitbox' + (step.shape === 'circle' ? ' circle' : '');
            hitbox.style.background = 'rgba(255, 68, 68, 0.3)';
        }}

        function hidePointerOverlays() {{
            tutorialDrag = null;
            hitbox.style.display = 'none';
            dragTarget.style.display = 'none';
            dragLine.style.display = 'none';
            modifierBadge.style.display = 'none';
        }}

        function positionDragOverlay(step) {{
            const videoRect = video.getBoundingClientRect();
            const scaleX = videoRect.width / video.videoWidth;
            const scaleY = videoRect.height / video.videoHeight;

            positionHitbox(step);
            dragTarget.style.display = 'block';
            dragTarget.style.left = (step.drag_end_x * scaleX) + 'px';
            dragTarget.style.top = (step.drag_end_y * scaleY) + 'px';
            dragTarget.style.width = (step.drag_end_width * scaleX) + 'px';
            dragTarget.style.height = (step.drag_end_height * scaleY) + 'px';
            dragTarget.className = 'hitbox drag-target' + (step.shape === 'circle' ? ' circle' : '');

            const startCenter = {{
                x: (step.x + (step.width / 2)) * scaleX,
                y: (step.y + (step.height / 2)) * scaleY
            }};
            const endCenter = {{
                x: (step.drag_end_x + (step.drag_end_width / 2)) * scaleX,
                y: (step.drag_end_y + (step.drag_end_height / 2)) * scaleY
            }};
            const dx = endCenter.x - startCenter.x;
            const dy = endCenter.y - startCenter.y;
            const arrowEnabled = step.drag_direction_arrow_enabled !== false;
            const arrowSize = Math.max(10, Math.min(40, Number(step.drag_direction_arrow_size || 16)));
            const lineThickness = Math.max(3, Math.round(arrowSize * 0.25));

            dragLine.style.display = 'block';
            dragLine.style.left = startCenter.x + 'px';
            dragLine.style.top = startCenter.y + 'px';
            dragLine.style.width = Math.max(18, Math.hypot(dx, dy) - 8) + 'px';
            dragLine.style.transform = `rotate(${{Math.atan2(dy, dx)}}rad)`;
            dragLine.style.setProperty('--drag-arrow-size', `${{arrowSize}}px`);
            dragLine.style.setProperty('--drag-line-thickness', `${{lineThickness}}px`);
            dragLine.classList.toggle('no-arrow', !arrowEnabled);
            const modifierText = (step.modifier_keys || []).join(' + ').replace(/\\b\\w/g, ch => ch.toUpperCase());
            if (modifierText) {{
                modifierBadge.style.display = 'block';
                modifierBadge.textContent = modifierText;
                modifierBadge.style.left = (step.x * scaleX) + 'px';
                modifierBadge.style.top = Math.max(12, (step.y * scaleY) - 42) + 'px';
            }}
            tutorialDrag = {{
                active: false,
                validDistance: false,
                startPoint: null
            }};
        }}

        function pointInStepArea(step, x, y, useDragEnd = false) {{
            const left = useDragEnd ? step.drag_end_x : step.x;
            const top = useDragEnd ? step.drag_end_y : step.y;
            const width = useDragEnd ? step.drag_end_width : step.width;
            const height = useDragEnd ? step.drag_end_height : step.height;

            if (step.shape === 'circle') {{
                const rx = width / 2;
                const ry = height / 2;
                if (rx <= 0 || ry <= 0) return false;
                const cx = left + rx;
                const cy = top + ry;
                const dx = (x - cx) / rx;
                const dy = (y - cy) / ry;
                return (dx * dx) + (dy * dy) <= 1;
            }}

            return x >= left && x <= left + width && y >= top && y <= top + height;
        }}

        function clientToVideoPoint(clientX, clientY) {{
            const videoRect = video.getBoundingClientRect();
            const scaleX = videoRect.width / video.videoWidth;
            const scaleY = videoRect.height / video.videoHeight;
            return {{
                x: (clientX - videoRect.left) / scaleX,
                y: (clientY - videoRect.top) / scaleY
            }};
        }}

        function mouseButtonName(button) {{
            if (button === 1) return 'middle';
            if (button === 2) return 'right';
            return 'left';
        }}

        function normalizeModifierKey(key) {{
            const value = (key || '').toLowerCase();
            if (value === 'control') return 'ctrl';
            if (value === 'shift') return 'shift';
            if (value === 'alt') return 'alt';
            if (value === 'meta' || value === 'os') return 'cmd';
            if (value === ' ' || value === 'spacebar' || value === 'space') return 'space';
            return '';
        }}

        function eventKeyName(e) {{
            if ((e.code || '') === 'Space') return 'space';
            const rawKey = e.key === 'Spacebar' ? 'space' : e.key;
            return normalizeKeyName(rawKey);
        }}

        function requiredModifiersMatch(step) {{
            const required = step.modifier_keys || [];
            return required.every(key => pressedModifierKeys.has(key));
        }}

        function normalizeKeyName(value) {{
            const input = (value || '').toLowerCase().trim();
            if (input.length === 1) {{
                const code = input.charCodeAt(0);
                if (code >= 1 && code <= 26) {{
                    return String.fromCharCode(96 + code);
                }}
            }}
            if (input.startsWith('key.')) return normalizeKeyName(input.substring(4));
            const aliases = {{
                'escape': 'esc',
                'return': 'enter',
                'del': 'delete',
                'arrowup': 'up',
                'arrowdown': 'down',
                'arrowleft': 'left',
                'arrowright': 'right',
                'page_up': 'pageup',
                'page_down': 'pagedown',
                'control': 'ctrl',
                'meta': 'cmd',
                ' ': 'space',
                'spacebar': 'space'
            }};
            return aliases[input] || input;
        }}

        function normalizeKeyCombo(value) {{
            const parts = (value || '').split('+').map(part => normalizeKeyName(part)).filter(Boolean);
            const modifierOrder = ['ctrl', 'shift', 'alt', 'cmd', 'space'];
            const modifiers = [];
            let mainKey = '';

            for (const part of parts) {{
                if (modifierOrder.includes(part)) {{
                    if (!modifiers.includes(part)) modifiers.push(part);
                }} else if (!mainKey) {{
                    mainKey = part;
                }}
            }}

            modifiers.sort((a, b) => modifierOrder.indexOf(a) - modifierOrder.indexOf(b));
            if (mainKey) modifiers.push(mainKey);
            return modifiers.join('+');
        }}

        function formatKeyPart(value) {{
            const normalized = normalizeKeyName(value);
            if (/^f\\d+$/.test(normalized)) return normalized.toUpperCase();
            if (/^[a-z]$/.test(normalized)) return normalized.toUpperCase();
            return normalized.replace(/\\b\\w/g, ch => ch.toUpperCase());
        }}

        function formatKeyCombo(value) {{
            const normalized = normalizeKeyCombo(value);
            if (!normalized) return '';
            return normalized.split('+').map(formatKeyPart).join(' + ');
        }}

        function formatMouseButton(value) {{
            const button = (value || 'left').toLowerCase();
            if (button === 'right') return 'Right click';
            if (button === 'middle') return 'Middle click';
            return 'Left click';
        }}

        function escapeHtml(value) {{
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function getStepGuide(step) {{
            const strings = guideStrings();
            const customInstruction = (step.instruction || '').trim();
            const customTitle = (step.description || '').trim();
            if (step.action_type === 'keyboard') {{
                const expectedInput = normalizeKeyCombo(step.keyboard_input);
                const comboParts = expectedInput.split('+').filter(Boolean);
                const comboMainKey = comboParts.length ? comboParts[comboParts.length - 1] : '';
                const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter',
                    'space', 'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                    'insert', 'ctrl', 'alt', 'shift', 'cmd', 'capslock', 'numlock',
                    'scrolllock', 'pause', 'printscreen'];
                const isFkey = comboMainKey.startsWith('f') && comboMainKey.length >= 2 && !isNaN(comboMainKey.substring(1));
                const inferredSpecial = comboParts.length > 1 || specialKeys.includes(comboMainKey) || isFkey;
                const usesLegacyInference = !step.keyboard_mode;
                const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);
                if (isSpecial) {{
                    const comboLabel = formatKeyCombo(expectedInput || step.keyboard_input);
                    return {{
                        eyebrow: strings.keyboardStep,
                        title: customTitle ? escapeHtml(customTitle) : `${{strings.press}} <span class="guide-accent">${{escapeHtml(comboLabel)}}</span>`,
                        body: customInstruction ? escapeHtml(customInstruction) : strings.pressComboBody
                    }};
                }}
                const typeBody = (step.keyboard_space_behavior || 'submit_step') === 'submit_step'
                    ? strings.typeBodySubmit
                    : strings.typeBody;
                return {{
                    eyebrow: strings.typingStep,
                    title: customTitle ? escapeHtml(customTitle) : `${{strings.type}} <span class="guide-accent">${{escapeHtml(step.keyboard_input || '')}}</span>`,
                    body: customInstruction ? escapeHtml(customInstruction) : typeBody
                }};
            }}

            if (step.action_type === 'mouse_drag') {{
                const modifierText = (step.modifier_keys || []).map(formatKeyPart).join(' + ');
                const actionText = formatMouseButton(step.drag_button).replace(' click', '');
                const translatedAction = translateMouseButton(step.drag_button);
                const fallbackTitle = strings.dragWith
                    ? `${{strings.dragWith}} <span class="guide-accent">${{escapeHtml(translatedAction || actionText)}}</span> ${{strings.fromRedToBlue}}`
                    : `<span class="guide-accent">${{escapeHtml(translatedAction || actionText)}}</span> ${{strings.fromRedToBlue}}`;
                return {{
                    eyebrow: strings.dragStep,
                    title: customTitle ? escapeHtml(customTitle) : fallbackTitle,
                    body: customInstruction ? escapeHtml(customInstruction) : ''
                }};
            }}

            const modifierText = (step.modifier_keys || []).map(formatKeyPart).join(' + ');
            const fallbackClickTitle = `${{translateMouseButton(step.click_button)}} ${{strings.highlightedArea}}`;
            return {{
                eyebrow: strings.clickStep,
                title: customTitle ? escapeHtml(customTitle) : fallbackClickTitle,
                body: customInstruction ? escapeHtml(customInstruction) : ''
            }};
        }}
        function guideStrings() {{
            const language = (guideConfig.language || 'ko').toLowerCase();
            if (language === 'en') {{
                return {{
                    keyboardStep: 'Keyboard Step',
                    typingStep: 'Typing Step',
                    dragStep: 'Drag Step',
                    clickStep: 'Click Step',
                    press: 'Press',
                    type: 'Type',
                    leftClick: 'Left click',
                    rightClick: 'Right click',
                    middleClick: 'Middle click',
                    highlightedArea: 'the highlighted area',
                    dragWith: 'Drag with',
                    fromRedToBlue: 'from the red area to the blue target',
                    pressComboBody: 'Press the highlighted key combination to continue.',
                    typeBody: 'Type the requested text, then press Enter to submit.',
                    typeBodySubmit: 'Type the requested text, then press Enter or Space to submit.',
                    dragBody: 'Start inside the red area and finish inside the blue target.',
                    clickBody: 'Click the highlighted area to continue.',
                    holdPrefix: 'Hold',
                    holdWhileDragging: 'while dragging.',
                    holdWhileClicking: 'while clicking.',
                }};
            }}
            return {{
                keyboardStep: '키보드 단계',
                typingStep: '텍스트 입력 단계',
                dragStep: '드래그 단계',
                clickStep: '클릭 단계',
                press: '누르기',
                type: '입력하기',
                leftClick: '왼쪽 클릭',
                rightClick: '오른쪽 클릭',
                middleClick: '가운데 클릭',
                highlightedArea: '강조된 영역',
                dragWith: '',
                fromRedToBlue: '빨간 영역에서 파란 대상까지 이동하세요',
                pressComboBody: '표시된 키 또는 조합 키를 눌러 다음 단계로 진행하세요.',
                typeBody: '요청된 텍스트를 입력한 뒤 Enter를 눌러 제출하세요.',
                typeBodySubmit: '요청된 텍스트를 입력한 뒤 Enter 또는 Space를 눌러 제출하세요.',
                dragBody: '빨간 영역에서 시작해서 파란 대상 안에서 드래그를 마치세요.',
                clickBody: '강조된 영역을 클릭해 다음 단계로 진행하세요.',
                holdPrefix: '',
                holdWhileDragging: ' 키를 누른 상태로 드래그하세요.',
                holdWhileClicking: ' 키를 누른 상태로 클릭하세요.',
            }};
        }}

        function translateMouseButton(value) {{
            const strings = guideStrings();
            const button = (value || 'left').toLowerCase();
            if (button === 'right') return strings.rightClick;
            if (button === 'middle') return strings.middleClick;
            return strings.leftClick;
        }}

        function resolveGuideCharacter(step) {{
            return step.guide_image || guideConfig.characterImage || '';
        }}

        function stepUsesDragGuideGif(step) {{
            return step.action_type === 'mouse_drag' && /^data:image\\/gif;base64,/i.test(step.guide_image || '');
        }}

        function clampToViewport(value, size, minValue, maxValue) {{
            return Math.min(Math.max(minValue, value), Math.max(minValue, maxValue - size));
        }}

        function candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin) {{
            const clampedLeft = clampToViewport(candidate.left, overlayWidth, margin, window.innerWidth - margin);
            const clampedTop = clampToViewport(candidate.top, overlayHeight, margin, window.innerHeight - margin);
            const overlapWidth = Math.max(0, Math.min(clampedLeft + overlayWidth, actionRight + margin) - Math.max(clampedLeft, actionLeft - margin));
            const overlapHeight = Math.max(0, Math.min(clampedTop + overlayHeight, actionBottom + margin) - Math.max(clampedTop, actionTop - margin));
            const visibleWidth = Math.max(0, Math.min(window.innerWidth - margin, clampedLeft + overlayWidth) - Math.max(margin, clampedLeft));
            const visibleHeight = Math.max(0, Math.min(window.innerHeight - margin, clampedTop + overlayHeight) - Math.max(margin, clampedTop));
            return {{
                left: clampedLeft,
                top: clampedTop,
                overlapArea: overlapWidth * overlapHeight,
                visibleArea: visibleWidth * visibleHeight,
                score: candidate.score || 0,
            }};
        }}

        function positionDragGuideNearAction(step) {{
            const margin = 12;
            const overlayWidth = dragGuideOverlay.offsetWidth || 220;
            const overlayHeight = dragGuideOverlay.offsetHeight || 160;
            const videoRect = video.getBoundingClientRect();
            const scaleX = video.videoWidth ? (videoRect.width / video.videoWidth) : 1;
            const scaleY = video.videoHeight ? (videoRect.height / video.videoHeight) : 1;
            const offset = Math.max(28, Number(guideConfig.cardOffset || 16));
            const actionLeft = videoRect.left + (Math.min(step.x, step.drag_end_x) * scaleX);
            const actionTop = videoRect.top + (Math.min(step.y, step.drag_end_y) * scaleY);
            const actionRight = videoRect.left + (Math.max(step.x + step.width, step.drag_end_x + step.drag_end_width) * scaleX);
            const actionBottom = videoRect.top + (Math.max(step.y + step.height, step.drag_end_y + step.drag_end_height) * scaleY);
            const actionCenterX = (actionLeft + actionRight) / 2;
            const actionCenterY = (actionTop + actionBottom) / 2;
            const dragDx = (step.drag_end_x + (step.drag_end_width / 2)) - (step.x + (step.width / 2));
            const dragDy = (step.drag_end_y + (step.drag_end_height / 2)) - (step.y + (step.height / 2));

            const sideCandidates = [
                {{
                    left: actionRight + offset,
                    top: actionCenterY - (overlayHeight / 2),
                    score: window.innerWidth - actionRight,
                }},
                {{
                    left: actionLeft - overlayWidth - offset,
                    top: actionCenterY - (overlayHeight / 2),
                    score: actionLeft,
                }},
            ];
            const verticalCandidates = [
                {{
                    left: actionCenterX - (overlayWidth / 2),
                    top: actionBottom + offset,
                    score: window.innerHeight - actionBottom,
                }},
                {{
                    left: actionCenterX - (overlayWidth / 2),
                    top: actionTop - overlayHeight - offset,
                    score: actionTop,
                }},
            ];
            const candidates = Math.abs(dragDx) >= Math.abs(dragDy) ? [...verticalCandidates, ...sideCandidates] : [...sideCandidates, ...verticalCandidates];

            const rankedCandidates = candidates
                .map((candidate) => candidateOverlapArea(candidate, overlayWidth, overlayHeight, actionLeft, actionTop, actionRight, actionBottom, margin))
                .sort((a, b) => {{
                    if (a.overlapArea !== b.overlapArea) return a.overlapArea - b.overlapArea;
                    if (a.visibleArea !== b.visibleArea) return b.visibleArea - a.visibleArea;
                    return b.score - a.score;
                }});

            const bestCandidate = rankedCandidates[0] || {{ left: margin, top: margin }};
            const left = bestCandidate.left;
            const top = bestCandidate.top;

            dragGuideOverlay.style.left = `${{left}}px`;
            dragGuideOverlay.style.top = `${{top}}px`;
        }}

        function positionGuideNearAction(step) {{
            const margin = 12;
            const anchorMode = (guideConfig.cardAnchor || 'top_fixed').toLowerCase();
            const horizontalOffset = Number(guideConfig.cardLeft || 0);
            const verticalOffset = Number(guideConfig.cardTop || 0);
            const cardScale = Math.min(200, Math.max(50, Number(guideConfig.cardScale || 100))) / 100;
            const fixedWidth = Math.max(280, Number(guideConfig.cardWidth || 680));
            const availableWidth = Math.max(220, window.innerWidth - 40);
            const baseWidth = Math.max(220, Math.min(fixedWidth, Math.round(availableWidth / Math.max(cardScale, 0.01))));
            guideOverlay.style.width = `${{baseWidth}}px`;
            guideOverlay.style.transformOrigin = 'top left';
            guideOverlay.style.transform = `scale(${{cardScale}})`;
            const overlayWidth = baseWidth * cardScale;
            const overlayHeight = (guideOverlay.offsetHeight || 140) * cardScale;
            if (anchorMode === 'top_fixed') {{
                const centeredLeft = Math.round((window.innerWidth - overlayWidth) / 2);
                const baseTop = 24;
                guideOverlay.style.left = `${{Math.max(margin, Math.min(centeredLeft + horizontalOffset, window.innerWidth - overlayWidth - margin))}}px`;
                guideOverlay.style.top = `${{Math.max(margin, Math.min(baseTop + verticalOffset, window.innerHeight - overlayHeight - margin))}}px`;
                guideOverlay.style.bottom = 'auto';
                return;
            }}
            const videoRect = video.getBoundingClientRect();
            const scaleX = video.videoWidth ? (videoRect.width / video.videoWidth) : 1;
            const scaleY = video.videoHeight ? (videoRect.height / video.videoHeight) : 1;

            let anchorX = videoRect.left + ((step.x + (step.width / 2)) * scaleX);
            let anchorY = videoRect.top + ((step.y + (step.height / 2)) * scaleY);

            if (step.action_type === 'mouse_drag') {{
                anchorX = videoRect.left + ((step.drag_end_x + (step.drag_end_width / 2)) * scaleX);
                anchorY = videoRect.top + ((step.drag_end_y + (step.drag_end_height / 2)) * scaleY);
            }}

            const preferredDirection = (guideConfig.cardDirection || 'auto').toLowerCase();
            const offset = Math.max(28, Number(guideConfig.cardOffset || 16));
            let left = anchorX + offset;
            let top = anchorY - (overlayHeight / 2);

            if (preferredDirection === 'left') {{
                left = anchorX - overlayWidth - offset;
            }} else if (preferredDirection === 'top') {{
                left = anchorX - (overlayWidth / 2);
                top = anchorY - overlayHeight - offset;
            }} else if (preferredDirection === 'bottom') {{
                left = anchorX - (overlayWidth / 2);
                top = anchorY + offset;
            }} else if (preferredDirection === 'right') {{
                left = anchorX + offset;
            }} else if (left + overlayWidth > window.innerWidth - margin) {{
                left = anchorX - overlayWidth - offset;
            }}
            if (left < margin) left = margin;
            if (top < margin) top = margin;
            if (top + overlayHeight > window.innerHeight - margin) {{
                top = Math.max(margin, window.innerHeight - overlayHeight - margin);
            }}

            guideOverlay.style.left = `${{left}}px`;
            guideOverlay.style.top = `${{top}}px`;
            guideOverlay.style.bottom = 'auto';
        }}

        function showGuide(step) {{
            if (stepUsesDragGuideGif(step)) {{
                const gifWidth = Math.max(140, Math.min(520, Number(step.drag_gif_preview_size || 260)));
                dragGuideMedia.src = step.guide_image;
                dragGuideMedia.alt = guideConfig.language === 'en' ? 'Drag guide animation' : '드래그 가이드 애니메이션';
                dragGuideMedia.style.width = `${{gifWidth}}px`;
                dragGuideMedia.style.height = `${{gifWidth}}px`;
                positionDragGuideNearAction(step);
                dragGuideOverlay.classList.remove('hidden');
            }} else {{
                dragGuideMedia.removeAttribute('src');
                dragGuideMedia.alt = '';
                dragGuideOverlay.classList.add('hidden');
            }}
            const guide = getStepGuide(step);
            const guideCard = guideOverlay.querySelector('.guide-card');
            const characterSize = Math.max(48, Number(guideConfig.characterSize || 112));
            const cardGap = Math.max(0, Number(guideConfig.cardGap || 18));
            const cardPadding = Math.max(10, Number(guideConfig.cardPadding || 22));
            const cardOpacity = Math.min(100, Math.max(0, Number(guideConfig.cardOpacity ?? 94))) / 100;
            const cardBlur = 18 * cardOpacity;
            const outlineAlpha = 0.16;
            const badgeSize = Math.max(52, Number(guideConfig.badgeSize || 96));
            guideCard.style.gap = `${{cardGap}}px`;
            guideCard.style.padding = `${{Math.max(14, Math.round(cardPadding))}}px ${{Math.max(18, Math.round(cardPadding * 1.25))}}px`;
            guideCard.style.background = `rgba(6, 7, 16, ${{(cardOpacity * 0.98).toFixed(3)}})`;
            guideCard.style.borderColor = `rgba(255, 255, 255, ${{outlineAlpha.toFixed(3)}})`;
            guideCard.style.boxShadow = `0 18px 48px rgba(0, 0, 0, ${{(cardOpacity * 0.5).toFixed(3)}})`;
            guideCard.style.backdropFilter = cardBlur > 0 ? `blur(${{cardBlur.toFixed(2)}}px)` : 'none';
            guideCard.style.webkitBackdropFilter = cardBlur > 0 ? `blur(${{cardBlur.toFixed(2)}}px)` : 'none';
            guideCard.style.transform = 'none';
            guideCharacter.style.width = `${{characterSize}}px`;
            guideCharacter.style.height = `${{characterSize}}px`;
            stepBadge.style.width = `${{badgeSize}}px`;
            stepBadge.style.height = `${{badgeSize}}px`;
            stepBadge.style.fontSize = `${{Math.max(22, Math.round(badgeSize * 0.42))}}px`;
            stepBadge.textContent = String(step.index || '');
            stepDesc.innerHTML = guide.title;
            stepInstruction.innerHTML = guide.body;
            stepInstruction.style.display = guide.body ? 'block' : 'none';
            const characterImage = resolveGuideCharacter(step);
            if (characterImage) {{
                guideCharacter.src = characterImage;
                guideCharacter.alt = guideConfig.language === 'en' ? 'Guide character' : '가이드 캐릭터';
                guideCard.classList.add('has-character');
            }} else {{
                guideCharacter.removeAttribute('src');
                guideCharacter.alt = '';
                guideCard.classList.remove('has-character');
            }}
            positionGuideNearAction(step);
            guideOverlay.classList.remove('hidden');
        }}

        function hideGuide() {{
            guideOverlay.classList.add('hidden');
            dragGuideOverlay.classList.add('hidden');
            dragGuideMedia.removeAttribute('src');
            dragGuideMedia.alt = '';
        }}

        function normalizeKeyCode(value) {{
            return (value || '').trim();
        }}

        function eventKeyCode(e) {{
            return normalizeKeyCode(e.code);
        }}

        function normalizeTextInput(value) {{
            return (value || '')
                .trim()
                .toLowerCase()
                .replace(/\\s*,\\s*/g, ',')
                .replace(/\\s+/g, ' ');
        }}

        function eventMatchesExpectedInput(e, expectedInput, expectedCode) {{
            const normalizedExpected = normalizeKeyCombo(expectedInput);
            const normalizedCode = normalizeKeyCode(expectedCode);
            if (!normalizedExpected.includes('+')) {{
                if (normalizedCode) return eventKeyCode(e) === normalizedCode;
                return eventKeyName(e) === normalizedExpected;
            }}

            const parts = normalizedExpected.split('+');
            const expectedMain = parts[parts.length - 1];
            const requiredModifiers = new Set(parts.slice(0, -1));
            const actualMainName = eventKeyName(e);
            const activeModifiers = new Set([
                e.ctrlKey ? 'ctrl' : '',
                e.shiftKey ? 'shift' : '',
                e.altKey ? 'alt' : '',
                e.metaKey ? 'cmd' : '',
                actualMainName === 'space' ? 'space' : ''
            ].filter(Boolean));

            if (activeModifiers.has(actualMainName)) {{
                activeModifiers.delete(actualMainName);
            }}

            const mainMatches = normalizedCode
                ? eventKeyCode(e) === normalizedCode
                : actualMainName === expectedMain;

            return mainMatches &&
                requiredModifiers.size === activeModifiers.size &&
                Array.from(requiredModifiers).every(key => activeModifiers.has(key));
        }}
        
        hitbox.addEventListener('click', function() {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'click') return;
            if ((step.click_button || 'left') !== 'left') return;
            if (!requiredModifiersMatch(step)) return;
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            nextStep();
        }});

        hitbox.addEventListener('auxclick', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'click') return;
            const required = step.click_button || 'left';
            const clicked = e.button === 1 ? 'middle' : (e.button === 2 ? 'right' : 'left');
            if (required !== clicked) return;
            if (!requiredModifiersMatch(step)) return;
            e.preventDefault();
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            nextStep();
        }});

        hitbox.addEventListener('contextmenu', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'click') return;
            if ((step.click_button || 'left') !== 'right') return;
            if (!requiredModifiersMatch(step)) return;
            e.preventDefault();
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            nextStep();
        }});
        
        function nextStep() {{
            hidePointerOverlays();
            hideGuide();
            currentStep++;
            isPaused = false;
            
            if (currentStep >= steps.length) {{
                if (audio.src) audio.pause();  // Stop audio on completion
                showCompletion();
            }} else {{
                safePlayMedia();
            }}
        }}

        function showPostDragState(step, onDone) {{
            const targetTime = Math.max(
                Number(step.drag_end_timestamp || step.timestamp || 0),
                Number(step.timestamp || 0)
            );
            const resume = () => setTimeout(onDone, 240);
            if (video.readyState >= 2) {{
                video.currentTime = targetTime;
                resume();
                return;
            }}
            const handleSeek = () => {{
                video.removeEventListener('seeked', handleSeek);
                resume();
            }};
            video.addEventListener('seeked', handleSeek);
            video.currentTime = targetTime;
        }}
        
        function showKeyboardModal(step) {{
            keyboardModal.classList.add('active');
            keyboardModal.tabIndex = -1;
            keyboardModal.focus();
            document.onkeydown = null;
            let expectedInput = normalizeKeyCombo(step.keyboard_input);
            const expectedCode = normalizeKeyCode(step.keyboard_code);
            const expectedText = normalizeTextInput(step.keyboard_input);
            const spaceSubmits = (step.keyboard_space_behavior || 'submit_step') === 'submit_step';
            
            const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter',
                               'space', 'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                               'insert', 'ctrl', 'alt', 'shift', 'cmd', 'capslock', 'numlock',
                               'scrolllock', 'pause', 'printscreen'];
            const comboParts = expectedInput.split('+').filter(Boolean);
            const comboMainKey = comboParts.length ? comboParts[comboParts.length - 1] : '';
            const isFkey = comboMainKey.startsWith('f') && comboMainKey.length >= 2 && !isNaN(comboMainKey.substring(1));
            const inferredSpecial = comboParts.length > 1 || specialKeys.includes(comboMainKey) || isFkey;
            const usesLegacyInference = !step.keyboard_mode;
            const isSpecial = (step.keyboard_mode || '') === 'key' || (usesLegacyInference && inferredSpecial);
            const customInstruction = (step.instruction || '').trim();
            const defaultSpecialInstruction = isSpecial
                ? (guideConfig.language === 'en'
                    ? `Press ${{formatKeyCombo(expectedInput)}} to continue.`
                    : `${{formatKeyCombo(expectedInput)}} 키를 눌러 다음 단계로 진행하세요.`)
                : '';
            const titleMessage = isSpecial
                ? ((step.description || '').trim() || `Press ${{formatKeyCombo(expectedInput)}}`)
                : '';
            const hintMessage = isSpecial
                ? (customInstruction || defaultSpecialInstruction)
                : '';
            modalTitle.textContent = titleMessage;
            modalTitle.style.display = titleMessage ? 'block' : 'none';
            modalHint.textContent = hintMessage;
            modalHint.style.display = hintMessage ? 'block' : 'none';
            
            if (isSpecial) {{
                modalInput.style.display = 'none';
                modalInputWrap.style.display = 'none';
                modalInputGhost.textContent = '';
                modalInputGhost.style.display = 'none';
            }} else {{
                modalInput.style.display = 'block';
                modalInputWrap.style.display = 'block';
                modalInputGhost.textContent = step.keyboard_input || '';
                modalInputGhost.style.display = 'flex';
                modalInput.focus();
            }}
            
            modalInput.value = '';
            modalInput.className = 'modal-input';
            
            document.onkeydown = function(e) {{
                if (isSpecial && eventMatchesExpectedInput(e, expectedInput, expectedCode)) {{
                    e.preventDefault();
                    modalInput.className = 'modal-input success';
                    document.onkeydown = null;
                    hideKeyboardModal();
                    nextStep();
                    return false;
                }}
                let keyName = e.key.toLowerCase();
                if (e.key === 'Delete') keyName = 'delete';
                else if (e.key === 'Backspace') keyName = 'backspace';
                else if (e.key === 'Tab') keyName = 'tab';
                else if (e.key === 'Escape') keyName = 'esc';
                else if (e.key === 'Enter') keyName = 'enter';
                else if (e.key === ' ') keyName = 'space';
                else if (e.key === 'ArrowUp') keyName = 'up';
                else if (e.key === 'ArrowDown') keyName = 'down';
                else if (e.key === 'ArrowLeft') keyName = 'left';
                else if (e.key === 'ArrowRight') keyName = 'right';
                else if (e.key === 'Home') keyName = 'home';
                else if (e.key === 'End') keyName = 'end';
                else if (e.key === 'PageUp') keyName = 'pageup';
                else if (e.key === 'PageDown') keyName = 'pagedown';
                else if (e.key === 'Insert') keyName = 'insert';
                else if (e.key.startsWith('F') && e.key.length > 1) keyName = e.key.toLowerCase();
                
                if (isSpecial && eventMatchesExpectedInput(e, expectedInput, expectedCode)) {{
                    e.preventDefault();
                    modalInput.className = 'modal-input success';
                    document.onkeydown = null;
                    hideKeyboardModal();
                    nextStep();
                    return false;
                }}
                
                if (!isSpecial && (keyName === 'enter' || (spaceSubmits && keyName === 'space'))) {{
                    e.preventDefault();
                    if (normalizeTextInput(modalInput.value) === expectedText) {{
                        modalInput.className = 'modal-input success';
                        document.onkeydown = null;
                        hideKeyboardModal();
                        nextStep();
                    }} else {{
                        modalInput.className = 'modal-input error';
                        setTimeout(function() {{ modalInput.className = 'modal-input'; }}, 300);
                    }}
                }}
            }};
        }}
        
        function hideKeyboardModal() {{
            document.onkeydown = null;
            keyboardModal.classList.remove('active');
        }}

        videoWrapper.addEventListener('mousedown', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'mouse_drag') return;
            const requiredButton = step.drag_button || 'left';
            if (mouseButtonName(e.button) !== requiredButton) return;
            if (!requiredModifiersMatch(step)) return;
            const point = clientToVideoPoint(e.clientX, e.clientY);
            if (!pointInStepArea(step, point.x, point.y, false)) return;
            tutorialDrag = {{
                active: true,
                validDistance: false,
                startPoint: point,
                startButton: requiredButton
            }};
            e.preventDefault();
        }});

        window.addEventListener('mousemove', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'mouse_drag' || !tutorialDrag || !tutorialDrag.active) return;
            const point = clientToVideoPoint(e.clientX, e.clientY);
            tutorialDrag.validDistance = Math.hypot(
                point.x - tutorialDrag.startPoint.x,
                point.y - tutorialDrag.startPoint.y
            ) >= (step.drag_min_distance || 30);
        }});

        window.addEventListener('mouseup', function(e) {{
            const step = steps[currentStep];
            if (!step || step.action_type !== 'mouse_drag' || !tutorialDrag || !tutorialDrag.active) return;
            const requiredButton = step.drag_button || 'left';
            if ((tutorialDrag.startButton || requiredButton) !== requiredButton) {{
                tutorialDrag.active = false;
                return;
            }}
            if (!requiredModifiersMatch(step)) {{
                tutorialDrag.active = false;
                return;
            }}
            const point = clientToVideoPoint(e.clientX, e.clientY);
            const completed = tutorialDrag.validDistance && pointInStepArea(step, point.x, point.y, true);
            tutorialDrag.active = false;
            if (completed) {{
                hitbox.style.background = 'rgba(0, 255, 0, 0.5)';
                dragTarget.style.background = 'rgba(0, 255, 0, 0.45)';
                showPostDragState(step, () => nextStep());
            }}
        }});

        window.addEventListener('keydown', function(e) {{
            const modifierKey = normalizeModifierKey(e.key);
            if (modifierKey) {{
                pressedModifierKeys.add(modifierKey);
            }}
        }});

        window.addEventListener('keyup', function(e) {{
            const modifierKey = normalizeModifierKey(e.key);
            if (modifierKey) {{
                pressedModifierKeys.delete(modifierKey);
            }}
        }});

        window.addEventListener('blur', function() {{
            pressedModifierKeys.clear();
        }});

        modalInput.addEventListener('input', function() {{
            modalInputGhost.style.display = modalInput.value ? 'none' : 'flex';
        }});
        
        function showCompletion() {{
            hideGuide();
            document.getElementById('completionScreen').classList.remove('hidden');
            document.getElementById('progressBar').style.width = '100%';
        }}
        
        video.addEventListener('ended', function() {{
            if (currentStep >= steps.length) {{
                showCompletion();
            }}
        }});
    </script>
</body>
</html>'''
