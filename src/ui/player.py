from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QMessageBox, QLineEdit, QPushButton, QScrollArea
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QImage, QWheelEvent
from PySide6.QtCore import Qt, QRect, QTimer, QPoint, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import winsound
import os
import cv2
import numpy as np
from ..key_utils import display_key_name, is_special_key_name, normalize_key_name
from ..model import Tutorial


class SpecialKeyLineEdit(QLineEdit):
    """QLineEdit that forwards special key events to parent Player."""
    
    SPECIAL_KEYS = {
        Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_Tab, Qt.Key.Key_Escape,
        Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Up, Qt.Key.Key_Down,
        Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End,
        Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Insert,
        Qt.Key.Key_F1, Qt.Key.Key_F2, Qt.Key.Key_F3, Qt.Key.Key_F4,
        Qt.Key.Key_F5, Qt.Key.Key_F6, Qt.Key.Key_F7, Qt.Key.Key_F8,
        Qt.Key.Key_F9, Qt.Key.Key_F10, Qt.Key.Key_F11, Qt.Key.Key_F12,
    }
    
    def keyPressEvent(self, event):
        print(f"SpecialKeyLineEdit.keyPressEvent: key={event.key()}")
        
        # Forward special keys to parent Player
        if event.key() in self.SPECIAL_KEYS:
            print(f"  Special key detected, forwarding to Player")
            # Find Player parent by class name
            parent = self.parent()
            while parent:
                if parent.__class__.__name__ == 'Player':
                    print(f"  Found Player, calling keyPressEvent")
                    parent.keyPressEvent(event)
                    return
                parent = parent.parent()
            print(f"  Player not found!")
        super().keyPressEvent(event)



class ZoomableVideoWidget(QWidget):
    """Video widget with zoom/pan support."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = parent
        
        # Zoom state
        self.scale = 1.0
        self.base_scale = 1.0  # Scale to fit window (treated as 100%)
        self.min_scale = 0.25
        self.max_scale = 4.0
        
        # Pan state
        self.pan_offset = QPoint(0, 0)
        self.is_panning = False
        self.pan_start = QPoint(0, 0)
        
        # Image state
        self.current_pixmap = None
        self.native_size = (1920, 1080)  # Original image size
        
        # Overlay state
        self.current_step = None
        self.waiting_for_click = False
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background-color: black;")
    
    def set_overlay_state(self, step, waiting):
        self.current_step = step
        self.waiting_for_click = waiting
        self.update()
    
    def setPixmap(self, pixmap: QPixmap):
        self.current_pixmap = pixmap
        if pixmap:
            self.native_size = (pixmap.width(), pixmap.height())
        self.update()
    
    def fit_to_window(self):
        """Calculate scale to fit image in window."""
        if not self.current_pixmap:
            return
        
        img_w, img_h = self.native_size
        win_w, win_h = self.width(), self.height()
        
        scale_x = win_w / img_w
        scale_y = win_h / img_h
        self.base_scale = min(scale_x, scale_y)
        self.scale = self.base_scale
        self.pan_offset = QPoint(0, 0)
        self._update_zoom_label()
        self.update()
    
    def zoom_in(self):
        self.scale = min(self.scale * 1.25, self.max_scale)
        self._update_zoom_label()
        self.update()
    
    def zoom_out(self):
        self.scale = max(self.scale / 1.25, self.min_scale)
        self._update_zoom_label()
        self.update()
    
    def _update_zoom_label(self):
        """Notify zoom control to update label."""
        if hasattr(self, 'zoom_control') and self.zoom_control:
            self.zoom_control.update_zoom_label()
    
    def reset_zoom(self):
        """Reset to 100% (base_scale)."""
        self.scale = self.base_scale
        self.pan_offset = QPoint(0, 0)
        self._update_zoom_label()
        self.update()
    
    def set_actual_size(self):
        """Set to actual 1:1 pixel size."""
        self.scale = 1.0
        self.pan_offset = QPoint(0, 0)
        self.update()
    
    def get_zoom_percent(self) -> int:
        """Get current zoom as percentage of base_scale."""
        if self.base_scale == 0:
            return 100
        return int((self.scale / self.base_scale) * 100)
    
    def screen_to_image(self, pos: QPoint) -> QPoint:
        """Convert screen coordinates to original image coordinates."""
        if self.scale == 0:
            return pos
        
        # Calculate image position in widget
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        # Convert to image coordinates
        img_x = int((pos.x() - offset_x) / self.scale)
        img_y = int((pos.y() - offset_y) / self.scale)
        
        return QPoint(img_x, img_y)
    
    def image_to_screen(self, pos: QPoint) -> QPoint:
        """Convert image coordinates to screen coordinates."""
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        screen_x = int(pos.x() * self.scale + offset_x)
        screen_y = int(pos.y() * self.scale + offset_y)
        
        return QPoint(screen_x, screen_y)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        if not self.current_pixmap:
            return
        
        # Calculate scaled size and position
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        # Draw scaled pixmap
        scaled_pixmap = self.current_pixmap.scaled(img_w, img_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(offset_x, offset_y, scaled_pixmap)
        
        # Draw hitbox overlay
        if self.waiting_for_click and self.current_step:
            step = self.current_step
            
            # Scale hitbox coordinates
            hitbox_x = int(step.x * self.scale + offset_x)
            hitbox_y = int(step.y * self.scale + offset_y)
            hitbox_w = int(step.width * self.scale)
            hitbox_h = int(step.height * self.scale)
            
            # Parse hitbox line color
            line_color = QColor(step.hitbox_line_color) if step.hitbox_line_color else QColor(255, 165, 0)
            
            # Parse hitbox fill color with opacity
            fill_color_str = step.hitbox_fill_color or "#FF0000"
            fill_color = QColor(fill_color_str[:7]) if fill_color_str.startswith("#") else QColor(255, 165, 0)
            fill_opacity = step.hitbox_fill_opacity if hasattr(step, 'hitbox_fill_opacity') else 20
            fill_color.setAlpha(int(fill_opacity * 255 / 100))
            
            # Map line style
            line_style_map = {
                "solid": Qt.PenStyle.SolidLine,
                "dashed": Qt.PenStyle.DashLine,
                "dotted": Qt.PenStyle.DotLine
            }
            pen_style = line_style_map.get(step.hitbox_line_style, Qt.PenStyle.SolidLine)
            
            # Hitbox with custom styling
            line_width = max(1, int(step.hitbox_line_width * self.scale)) if step.hitbox_line_width else 4
            pen = QPen(line_color, line_width, pen_style)
            painter.setPen(pen)
            painter.setBrush(fill_color)
            
            hitbox_rect = QRect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
            if step.shape == "circle":
                painter.drawEllipse(hitbox_rect)
            else:
                painter.drawRect(hitbox_rect)
            
            # Description / Instruction box
            display_text = step.instruction if step.instruction else step.description
            painter.setBrush(QColor(0, 0, 0, 180))
            painter.setPen(Qt.PenStyle.NoPen)
            
            # Calculate text size for dynamic box sizing
            font_metrics = painter.fontMetrics()
            text_width = min(max(font_metrics.horizontalAdvance(display_text) + 40, 250), 500)
            text_height = max(font_metrics.boundingRect(0, 0, text_width - 20, 0, 
                Qt.TextFlag.TextWordWrap, display_text).height() + 30, 60)
            desc_rect = QRect(hitbox_x, hitbox_y + hitbox_h + 15, text_width, text_height)
            
            if desc_rect.bottom() > self.height():
                desc_rect.moveBottom(hitbox_y - 15)
            if desc_rect.right() > self.width():
                desc_rect.moveRight(self.width() - 20)
            
            painter.drawRoundedRect(desc_rect, 8, 8)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(desc_rect.adjusted(10, 5, -10, -5), 
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display_text)
    
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Wheel = Zoom
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Middle button for panning
            self.is_panning = True
            self.pan_start = event.pos() - self.pan_offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.RightButton:
            # Handle left/right click for hitbox
            if self.waiting_for_click and self.current_step and self.player:
                step = self.current_step
                required_button = getattr(step, 'click_button', 'left')
                
                # Map Qt button to step button type
                if event.button() == Qt.MouseButton.LeftButton:
                    clicked_button = 'left'
                elif event.button() == Qt.MouseButton.RightButton:
                    clicked_button = 'right'
                else:
                    clicked_button = 'left'
                
                img_pos = self.screen_to_image(event.pos())
                
                print(f"Click at screen: {event.pos().x()}, {event.pos().y()}")
                print(f"Click at image: {img_pos.x()}, {img_pos.y()}")
                print(f"Hitbox: x={step.x}, y={step.y}, w={step.width}, h={step.height}")
                print(f"Required button: {required_button}, Clicked: {clicked_button}")
                
                # Check if click is within hitbox
                in_hitbox = (step.x <= img_pos.x() <= step.x + step.width and
                            step.y <= img_pos.y() <= step.y + step.height)
                
                print(f"In hitbox: {in_hitbox}")
                
                if in_hitbox:
                    # Button check is optional - if left button required, accept left click
                    if clicked_button == required_button or required_button == 'left':
                        self.player.on_correct_click()
    
    def mouseMoveEvent(self, event):
        if self.is_panning:
            self.pan_offset = event.pos() - self.pan_start
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_pixmap and self.scale == self.base_scale:
            self.fit_to_window()


class ZoomControlBar(QWidget):
    """Compact zoom control bar - matches Editor preview style exactly."""
    
    def __init__(self, video_widget: ZoomableVideoWidget, parent=None):
        super().__init__(parent)
        self.video_widget = video_widget
        self.video_widget.zoom_control = self  # Reference for real-time updates
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        # Zoom Out
        self.btn_out = QPushButton("−")
        self.btn_out.setStyleSheet(self.get_btn_style())
        self.btn_out.clicked.connect(self.video_widget.zoom_out)
        layout.addWidget(self.btn_out)
        
        # Zoom In
        self.btn_in = QPushButton("+")
        self.btn_in.setStyleSheet(self.get_btn_style())
        self.btn_in.clicked.connect(self.video_widget.zoom_in)
        layout.addWidget(self.btn_in)
        
        # Fit
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setStyleSheet(self.get_btn_style())
        self.btn_fit.clicked.connect(self.video_widget.fit_to_window)
        layout.addWidget(self.btn_fit)
        
        # Dynamic zoom percentage label
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apply_theme()
        layout.addWidget(self.zoom_label)
        
        layout.addStretch()
    
    def get_btn_style(self):
        from . import styles
        if styles.is_dark_mode():
            return """
                QPushButton {
                    background: #3a3a3a;
                    color: #d0d0d0;
                    border: 1px solid #4a4a4a;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-size: 16px;
                }
                QPushButton:hover { background: #4a4a4a; color: white; }
                QPushButton:pressed { background: #2a2a2a; }
            """
        else:
            return """
                QPushButton {
                    background: #e8e8e8;
                    color: #333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-size: 16px;
                }
                QPushButton:hover { background: #ddd; }
                QPushButton:pressed { background: #ccc; }
            """
    
    def apply_theme(self):
        from . import styles
        btn_style = self.get_btn_style()
        self.btn_out.setStyleSheet(btn_style)
        self.btn_in.setStyleSheet(btn_style)
        self.btn_fit.setStyleSheet(btn_style)
        
        if styles.is_dark_mode():
            label_style = """
                QLabel {
                    background: #3a3a3a;
                    color: #d0d0d0;
                    border: 1px solid #4a4a4a;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-size: 16px;
                }
            """
        else:
            label_style = """
                QLabel {
                    background: #e8e8e8;
                    color: #333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-size: 16px;
                }
            """
        self.zoom_label.setStyleSheet(label_style)
    
    def update_zoom_label(self):
        self.zoom_label.setText(f"{self.video_widget.get_zoom_percent()}%")


# Keep VideoLabel for backward compatibility
class VideoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: black;")
        self.current_step = None
        self.waiting_for_click = False

    def set_overlay_state(self, step, waiting):
        self.current_step = step
        self.waiting_for_click = waiting
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.waiting_for_click and self.current_step:
            step = self.current_step
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            pen = QPen(QColor(255, 165, 0), 4)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            hitbox = QRect(step.x, step.y, step.width, step.height)
            if step.shape == "circle":
                painter.drawEllipse(hitbox)
            else:
                painter.drawRect(hitbox)
                
            display_text = step.instruction if step.instruction else step.description
            painter.setBrush(QColor(0, 0, 0, 180))
            painter.setPen(Qt.PenStyle.NoPen)
            
            font_metrics = painter.fontMetrics()
            text_width = min(max(font_metrics.horizontalAdvance(display_text) + 40, 250), 500)
            text_height = max(font_metrics.boundingRect(0, 0, text_width - 20, 0, 
                Qt.TextFlag.TextWordWrap, display_text).height() + 30, 60)
            desc_rect = QRect(step.x, step.y + step.height + 15, text_width, text_height)
            
            if desc_rect.bottom() > self.height():
                desc_rect.moveBottom(step.y - 15)
            if desc_rect.right() > self.width():
                desc_rect.moveRight(self.width() - 20)
            
            painter.drawRoundedRect(desc_rect, 8, 8)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(desc_rect.adjusted(10, 5, -10, -5), 
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display_text)

class Player(QWidget):
    # Add signal to notify main window
    from PySide6.QtCore import Signal
    closed = Signal()

    def __init__(self, tutorial: Tutorial, video_mode: bool = True):
        super().__init__()
        self.tutorial = tutorial
        self.current_step_index = 0
        self.waiting_for_click = False 
        
        # Enable keyboard focus for Player widget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # UI
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        
        # Use ZoomableVideoWidget instead of VideoLabel for proper zoom/pan
        self.video_widget = ZoomableVideoWidget(self)
        self.video_widget.player = self
        self.layout.addWidget(self.video_widget)
        
        # Zoom controls overlay (positioned in bottom-left)
        self.zoom_controls = ZoomControlBar(self.video_widget, self)
        self.zoom_controls.move(10, 10)  # Will be repositioned in resizeEvent
        self.zoom_controls.raise_()
        
        # Text input for keyboard steps (overlay, not in layout)
        self.text_input = SpecialKeyLineEdit(self)  # Custom class that forwards special keys
        self.text_input.setPlaceholderText("Type the required text and press Enter...")
        self.text_input.setStyleSheet("""
            QLineEdit {
                font-size: 32px;
                padding: 20px 40px;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                border: 3px solid #0096FF;
                border-radius: 15px;
            }
        """)
        self.text_input.setFixedWidth(600)
        self.text_input.setFixedHeight(80)
        self.text_input.returnPressed.connect(self.on_text_submitted)
        self.text_input.textChanged.connect(self.on_text_changed)  # Check for space
        self.text_input.hide()  # Hidden until keyboard step
        # Install event filter to capture keyboard events
        self.text_input.installEventFilter(self)
        # Don't add to layout - we'll position it manually
        
        # Video State
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.fps = 24.0
        self.frame_counter = 0
        
        # Audio State
        self.audio_player = None
        self.audio_output = None
        self.setup_audio()

        self.init_ui()
        
        # Mode check - use the passed video_mode parameter
        has_video = bool(self.tutorial.video_path and os.path.exists(self.tutorial.video_path))
        
        # User wants video mode AND video is available
        self.is_video_mode = video_mode and has_video
        
        print(f"DEBUG: video_mode requested = {video_mode}")
        print(f"DEBUG: has_video = {has_video}")
        print(f"DEBUG: is_video_mode = {self.is_video_mode}")
        
        if self.is_video_mode:
            self.setup_video()
        else:
            print("Running in Screenshot mode")
            self.update_image_mode()

    def _qt_key_to_name(self, key: int) -> str | None:
        if key == Qt.Key.Key_Delete:
            return "delete"
        if key == Qt.Key.Key_Backspace:
            return "backspace"
        if key == Qt.Key.Key_Tab:
            return "tab"
        if key == Qt.Key.Key_Escape:
            return "esc"
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            return "enter"
        if key == Qt.Key.Key_Space:
            return "space"
        if key == Qt.Key.Key_Up:
            return "up"
        if key == Qt.Key.Key_Down:
            return "down"
        if key == Qt.Key.Key_Left:
            return "left"
        if key == Qt.Key.Key_Right:
            return "right"
        if key == Qt.Key.Key_Home:
            return "home"
        if key == Qt.Key.Key_End:
            return "end"
        if key == Qt.Key.Key_PageUp:
            return "pageup"
        if key == Qt.Key.Key_PageDown:
            return "pagedown"
        if key == Qt.Key.Key_Insert:
            return "insert"
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            return f"f{key - Qt.Key.Key_F1 + 1}"
        return None

    def _expected_keyboard_input(self, step) -> str:
        return normalize_key_name(step.keyboard_input or "")

    def _is_special_keyboard_step(self, step) -> bool:
        if step.action_type != "keyboard":
            return False
        if getattr(step, "keyboard_mode", "text") == "key":
            return True
        return is_special_key_name(step.keyboard_input or "")

    def _complete_current_step(self):
        if self.current_step_index >= len(self.tutorial.steps):
            return
        step = self.tutorial.steps[self.current_step_index]
        if step.sound_enabled:
            winsound.MessageBeep(winsound.MB_OK)
        self.text_input.hide()
        self.next_step()

    def _handle_step_key_press(self, event) -> bool:
        print(f"Player._handle_step_key_press: key={event.key()}, waiting={self.waiting_for_click}")

        if self.current_step_index >= len(self.tutorial.steps):
            return False

        step = self.tutorial.steps[self.current_step_index]
        if step.action_type != "keyboard" or not step.keyboard_input or not self.waiting_for_click:
            return False

        key_name = self._qt_key_to_name(event.key())
        expected = self._expected_keyboard_input(step)
        print(f"  key_name={key_name}, expected={expected}, raw='{step.keyboard_input}'")

        if self._is_special_keyboard_step(step):
            if key_name and key_name == expected:
                print("  MATCH! Advancing to next step.")
                self._complete_current_step()
                event.accept()
                return True
            return False

        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            print("  Submit key pressed for regular text step")
            self.on_text_submitted()
            return True

        return False

    def init_ui(self):
        self.setWindowTitle("TutoMake Player")
        # Ensure it is really on top
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool) 
        # Type.Tool sometimes helps avoid taskbar interaction but Frameless is key.
        
        self.showFullScreen()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.raise_()
        self.activateWindow()
    
    def showEvent(self, event):
        """Fit video to window when shown."""
        super().showEvent(event)
        QTimer.singleShot(100, self.video_widget.fit_to_window)
    
    def resizeEvent(self, event):
        """Reposition zoom controls and fit video on resize."""
        super().resizeEvent(event)
        
        # Ensure zoom controls size is updated
        self.zoom_controls.adjustSize()
        
        # Reposition zoom controls at bottom-left
        self.zoom_controls.move(20, self.height() - self.zoom_controls.height() - 20)
        self.zoom_controls.raise_()
        
        # Fit video to new window size
        self.video_widget.fit_to_window()

    def setup_audio(self):
        """Initialize audio player if tutorial has audio."""
        if self.tutorial.audio_path and os.path.exists(self.tutorial.audio_path):
            print(f"Setting up audio: {self.tutorial.audio_path}")
            self.audio_output = QAudioOutput()
            self.audio_output.setVolume(1.0)
            
            self.audio_player = QMediaPlayer()
            self.audio_player.setAudioOutput(self.audio_output)
            self.audio_player.setSource(QUrl.fromLocalFile(self.tutorial.audio_path))
            print(f"Audio loaded, offset: {self.tutorial.audio_offset}s")
        else:
            print("No audio file or file not found")
    
    def play_audio(self):
        """Start audio playback with sync offset."""
        if self.audio_player:
            # Apply offset: positive offset means audio starts later
            offset_ms = int(self.tutorial.audio_offset * 1000)
            if offset_ms >= 0:
                # Delay audio start - will be handled by timer
                QTimer.singleShot(offset_ms, self._start_audio_playback)
            else:
                # Audio starts before video - seek to position
                self.audio_player.setPosition(-offset_ms)
                self._start_audio_playback()
    
    def _start_audio_playback(self):
        """Actually start the audio playback."""
        if self.audio_player:
            self.audio_player.play()
            print("Audio playback started")
    
    def pause_audio(self):
        """Pause audio playback."""
        if self.audio_player:
            self.audio_player.pause()
    
    def resume_audio(self):
        """Resume audio playback."""
        if self.audio_player:
            self.audio_player.play()
    
    def stop_audio(self):
        """Stop audio playback."""
        if self.audio_player:
            self.audio_player.stop()
    
    def setup_video(self):
        print(f"Opening video: {self.tutorial.video_path}")
        self.cap = cv2.VideoCapture(self.tutorial.video_path)
        if not self.cap.isOpened():
             print("Failed to open video")
             QMessageBox.critical(self, "Error", "Could not open video file.")
             self.close()
             return
             
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if self.fps <= 0: self.fps = 24.0
        
        print(f"Video Info: FPS={self.fps}, Total Frames={total_frames}")
        for i, step in enumerate(self.tutorial.steps):
            print(f"  Step {i}: timestamp={step.timestamp:.3f}s -> frame {int(step.timestamp * self.fps)}")
        
        interval = int(1000 / self.fps)
        self.timer.start(interval)
        
        # Start audio playback in sync with video
        self.play_audio()

    def next_frame(self):
        if self.waiting_for_click:
            return

        ret, frame = self.cap.read()
        if not ret:
            print("Video ended or read failed")
            self.timer.stop()
            if self.current_step_index >= len(self.tutorial.steps):
                QMessageBox.information(self, "Finished", "Tutorial Completed!")
                self.close()
            return
            
        # CV2 to QPixmap - IMPORTANT: copy the data to avoid memory issues
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)
        
        self.video_widget.setPixmap(pixmap)
        self.frame_counter += 1
        
        self.check_step_trigger()

    def check_step_trigger(self):
        if self.current_step_index >= len(self.tutorial.steps):
            return

        step = self.tutorial.steps[self.current_step_index]
        delay_frames = int(self.fps * 0.2)
        
        target_frame = int(step.timestamp * self.fps)
        pause_frame = max(target_frame + delay_frames, 5)  # At least play 5 frames
        
        # Only print every 24 frames to avoid spam
        if self.frame_counter % 24 == 0:
            print(f"Playing: frame={self.frame_counter}, waiting for pause_frame={pause_frame}")
        
        if self.frame_counter >= pause_frame:
            print(f"PAUSING: frame_counter={self.frame_counter}, step={self.current_step_index}, type={step.action_type}")
            self.waiting_for_click = True
            self.pause_audio()  # Pause audio when waiting for user
            
            if step.action_type == "keyboard":
                # Check if it's a special key step
                if self._is_special_keyboard_step(step):
                    # For special keys, HIDE text input and let Player handle keys directly
                    self.text_input.hide()
                    self.video_widget.set_overlay_state(step, True)  # Show hitbox as visual hint
                    # Ensure Player receives keyboard events
                    self.setFocus()
                    self.activateWindow()
                    print(f"Special key step: waiting for '{self._expected_keyboard_input(step)}', Player has focus={self.hasFocus()}")
                else:
                    # Normal text input
                    self.video_widget.set_overlay_state(None, False)
                    self.text_input.clear()
                    self.text_input.setReadOnly(False)
                    self.text_input.setPlaceholderText(f"Type: {step.keyboard_input}")
                    
                    x = (self.width() - self.text_input.width()) // 2
                    y = (self.height() - self.text_input.height()) // 2
                    self.text_input.move(x, y)
                    self.text_input.show()
                    self.text_input.raise_()
                    self.text_input.setFocus()
                    print(f"Showing text input for: '{step.keyboard_input}' at ({x}, {y})")
            else:
                # Show hitbox for click steps
                self.text_input.hide()
                self.video_widget.set_overlay_state(step, True)

    def eventFilter(self, obj, event):
        """Intercept keyboard events from text_input to handle special keys."""
        from PySide6.QtCore import QEvent
        
        if obj == self.text_input and event.type() == QEvent.Type.KeyPress:
            print(f"eventFilter: KeyPress from text_input, key={event.key()}")
            
            if self._handle_step_key_press(event):
                return True
        
        return super().eventFilter(obj, event)

    def on_text_submitted(self):
        if self.current_step_index >= len(self.tutorial.steps):
            return
            
        step = self.tutorial.steps[self.current_step_index]
        user_input = self.text_input.text().strip()
        expected = (step.keyboard_input or "").strip()
        
        print(f"on_text_submitted: user_input='{user_input}', expected='{expected}'")
        
        # Check if input matches (case-insensitive)
        if user_input.lower() == expected.lower():
            print(f"  MATCH! Advancing to next step.")
            if step.sound_enabled:
                winsound.MessageBeep(winsound.MB_OK)
            self.text_input.hide()
            self.next_step()
        else:
            # Wrong input - flash red
            self.text_input.setStyleSheet("""
                QLineEdit {
                    font-size: 24px;
                    padding: 15px;
                    background: rgba(255, 0, 0, 0.8);
                    color: white;
                    border: 2px solid red;
                    border-radius: 10px;
                }
            """)
            QTimer.singleShot(500, self.reset_text_input_style)
    
    def reset_text_input_style(self):
        self.text_input.setStyleSheet("""
            QLineEdit {
                font-size: 24px;
                padding: 15px;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                border: 2px solid #0096FF;
                border-radius: 10px;
            }
        """)

    def on_text_changed(self, text):
        """Check if user typed space to submit (only for regular text steps)."""
        # We don't want space to submit if the expected input actually contains space
        if self.current_step_index < len(self.tutorial.steps):
            step = self.tutorial.steps[self.current_step_index]
            if step.action_type == "keyboard" and step.keyboard_input:
                 # If expecting "Space", we handle it in keyPressEvent
                 pass

        if text.endswith(' '):
            # Remove the space and submit if it's a normal text step
            # For now, keep existing behavior but maybe refine later
            self.text_input.setText(text.rstrip())
            self.on_text_submitted()

    def update_image_mode(self):
        if self.current_step_index < len(self.tutorial.steps):
            step = self.tutorial.steps[self.current_step_index]
            pixmap = QPixmap(step.image_path)
            self.video_widget.setPixmap(pixmap)
            self.waiting_for_click = True
            self.video_widget.set_overlay_state(step, True)
            
            # Show/Hide text input based on step type
            if step.action_type == "keyboard":
                # Check if it's a special key step - handle Key.xxx format from pynput
                if self._is_special_keyboard_step(step):
                    self.text_input.setPlaceholderText(f"Press {display_key_name(step.keyboard_input)}...")
                    self.text_input.setText("")
                    self.text_input.setReadOnly(True)
                    self.text_input.show()
                    self.setFocus()  # Keep focus on player for keyPressEvent to work
                else:
                    self.text_input.setPlaceholderText("Type here...")
                    self.text_input.setText("")
                    self.text_input.show()
                    self.text_input.setFocus()
            else:
                self.text_input.hide()

    def mousePressEvent(self, event):
        if not self.waiting_for_click:
            return 
            
        # Coordinate mapping: video_label might be offset?
        # But we used QVBoxLayout with margin 0 and showFullScreen, so it should be same.
        x, y = event.pos().x(), event.pos().y()
        self.handle_click(x, y)

    def handle_click(self, x, y):
        if self.current_step_index >= len(self.tutorial.steps):
            self.close()
            return

        step = self.tutorial.steps[self.current_step_index]
        # print(f"Click at {x}, {y}. Target: {step.x}, {step.y}, {step.width}, {step.height}")
        
        # Only process click if step is click type
        if step.action_type != "click":
            return

        if (step.x <= x <= step.x + step.width) and (step.y <= y <= step.y + step.height):
            if step.sound_enabled:
                winsound.MessageBeep(winsound.MB_OK)
            self.next_step()

    def on_correct_click(self):
        """Called when user clicks correctly on hitbox (from ZoomableVideoWidget)."""
        if self.current_step_index < len(self.tutorial.steps):
            step = self.tutorial.steps[self.current_step_index]
            if step.sound_enabled:
                winsound.MessageBeep(winsound.MB_OK)
        self.next_step()

    def next_step(self):
        self.current_step_index += 1
        self.waiting_for_click = False
        self.video_widget.set_overlay_state(None, False)
        
        if self.current_step_index >= len(self.tutorial.steps):
            self.stop_audio()  # Stop audio when tutorial ends
            QMessageBox.information(self, "Finished", "Tutorial Completed!")
            self.close()
        elif not self.is_video_mode:
            self.update_image_mode()
        else:
            self.resume_audio()  # Resume audio when continuing video

    def keyPressEvent(self, event):
        # Close player with Ctrl + ` (backtick)
        if event.key() == Qt.Key.Key_QuoteLeft and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.cap: self.cap.release()
            self.timer.stop()
            self.close()
            return

        if self._handle_step_key_press(event):
            return

        current_step = (
            self.tutorial.steps[self.current_step_index]
            if self.current_step_index < len(self.tutorial.steps)
            else None
        )
        if event.key() == Qt.Key.Key_Escape and not (
            current_step and self._is_special_keyboard_step(current_step)
        ):
            self.close()
            return

        super().keyPressEvent(event)
            
    def closeEvent(self, event):
        self.stop_audio()  # Stop audio playback
        if self.cap: self.cap.release()
        self.timer.stop()
        self.closed.emit() # Emit signal
        super().closeEvent(event)

