from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                             QLabel, QLineEdit, QTextEdit, QFormLayout, QScrollArea, QSizePolicy,
                             QRadioButton, QButtonGroup, QCheckBox, QSlider, QPushButton,
                             QMenu, QMainWindow, QDockWidget, QGraphicsView, QGraphicsScene,
                             QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem, QGroupBox,
                             QComboBox, QFileDialog, QMessageBox, QSpinBox, QLayout, QAbstractSpinBox,
                             QStyle, QStyleOptionSpinBox, QApplication, QPlainTextEdit)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QResizeEvent, QImage, QAction, QPolygon, QFont, QBrush, QWheelEvent, QPalette, QMovie
from PySide6.QtCore import Qt, QRect, QTimer, Signal, QPoint, QRectF, QPointF, QSignalBlocker, QSize, QObject
import os
import tempfile
import threading
import wave
import cv2
import numpy as np
from ..key_utils import display_key_combo, display_key_name, key_code_from_key_name, normalize_key_combo, normalize_key_name
from ..model import Tutorial, Step
from ..recorder import AUDIO_AVAILABLE, get_audio_input_devices, record_test_audio_clip
from ..exporters.web_exporter import WebExporter
from ..settings import Settings

class ZoomableImageCanvas(QWidget):
    """Image canvas with zoom/pan support for Editor."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = None
        self.current_pixmap = None
        self.native_size = (800, 600)
        
        # Zoom state
        self.scale = 1.0
        self.base_scale = 1.0  # Scale to fit (treated as 100%)
        self.min_scale = 0.25
        self.max_scale = 4.0
        
        # Pan state
        self.pan_offset = QPoint(0, 0)
        self.is_panning = False
        self.pan_start = QPoint(0, 0)
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)
        self.apply_theme()
    
    def apply_theme(self):
        """Apply current theme colors."""
        from . import styles
        if styles.is_dark_mode():
            self.bg_color = QColor(26, 26, 26)
            self.text_color = QColor(100, 100, 100)
        else:
            self.bg_color = QColor(245, 245, 245)
            self.text_color = QColor(150, 150, 150)
        self.update()
    
    def set_step(self, step: Step):
        self.step = step
        if step and step.image_path:
            self.current_pixmap = QPixmap(step.image_path)
            self.native_size = (self.current_pixmap.width(), self.current_pixmap.height())
            self.fit_to_window()
        else:
            self.current_pixmap = None
        self.update()
    
    def setPixmap(self, pixmap: QPixmap):
        """Compatibility method for video frame display."""
        self.current_pixmap = pixmap
        if pixmap:
            self.native_size = (pixmap.width(), pixmap.height())
        self.update()
    
    def adjustSize(self):
        """Override to prevent automatic resizing."""
        pass
    
    def fit_to_window(self):
        """Calculate scale to fit image in widget."""
        if not self.current_pixmap:
            return
        
        img_w, img_h = self.native_size
        if img_w == 0 or img_h == 0:
            return
            
        win_w = max(self.width(), 100)
        win_h = max(self.height(), 100)
        
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
        self._update_zoom_label()
        self.update()
    
    def _update_zoom_label(self):
        """Notify zoom control to update label."""
        if hasattr(self, 'zoom_control') and self.zoom_control:
            self.zoom_control.update_zoom_label()
    
    def get_zoom_percent(self) -> int:
        if self.base_scale == 0:
            return 100
        return int((self.scale / self.base_scale) * 100)
    
    def screen_to_image(self, pos: QPoint) -> QPoint:
        """Convert screen coordinates to original image coordinates."""
        if self.scale == 0:
            return pos
        
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        img_x = int((pos.x() - offset_x) / self.scale)
        img_y = int((pos.y() - offset_y) / self.scale)
        
        return QPoint(img_x, img_y)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.bg_color)
        
        if not self.current_pixmap:
            painter.setPen(self.text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Image")
            return
        
        # Calculate scaled size and position
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        # Draw scaled pixmap
        scaled_pixmap = self.current_pixmap.scaled(img_w, img_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(offset_x, offset_y, scaled_pixmap)
        
        # Draw hitbox/overlay
        if self.step:
            step = self.step
            
            if step.action_type == "keyboard":
                # Text box for keyboard steps
                box_x = int(step.x * self.scale + offset_x)
                box_y = int(step.y * self.scale + offset_y)
                box_w = int(300 * self.scale)
                box_h = int(50 * self.scale)
                
                rect = QRect(box_x, box_y, box_w, box_h)
                
                bg_color = QColor(step.text_bg_color) if step.text_bg_color else QColor(0, 0, 0)
                bg_color.setAlpha(200)
                painter.setBrush(bg_color)
                painter.setPen(QPen(QColor(0, 150, 255), 3))
                painter.drawRoundedRect(rect, 10, 10)
                
                text_color = QColor(step.text_color) if step.text_color else QColor(255, 255, 255)
                painter.setPen(text_color)
                font = painter.font()
                font.setPointSize(max(8, int((step.text_font_size or 24) * self.scale)))
                font.setBold((getattr(step, "text_font_weight", "normal") or "normal").lower() == "bold")
                painter.setFont(font)
                
                display_text = step.keyboard_input if step.keyboard_input else "Type here..."
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, display_text)
            else:
                # Hitbox for click steps
                hitbox_x = int(step.x * self.scale + offset_x)
                hitbox_y = int(step.y * self.scale + offset_y)
                hitbox_w = int(step.width * self.scale)
                hitbox_h = int(step.height * self.scale)
                
                # Parse hitbox line color
                line_color = QColor(step.hitbox_line_color) if step.hitbox_line_color else QColor(255, 0, 0)
                
                # Parse hitbox fill color with opacity
                fill_color_str = step.hitbox_fill_color or "#FF0000"
                fill_color = QColor(fill_color_str[:7]) if fill_color_str.startswith("#") else QColor(255, 0, 0)
                fill_opacity = step.hitbox_fill_opacity if hasattr(step, 'hitbox_fill_opacity') else 20
                fill_color.setAlpha(int(fill_opacity * 255 / 100))
                
                # Map line style
                line_style_map = {
                    "solid": Qt.PenStyle.SolidLine,
                    "dashed": Qt.PenStyle.DashLine,
                    "dotted": Qt.PenStyle.DotLine
                }
                pen_style = line_style_map.get(step.hitbox_line_style, Qt.PenStyle.SolidLine)
                
                # Main hitbox with custom styling
                line_width = max(1, int(step.hitbox_line_width * self.scale)) if step.hitbox_line_width else 2
                painter.setPen(QPen(line_color, line_width, pen_style))
                painter.setBrush(fill_color)
                
                rect = QRect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
                if step.shape == "circle":
                    painter.drawEllipse(rect)
                else:
                    painter.drawRect(rect)
                
                # Resize handles (8 handles: corners + midpoints)
                handle_size = 8
                handle_color = QColor(0, 120, 255)
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.setBrush(handle_color)
                
                # Corner handles
                corners = [
                    (hitbox_x - handle_size//2, hitbox_y - handle_size//2),  # top-left
                    (hitbox_x + hitbox_w - handle_size//2, hitbox_y - handle_size//2),  # top-right
                    (hitbox_x - handle_size//2, hitbox_y + hitbox_h - handle_size//2),  # bottom-left
                    (hitbox_x + hitbox_w - handle_size//2, hitbox_y + hitbox_h - handle_size//2),  # bottom-right
                ]
                
                # Edge midpoint handles
                midpoints = [
                    (hitbox_x + hitbox_w//2 - handle_size//2, hitbox_y - handle_size//2),  # top-center
                    (hitbox_x + hitbox_w//2 - handle_size//2, hitbox_y + hitbox_h - handle_size//2),  # bottom-center
                    (hitbox_x - handle_size//2, hitbox_y + hitbox_h//2 - handle_size//2),  # left-center
                    (hitbox_x + hitbox_w - handle_size//2, hitbox_y + hitbox_h//2 - handle_size//2),  # right-center
                ]
                
                for hx, hy in corners + midpoints:
                    painter.drawRect(hx, hy, handle_size, handle_size)
    
    def _get_hitbox_screen_rect(self):
        """Get the hitbox rectangle in screen coordinates."""
        if not self.step or not self.current_pixmap:
            return None
        
        img_w = int(self.native_size[0] * self.scale)
        img_h = int(self.native_size[1] * self.scale)
        offset_x = (self.width() - img_w) // 2 + self.pan_offset.x()
        offset_y = (self.height() - img_h) // 2 + self.pan_offset.y()
        
        hitbox_x = int(self.step.x * self.scale + offset_x)
        hitbox_y = int(self.step.y * self.scale + offset_y)
        hitbox_w = int(self.step.width * self.scale)
        hitbox_h = int(self.step.height * self.scale)
        
        return QRect(hitbox_x, hitbox_y, hitbox_w, hitbox_h)
    
    def _get_handle_at(self, pos):
        """Check if position is on a resize handle. Returns handle name or None."""
        rect = self._get_hitbox_screen_rect()
        if not rect:
            return None
        
        handle_size = 12  # Slightly larger for easier clicking
        x, y = pos.x(), pos.y()
        
        # Define handle regions
        handles = {
            'top-left': QRect(rect.left() - handle_size//2, rect.top() - handle_size//2, handle_size, handle_size),
            'top-right': QRect(rect.right() - handle_size//2, rect.top() - handle_size//2, handle_size, handle_size),
            'bottom-left': QRect(rect.left() - handle_size//2, rect.bottom() - handle_size//2, handle_size, handle_size),
            'bottom-right': QRect(rect.right() - handle_size//2, rect.bottom() - handle_size//2, handle_size, handle_size),
            'top': QRect(rect.center().x() - handle_size//2, rect.top() - handle_size//2, handle_size, handle_size),
            'bottom': QRect(rect.center().x() - handle_size//2, rect.bottom() - handle_size//2, handle_size, handle_size),
            'left': QRect(rect.left() - handle_size//2, rect.center().y() - handle_size//2, handle_size, handle_size),
            'right': QRect(rect.right() - handle_size//2, rect.center().y() - handle_size//2, handle_size, handle_size),
        }
        
        for name, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return name
        return None
    
    def _get_cursor_for_handle(self, handle):
        """Get appropriate cursor for resize handle."""
        cursors = {
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
        }
        return cursors.get(handle, Qt.CursorShape.ArrowCursor)
    
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
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
            self.is_panning = True
            self.pan_start = event.pos() - self.pan_offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.step:
            # Check if clicking on a resize handle
            handle = self._get_handle_at(event.pos())
            if handle:
                self.resize_handle = handle
                self.resize_start_pos = event.pos()
                self.resize_start_rect = QRect(self.step.x, self.step.y, self.step.width, self.step.height)
                return
            
            # Check if clicking inside the hitbox (for dragging)
            rect = self._get_hitbox_screen_rect()
            if rect and rect.contains(event.pos()):
                self.is_dragging_hitbox = True
                self.drag_start_pos = event.pos()
                self.drag_start_hitbox = QPoint(self.step.x, self.step.y)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        if self.is_panning:
            self.pan_offset = event.pos() - self.pan_start
            self.update()
        elif hasattr(self, 'is_dragging_hitbox') and self.is_dragging_hitbox:
            # Dragging the hitbox
            delta = event.pos() - self.drag_start_pos
            delta_img = QPoint(int(delta.x() / self.scale), int(delta.y() / self.scale))
            self.step.x = self.drag_start_hitbox.x() + delta_img.x()
            self.step.y = self.drag_start_hitbox.y() + delta_img.y()
            self.update()
        elif hasattr(self, 'resize_handle') and self.resize_handle:
            # Resizing the hitbox
            delta = event.pos() - self.resize_start_pos
            delta_x = int(delta.x() / self.scale)
            delta_y = int(delta.y() / self.scale)
            
            start = self.resize_start_rect
            new_x, new_y, new_w, new_h = start.x(), start.y(), start.width(), start.height()
            
            if 'left' in self.resize_handle:
                new_x = start.x() + delta_x
                new_w = start.width() - delta_x
            if 'right' in self.resize_handle:
                new_w = start.width() + delta_x
            if 'top' in self.resize_handle:
                new_y = start.y() + delta_y
                new_h = start.height() - delta_y
            if 'bottom' in self.resize_handle:
                new_h = start.height() + delta_y
            
            # Minimum size
            if new_w >= 20 and new_h >= 20:
                self.step.x = new_x
                self.step.y = new_y
                self.step.width = new_w
                self.step.height = new_h
                self.update()
        else:
            # Update cursor based on hover position
            if self.step:
                handle = self._get_handle_at(event.pos())
                if handle:
                    self.setCursor(self._get_cursor_for_handle(handle))
                else:
                    rect = self._get_hitbox_screen_rect()
                    if rect and rect.contains(event.pos()):
                        self.setCursor(Qt.CursorShape.OpenHandCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'is_dragging_hitbox'):
                self.is_dragging_hitbox = False
            if hasattr(self, 'resize_handle'):
                self.resize_handle = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_pixmap:
            self.fit_to_window()
        
        # Reposition zoom controls overlay at bottom-left
        if hasattr(self, 'zoom_control') and self.zoom_control:
            self.zoom_control.move(10, self.height() - self.zoom_control.height() - 10)


class ZoomControlBar(QWidget):
    """Compact zoom control bar for editor - matches Steps panel buttons."""
    
    def __init__(self, canvas: ZoomableImageCanvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.canvas.zoom_control = self  # Reference for real-time updates
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        
        # Match Steps panel button style
        btn_style = """
            QPushButton {
                background: #3a3a3a;
                color: #d0d0d0;
                border: 1px solid #4a4a4a;
                border-radius: 3px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4a4a4a;
                color: white;
            }
            QPushButton:pressed {
                background: #2a2a2a;
            }
        """
        
        self.btn_out = QPushButton("-")
        self.btn_out.setStyleSheet(btn_style)
        self.btn_out.clicked.connect(self.canvas.zoom_out)
        layout.addWidget(self.btn_out)
        
        self.btn_in = QPushButton("+")
        self.btn_in.setStyleSheet(self.get_btn_style())
        self.btn_in.clicked.connect(self.canvas.zoom_in)
        layout.addWidget(self.btn_in)
        
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setStyleSheet(self.get_btn_style())
        self.btn_fit.clicked.connect(self.canvas.fit_to_window)
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
                    border-radius: 3px;
                    padding: 5px 12px;
                    font-size: 12px;
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
                    border-radius: 3px;
                    padding: 5px 12px;
                    font-size: 12px;
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
                    border-radius: 3px;
                    padding: 5px 12px;
                    font-size: 12px;
                }
            """
        else:
            label_style = """
                QLabel {
                    background: #e8e8e8;
                    color: #333;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 5px 12px;
                    font-size: 12px;
                }
            """
        self.zoom_label.setStyleSheet(label_style)
    
    def update_zoom_label(self):
        self.zoom_label.setText(f"{self.canvas.get_zoom_percent()}%")


# Keep ImageCanvas for compatibility
class ImageCanvas(QLabel):
    def __init__(self):
        super().__init__()
        self.step = None
        self.scale_factor = 1.0
        self.setMouseTracking(True)
        self.dragging = False

    def set_step(self, step: Step):
        self.step = step
        if step and step.image_path:
            pixmap = QPixmap(step.image_path)
            self.setPixmap(pixmap)
            self.adjustSize()
        else:
            self.setText("No Image")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.step:
            return
            
        painter = QPainter(self)
        
        if self.step.action_type == "keyboard":
            rect = QRect(self.step.x, self.step.y, 300, 50)
            
            bg_color = QColor(self.step.text_bg_color) if self.step.text_bg_color else QColor(0, 0, 0)
            bg_color.setAlpha(200)
            painter.setBrush(bg_color)
            painter.setPen(QPen(QColor(0, 150, 255), 3))
            painter.drawRoundedRect(rect, 10, 10)
            
            text_color = QColor(self.step.text_color) if self.step.text_color else QColor(255, 255, 255)
            painter.setPen(text_color)
            font = painter.font()
            font.setPointSize(self.step.text_font_size or 24)
            font.setBold((getattr(self.step, "text_font_weight", "normal") or "normal").lower() == "bold")
            painter.setFont(font)
            
            display_text = self.step.keyboard_input if self.step.keyboard_input else "Type here..."
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, display_text)
        else:
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(255, 0, 0, 50))
            
            rect = QRect(self.step.x, self.step.y, self.step.width, self.step.height)
            
            if self.step.shape == "circle":
                painter.drawEllipse(rect)
            else:
                painter.drawRect(rect)

    def mousePressEvent(self, event):
        if not self.step: return
        self.step.x = event.pos().x() - self.step.width // 2
        self.step.y = event.pos().y() - self.step.height // 2
        self.update()

class TimelineWidget(QWidget):
    """Timeline bar with QGraphicsView, step markers, and Premiere-style zoom slider."""
    
    step_selected = Signal(int)  # Emitted when a step marker is clicked
    step_added = Signal(float)   # Emitted when user adds a step (timestamp in seconds)
    step_added_with_type = Signal(float, str) # Emitted with action type (timestamp, type)
    step_deleted = Signal(int)   # Emitted when user deletes a step (index)
    steps_reordered = Signal()   # Emitted when steps are reordered by drag-and-drop
    position_changed = Signal(float)  # Emitted when slider position changes (seconds)
    split_requested = Signal()
    delete_gap_requested = Signal(bool)
    audio_offset_preview = Signal(float)
    audio_offset_committed = Signal(float)
    audio_trim_preview = Signal()
    audio_trim_committed = Signal()
    audio_trim_preview = Signal()
    audio_trim_committed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tutorial = None
        self.video_duration = 0.0  # in seconds
        self.current_position = 0.0
        self.fps = 24.0
        self.pixels_per_second = 50  # Base zoom level
        self.zoom_scale = 1.0  # Current zoom multiplier
        self.selected_step_index = -1  # Currently selected step (-1 = none)
        self.playhead_line_item = None
        self.playhead_triangle_item = None
        self.step_rect_items = {}
        self.step_text_items = {}
        self.track_clip_y = 0
        self.track_clip_h = 0
        self.total_height = 0
        self.scene_duration = 0.0
        self.edit_range_start = None
        self.edit_range_end = None
        self.range_overlay_item = None
        self.audio_rect_item = None
        self.audio_text_item = None
        self.audio_waveform_items = []
        self.audio_handle_items = []
        self.track_audio_y = 0
        self.track_audio_h = 0
        self.leading_padding_seconds = 0.0
        self.snap_enabled = True
        self.current_snap_interval = 0.5
        self.snap_temporarily_disabled = False
        self.minimum_audio_clip_duration = 0.2
        
        # Playback state
        self.is_playing = False
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_tick)
        
        self.setMinimumHeight(250)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Enable keyboard focus for spacebar play/pause
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Zoom label for bottom overlay
        self.zoom_label = QLabel("100%")
        self.time_label = QLabel("00:00.0 / 00:00.0")
        self.time_label.setStyleSheet("color: #ddd; font-size: 11px; padding: 2px 6px;")

        controls_bar = QHBoxLayout()
        controls_bar.setContentsMargins(8, 6, 8, 6)
        controls_bar.setSpacing(8)

        timeline_btn_style = """
            QPushButton {
                min-height: 32px;
                min-width: 78px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
                background: #353535;
                color: #f3f3f3;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #454545;
                border-color: #5f5f5f;
            }
            QPushButton:pressed {
                background: #2d2d2d;
            }
        """

        self.btn_step_back = QPushButton("-0.1s")
        self.btn_step_back.setStyleSheet(timeline_btn_style)
        self.btn_step_back.clicked.connect(lambda: self.move_playhead(-0.1))
        controls_bar.addWidget(self.btn_step_back)

        self.btn_step_forward = QPushButton("+0.1s")
        self.btn_step_forward.setStyleSheet(timeline_btn_style)
        self.btn_step_forward.clicked.connect(lambda: self.move_playhead(0.1))
        controls_bar.addWidget(self.btn_step_forward)

        self.btn_mark_in = QPushButton("Mark In")
        self.btn_mark_in.setStyleSheet(timeline_btn_style)
        self.btn_mark_in.clicked.connect(self.mark_range_start)
        controls_bar.addWidget(self.btn_mark_in)

        self.btn_mark_out = QPushButton("Mark Out")
        self.btn_mark_out.setStyleSheet(timeline_btn_style)
        self.btn_mark_out.clicked.connect(self.mark_range_end)
        controls_bar.addWidget(self.btn_mark_out)

        self.btn_clear_range = QPushButton("Clear Range")
        self.btn_clear_range.setStyleSheet(timeline_btn_style)
        self.btn_clear_range.clicked.connect(self.clear_edit_range)
        controls_bar.addWidget(self.btn_clear_range)

        self.btn_split = QPushButton("Split")
        self.btn_split.setStyleSheet(timeline_btn_style)
        self.btn_split.clicked.connect(self.split_requested.emit)
        controls_bar.addWidget(self.btn_split)

        self.btn_delete_gap = QPushButton("Delete Gap")
        self.btn_delete_gap.setStyleSheet(timeline_btn_style)
        self.btn_delete_gap.clicked.connect(lambda: self.delete_gap_requested.emit(False))
        controls_bar.addWidget(self.btn_delete_gap)

        self.btn_ripple_delete = QPushButton("Ripple Delete")
        self.btn_ripple_delete.setStyleSheet(timeline_btn_style)
        self.btn_ripple_delete.clicked.connect(lambda: self.delete_gap_requested.emit(True))
        controls_bar.addWidget(self.btn_ripple_delete)

        controls_bar.addStretch()
        self.snap_label = QLabel("Snap 0.5s")
        self.snap_label.setStyleSheet("color: #a5d6a7; font-size: 11px; padding: 2px 6px;")
        controls_bar.addWidget(self.snap_label)
        controls_bar.addWidget(self.time_label)
        controls_bar.addWidget(self.zoom_label)
        main_layout.addLayout(controls_bar)
        
        # ===== Timeline Area with Track Labels =====
        timeline_container = QHBoxLayout()
        timeline_container.setContentsMargins(0, 0, 0, 0)
        timeline_container.setSpacing(0)
        
        # Track labels (left side)
        self.track_labels = QWidget()
        self.track_labels.setFixedWidth(50)
        self.track_labels.setStyleSheet("background: #252525;")
        labels_layout = QVBoxLayout(self.track_labels)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(0)
        
        # Ruler spacer
        ruler_spacer = QLabel("")
        ruler_spacer.setFixedHeight(25)
        ruler_spacer.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #444;")
        labels_layout.addWidget(ruler_spacer)
        
        # Track labels (simplified to V1 and A1 only)
        track_names = ["V1", "A1"]
        track_colors = ["#3a6ea5", "#5a8a5a"]
        for name, color in zip(track_names, track_colors):
            lbl = QLabel(name)
            lbl.setFixedHeight(40)  # Taller tracks
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"background: {color}; color: white; font-weight: bold; font-size: 11px; border-bottom: 1px solid #333;")
            labels_layout.addWidget(lbl)
        
        labels_layout.addStretch()
        timeline_container.addWidget(self.track_labels)
        
        # ===== QGraphicsView Timeline =====
        self.scene = QGraphicsScene()
        self.view = TimelineGraphicsView(self.scene, self)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setStyleSheet("QGraphicsView { border: none; background: #1e1e1e; }")
        self.view.setMinimumHeight(110)  # Adjusted for 2 tracks
        self.view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        timeline_container.addWidget(self.view, 1)
        
        main_layout.addLayout(timeline_container, 1)
        
        # ===== Premiere-style Zoom Slider Bar =====
        zoom_bar = QHBoxLayout()
        zoom_bar.setContentsMargins(50, 2, 5, 2)  # Left margin matches track labels
        
        # Zoom out button
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(24, 20)
        btn_zoom_out.clicked.connect(self.zoom_out)
        btn_zoom_out.setStyleSheet("QPushButton { background: #333; color: #aaa; border: none; font-size: 14px; } QPushButton:hover { background: #444; }")
        zoom_bar.addWidget(btn_zoom_out)
        
        # Custom zoom slider
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #666;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #888;
            }
            QSlider::sub-page:horizontal {
                background: #4a90d9;
                border-radius: 4px;
            }
        """)
        zoom_bar.addWidget(self.zoom_slider, 1)
        
        # Zoom in button
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(24, 20)
        btn_zoom_in.clicked.connect(self.zoom_in)
        btn_zoom_in.setStyleSheet("QPushButton { background: #333; color: #aaa; border: none; font-size: 14px; } QPushButton:hover { background: #444; }")
        zoom_bar.addWidget(btn_zoom_in)
        
        main_layout.addLayout(zoom_bar)
        
    def on_zoom_slider_changed(self, value):
        """Handle zoom slider value change."""
        self.zoom_scale = value / 100.0
        self.zoom_label.setText(f"{value}%")
        self.rebuild_scene()
        
    def zoom_in(self):
        new_val = min(self.zoom_slider.value() + 20, 400)
        self.zoom_slider.setValue(new_val)
        
    def zoom_out(self):
        new_val = max(self.zoom_slider.value() - 20, 10)
        self.zoom_slider.setValue(new_val)
        
    def apply_wheel_zoom(self, delta, center_x):
        """Apply zoom from Ctrl+wheel, centered on cursor position."""
        # Calculate zoom factor
        if delta > 0:
            factor = 1.15
        else:
            factor = 1 / 1.15
        
        new_scale = self.zoom_scale * factor
        new_scale = max(0.1, min(new_scale, 4.0))
        
        # Update slider (which triggers update_scene)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(new_scale * 100))
        self.zoom_slider.blockSignals(False)
        
        self.zoom_scale = new_scale
        self.zoom_label.setText(f"{int(new_scale * 100)}%")
        
        # Scroll to keep cursor position centered
        scroll_bar = self.view.horizontalScrollBar()
        scroll_pos = scroll_bar.value()
        
        # Update scene and adjust scroll
        self.rebuild_scene()
        
        # Center on cursor position after zoom
        new_center_x = center_x * factor
        scroll_bar.setValue(int(scroll_pos * factor))
        
    def set_tutorial(self, tutorial):
        self.tutorial = tutorial
        if tutorial and tutorial.video_path and os.path.exists(tutorial.video_path):
            cap = cv2.VideoCapture(tutorial.video_path)
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            self.video_duration = frame_count / self.fps if self.fps > 0 else 0
            cap.release()
        else:
            step_timestamps = [float(step.timestamp or 0.0) for step in getattr(tutorial, "steps", [])]
            self.video_duration = (max(step_timestamps) + 1.0) if step_timestamps else 0
            self.fps = 24.0
        self.current_position = max(0.0, min(self.current_position, self.video_duration))
        self.update_time_label()
        self.rebuild_scene()

    def move_playhead(self, delta_seconds):
        self.current_position = max(0.0, min(self.current_position + delta_seconds, self.video_duration))
        self.update_time_label()
        self.position_changed.emit(self.current_position)
        self.update_playhead()

    def scene_x_for_time(self, seconds: float) -> int:
        pps = self.pixels_per_second * self.zoom_scale
        return int((self.leading_padding_seconds + seconds) * pps)

    def time_for_scene_x(self, scene_x: float) -> float:
        pps = self.pixels_per_second * self.zoom_scale
        return (scene_x / pps) - self.leading_padding_seconds

    def _snap_interval_for_zoom(self) -> float:
        pps = self.pixels_per_second * self.zoom_scale
        if pps >= 200:
            return 0.1
        if pps >= 120:
            return 0.25
        if pps >= 70:
            return 0.5
        if pps >= 25:
            return 1.0
        return 2.0

    def snap_time(self, seconds: float) -> float:
        if not self.snap_enabled or self.snap_temporarily_disabled:
            return seconds
        interval = self._snap_interval_for_zoom()
        self.current_snap_interval = interval
        return round(seconds / interval) * interval

    def mark_range_start(self):
        self.edit_range_start = self.current_position
        self.update_time_label()
        self.rebuild_scene()

    def mark_range_end(self):
        self.edit_range_end = self.current_position
        self.update_time_label()
        self.rebuild_scene()

    def clear_edit_range(self):
        self.edit_range_start = None
        self.edit_range_end = None
        self.update_time_label()
        self.rebuild_scene()

    def get_edit_range(self):
        if self.edit_range_start is None or self.edit_range_end is None:
            return None
        start = min(self.edit_range_start, self.edit_range_end)
        end = max(self.edit_range_start, self.edit_range_end)
        if end <= start:
            return None
        return start, end
    
    def toggle_play(self):
        """Toggle playback state."""
        if self.is_playing:
            self.is_playing = False
            self.play_timer.stop()
        else:
            self.is_playing = True
            # Update every ~33ms for ~30fps playback
            self.play_timer.start(33)
    
    def _on_play_tick(self):
        """Called on each playback timer tick."""
        if not self.is_playing or self.video_duration <= 0:
            return
        
        # Advance by real time (33ms = 0.033s per tick)
        self.current_position += 0.033
        
        # Loop or stop at end
        if self.current_position >= self.video_duration:
            self.current_position = 0
            self.is_playing = False
            self.play_timer.stop()
        
        # Update playhead and emit position change
        self.update_playhead()
        self.position_changed.emit(self.current_position)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        from PySide6.QtCore import Qt
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            super().keyPressEvent(event)
            return
        
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Home:
            self.current_position = 0
            self.update_time_label()
            self.update_playhead()
            self.position_changed.emit(self.current_position)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_End:
            self.current_position = self.video_duration
            self.update_time_label()
            self.update_playhead()
            self.position_changed.emit(self.current_position)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Left:
            self.move_playhead(-0.1)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Right:
            self.move_playhead(0.1)
            event.accept()
            return
        
        super().keyPressEvent(event)
        
    def rebuild_scene(self):
        """Rebuild timeline background and clip items for structural changes."""
        self.scene.clear()
        self.step_rect_items.clear()
        self.step_text_items.clear()
        self.playhead_line_item = None
        self.playhead_triangle_item = None
        self.audio_rect_item = None
        self.audio_text_item = None
        self.audio_waveform_items = []
        self.audio_handle_items = []
        
        pps = self.pixels_per_second * self.zoom_scale
        duration = max(self.video_duration, 3600)  # Minimum 1 hour (feels infinite)
        total_width = int((duration + self.leading_padding_seconds + 2) * pps) + 100
        self.scene_duration = duration
        self.current_snap_interval = self._snap_interval_for_zoom()
        
        ruler_height = 25
        track_height = 40  # Taller tracks for 2-track layout
        total_height = ruler_height + 2 * track_height  # Only V1 and A1
        self.total_height = total_height
        self.track_clip_y = ruler_height + 2
        self.track_clip_h = track_height - 4
        self.track_audio_y = ruler_height + track_height + 2
        self.track_audio_h = track_height - 4
        
        # Set scene rect
        self.scene.setSceneRect(0, 0, total_width, total_height)
        
        # ===== Grid Background =====
        grid_pen = QPen(QColor(40, 40, 40), 1)
        
        # Vertical grid lines (time markers)
        if pps >= 100:
            interval = 1
        elif pps >= 50:
            interval = 2
        elif pps >= 25:
            interval = 5
        else:
            interval = 10
            
        for t in range(0, int(duration) + interval, interval):
            x = self.scene_x_for_time(t)
            line = self.scene.addLine(x, 0, x, total_height, grid_pen)
        
        # Horizontal grid lines (track separators) - only 3 lines for 2 tracks
        for i in range(3):
            y = ruler_height + i * track_height
            self.scene.addLine(0, y, total_width, y, QPen(QColor(50, 50, 50), 1))
        
        # ===== Time Ruler Background =====
        ruler_rect = self.scene.addRect(0, 0, total_width, ruler_height, 
                                        QPen(Qt.PenStyle.NoPen), QBrush(QColor(26, 26, 26)))
        
        # Time labels
        for t in range(0, int(duration) + interval, interval):
            x = self.scene_x_for_time(t)
            
            # Tick mark
            self.scene.addLine(x, ruler_height - 10, x, ruler_height, QPen(QColor(80, 80, 80), 1))
            
            # Time text
            time_str = f"{t // 60}:{t % 60:02d}"
            text_item = self.scene.addText(time_str, QFont("Arial", 8))
            text_item.setDefaultTextColor(QColor(150, 150, 150))
            text_item.setPos(x + 2, 2)
        
        # ===== Track Backgrounds =====
        # Draw colored background for full timeline width (infinite feel)
        
        # Track colors with transparency (only V1 and A1)
        track_colors = [
            QColor(42, 78, 117, 100),  # V1 - blue, semi-transparent
            QColor(58, 98, 58, 100),   # A1 - green, semi-transparent
        ]
        
        for i, color in enumerate(track_colors):
            y = ruler_height + i * track_height
            
            # Draw colored background for full width
            self.scene.addRect(0, y, total_width, track_height, 
                              QPen(Qt.PenStyle.NoPen), QBrush(color))
            
            # Track separator line
            self.scene.addLine(0, y + track_height, total_width, y + track_height, 
                              QPen(QColor(50, 50, 50), 1))

        edit_range = self.get_edit_range()
        if edit_range:
            start, end = edit_range
            overlay_x = int(start * pps)
            overlay_x = self.scene_x_for_time(start)
            overlay_w = max(1, int((end - start) * pps))
            self.range_overlay_item = self.scene.addRect(
                overlay_x,
                ruler_height,
                overlay_w,
                total_height - ruler_height,
                QPen(QColor(255, 196, 0, 160), 1, Qt.PenStyle.DashLine),
                QBrush(QColor(255, 196, 0, 45)),
            )
        
        # ===== Step Clips on V1 =====
        if self.tutorial and self.tutorial.steps:
            for i, step in enumerate(self.tutorial.steps):
                clip = self.scene.addRect(0, self.track_clip_y, 0, self.track_clip_h, QPen(), QBrush())
                clip.setData(0, i)
                clip.setData(1, "step")
                clip.setFlag(clip.GraphicsItemFlag.ItemIsSelectable, True)
                text = self.scene.addText("", QFont("Arial", 9, QFont.Weight.Bold))
                text.setDefaultTextColor(QColor(255, 255, 255))
                self.step_rect_items[i] = clip
                self.step_text_items[i] = text
                self._update_step_item(i)

        if self.tutorial and (self.tutorial.audio_path or self.tutorial.video_path):
            self.audio_rect_item = self.scene.addRect(0, self.track_audio_y, 0, self.track_audio_h, QPen(), QBrush())
            self.audio_rect_item.setData(0, "audio")
            self.audio_rect_item.setData(1, "audio")
            self.audio_text_item = self.scene.addText("", QFont("Arial", 9, QFont.Weight.Bold))
            self.audio_text_item.setDefaultTextColor(QColor(230, 255, 230))
            self._update_audio_item()

        self._create_playhead_items()
        self.update_playhead()

    def update_scene(self):
        """Compatibility wrapper for existing callers."""
        self.rebuild_scene()

    def _step_clip_width(self) -> int:
        pps = self.pixels_per_second * self.zoom_scale
        return max(30, int(pps * 0.5))

    def _update_step_item(self, step_idx: int):
        if not self.tutorial or step_idx not in self.step_rect_items or step_idx >= len(self.tutorial.steps):
            return

        pps = self.pixels_per_second * self.zoom_scale
        clip_w = self._step_clip_width()
        step = self.tutorial.steps[step_idx]
        x = self.scene_x_for_time(step.timestamp)

        if step.action_type == "keyboard":
            clip_color = QColor(0, 120, 200)
        else:
            clip_color = QColor(200, 100, 0)

        if self.selected_step_index == step_idx:
            border_pen = QPen(QColor(255, 255, 0), 3)
        else:
            border_pen = QPen(QColor(255, 255, 255, 100), 1)

        rect_item = self.step_rect_items[step_idx]
        rect_item.setRect(x, self.track_clip_y, clip_w, self.track_clip_h)
        rect_item.setPen(border_pen)
        rect_item.setBrush(QBrush(clip_color))
        rect_item.setData(0, step_idx)

        text_item = self.step_text_items[step_idx]
        text_item.setPlainText(str(step_idx + 1))
        text_item.setPos(x + 4, self.track_clip_y)

    def _update_audio_item(self):
        if not self.tutorial or not self.audio_rect_item or not self.audio_text_item:
            return

        for item in self.audio_handle_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.audio_handle_items = []

        offset = float(getattr(self.tutorial, "audio_offset", 0.0) or 0.0)
        x = self.scene_x_for_time(offset)
        effective_duration = self.get_effective_audio_duration()
        pps = self.pixels_per_second * self.zoom_scale
        clip_w = max(24, int(max(effective_duration, self.minimum_audio_clip_duration) * pps))
        self.audio_rect_item.setRect(x, self.track_audio_y, clip_w, self.track_audio_h)
        self.audio_rect_item.setPen(QPen(QColor(170, 255, 170, 180), 1))
        self.audio_rect_item.setBrush(QBrush(QColor(70, 130, 70, 180)))
        trim_start = float(getattr(self.tutorial, "audio_trim_start", 0.0) or 0.0)
        trim_end = getattr(self.tutorial, "audio_trim_end", None)
        trim_text = f"{trim_start:.1f}s"
        if trim_end is not None:
            trim_text += f"-{float(trim_end):.1f}s"
        self.audio_text_item.setPlainText(f"Audio {offset:+.1f}s  Trim {trim_text}")
        self.audio_text_item.setPos(x + 6, self.track_audio_y + 2)
        self._draw_audio_waveform(x, clip_w)
        self._draw_audio_handles(x, clip_w)

    def get_audio_source_duration(self):
        if not self.tutorial:
            return None
        audio_path = self.tutorial.audio_path
        if audio_path and os.path.exists(audio_path) and audio_path.lower().endswith(".wav"):
            try:
                with wave.open(audio_path, "rb") as wav_file:
                    frame_count = wav_file.getnframes()
                    frame_rate = wav_file.getframerate() or 0
                if frame_rate > 0:
                    return frame_count / frame_rate
            except Exception:
                return None
        if self.video_duration > 0:
            return self.video_duration
        return None

    def get_audio_trim_bounds(self):
        trim_start = max(0.0, float(getattr(self.tutorial, "audio_trim_start", 0.0) or 0.0))
        trim_end = getattr(self.tutorial, "audio_trim_end", None)
        source_duration = self.get_audio_source_duration()
        if trim_end is None:
            trim_end = source_duration
        if source_duration is not None:
            trim_end = min(float(trim_end), source_duration)
        if trim_end is None:
            trim_end = trim_start + max(self.video_duration, 1.0)
        trim_end = max(trim_start + self.minimum_audio_clip_duration, float(trim_end))
        return trim_start, trim_end

    def get_effective_audio_duration(self):
        trim_start, trim_end = self.get_audio_trim_bounds()
        return max(self.minimum_audio_clip_duration, trim_end - trim_start)

    def _draw_audio_handles(self, clip_x: int, clip_width: int):
        handle_width = 8
        handle_brush = QBrush(QColor(235, 255, 235, 220))
        handle_pen = QPen(QColor(220, 255, 220, 180), 1)
        grip_height = max(12, self.track_audio_h - 8)
        grip_y = self.track_audio_y + (self.track_audio_h - grip_height) / 2

        left_handle = self.scene.addRect(
            clip_x - handle_width / 2,
            grip_y,
            handle_width,
            grip_height,
            handle_pen,
            handle_brush,
        )
        left_handle.setData(0, "audio")
        left_handle.setData(1, "audio")
        left_handle.setData(2, "audio_handle_left")

        right_handle = self.scene.addRect(
            clip_x + clip_width - handle_width / 2,
            grip_y,
            handle_width,
            grip_height,
            handle_pen,
            handle_brush,
        )
        right_handle.setData(0, "audio")
        right_handle.setData(1, "audio")
        right_handle.setData(2, "audio_handle_right")

        self.audio_handle_items.extend([left_handle, right_handle])

    def _draw_audio_waveform(self, clip_x: int, clip_width: int):
        for item in self.audio_waveform_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.audio_waveform_items = []

        amplitudes = self._get_audio_waveform_samples(48)
        if not amplitudes:
            return

        center_y = self.track_audio_y + self.track_audio_h / 2
        usable_height = max(6, self.track_audio_h - 10)
        bar_spacing = max(3, clip_width / max(len(amplitudes), 1))
        bar_width = max(2, min(6, int(bar_spacing * 0.5)))

        baseline = self.scene.addLine(
            clip_x,
            center_y,
            clip_x + clip_width,
            center_y,
            QPen(QColor(220, 255, 220, 60), 1),
        )
        self.audio_waveform_items.append(baseline)

        for idx, amplitude in enumerate(amplitudes):
            bar_height = max(2.0, amplitude * usable_height)
            bar_x = clip_x + idx * bar_spacing + max(0, (bar_spacing - bar_width) / 2)
            bar = self.scene.addRect(
                bar_x,
                center_y - bar_height / 2,
                bar_width,
                bar_height,
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor(220, 255, 220, 150)),
            )
            self.audio_waveform_items.append(bar)

    def _get_audio_waveform_samples(self, sample_count: int):
        audio_path = self.tutorial.audio_path if self.tutorial else None
        if audio_path and os.path.exists(audio_path) and audio_path.lower().endswith(".wav"):
            try:
                with wave.open(audio_path, "rb") as wav_file:
                    frame_count = wav_file.getnframes()
                    channels = max(1, wav_file.getnchannels())
                    raw_frames = wav_file.readframes(frame_count)
                samples = np.frombuffer(raw_frames, dtype=np.int16)
                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1)
                if len(samples) > 0:
                    trim_start, trim_end = self.get_audio_trim_bounds()
                    source_duration = self.get_audio_source_duration() or 0.0
                    if source_duration > 0:
                        start_idx = int(max(0, min(len(samples), round((trim_start / source_duration) * len(samples)))))
                        end_idx = int(max(start_idx + 1, min(len(samples), round((trim_end / source_duration) * len(samples)))))
                        samples = samples[start_idx:end_idx]
                    window_size = max(1, len(samples) // sample_count)
                    amplitudes = []
                    for start in range(0, len(samples), window_size):
                        chunk = samples[start:start + window_size]
                        if len(amplitudes) >= sample_count:
                            break
                        amplitudes.append(float(np.max(np.abs(chunk))) / 32767.0 if len(chunk) else 0.0)
                    if amplitudes:
                        return amplitudes
            except Exception:
                pass

        # Fallback pattern so the audio clip remains readable even without a standalone wav file.
        return [0.22, 0.38, 0.55, 0.31, 0.74, 0.46, 0.29, 0.62, 0.41, 0.68, 0.25, 0.52] * 4

    def refresh_step_items(self):
        if not self.tutorial:
            return
        for i in range(len(self.tutorial.steps)):
            self._update_step_item(i)

    def _create_playhead_items(self):
        playhead_pen = QPen(QColor(255, 0, 0), 2)
        self.playhead_line_item = self.scene.addLine(0, 0, 0, self.total_height, playhead_pen)
        from PySide6.QtGui import QPolygonF
        triangle = QPolygonF([QPointF(-6, 0), QPointF(6, 0), QPointF(0, 10)])
        self.playhead_triangle_item = self.scene.addPolygon(
            triangle,
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(255, 0, 0))
        )

    def update_playhead(self):
        if not self.playhead_line_item or not self.playhead_triangle_item:
            return
        pps = self.pixels_per_second * self.zoom_scale
        playhead_x = self.scene_x_for_time(self.current_position)
        self.playhead_line_item.setLine(playhead_x, 0, playhead_x, self.total_height)
        self.playhead_triangle_item.setPos(playhead_x, 0)
        
    def on_timeline_clicked(self, position):
        """Called when timeline is clicked."""
        self.current_position = max(0, min(position, self.video_duration))
        self.update_time_label()
        self.position_changed.emit(self.current_position)
        self.update_playhead()
            
    def update_time_label(self):
        current = self.format_time(self.current_position)
        total = self.format_time(self.video_duration)
        range_text = ""
        edit_range = self.get_edit_range()
        if edit_range:
            start, end = edit_range
            range_text = f"  Range {self.format_time(start)}-{self.format_time(end)}"
        elif self.edit_range_start is not None:
            range_text = f"  In {self.format_time(self.edit_range_start)}"
        elif self.edit_range_end is not None:
            range_text = f"  Out {self.format_time(self.edit_range_end)}"
        self.time_label.setText(f"{current} / {total}{range_text}")
        if self.snap_temporarily_disabled:
            self.snap_label.setText("Snap Off (Alt)")
            self.snap_label.setStyleSheet("color: #ffcc80; font-size: 11px; padding: 2px 6px;")
        else:
            self.snap_label.setText(f"Snap {self.current_snap_interval:.2f}s")
            self.snap_label.setStyleSheet("color: #a5d6a7; font-size: 11px; padding: 2px 6px;")
        
    def format_time(self, seconds):
        total_tenths = max(0, int(round(seconds * 10)))
        m = total_tenths // 600
        s = (total_tenths % 600) // 10
        tenths = total_tenths % 10
        return f"{m:02d}:{s:02d}.{tenths}"
        
    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self.play_timer.stop()
        else:
            self.is_playing = True
            self.play_timer.start(int(1000 / self.fps))
            
    def advance_frame(self):
        if self.current_position < self.video_duration:
            self.current_position += 1.0 / self.fps
            self.update_time_label()
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            
            # Auto-scroll to keep playhead visible
            pps = self.pixels_per_second * self.zoom_scale
            playhead_x = self.scene_x_for_time(self.current_position)
            self.view.ensureVisible(playhead_x, 50, 100, 50)
        else:
            self.toggle_play()
            
    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        add_click_action = QAction("Add Click Step Here", self)
        add_click_action.triggered.connect(lambda: self.step_added.emit(self.current_position))
        menu.addAction(add_click_action)
        
        add_text_action = QAction("Add Text Step Here", self)
        add_text_action.triggered.connect(lambda: self.add_text_step(self.current_position))
        menu.addAction(add_text_action)
        
        menu.addSeparator()
        
        if self.tutorial and self.tutorial.steps:
            closest_idx = None
            min_diff = float('inf')
            for i, step in enumerate(self.tutorial.steps):
                diff = abs(step.timestamp - self.current_position)
                if diff < min_diff and diff < 1.0:
                    min_diff = diff
                    closest_idx = i
                    
            if closest_idx is not None:
                step = self.tutorial.steps[closest_idx]
                delete_action = QAction(f"Delete Step {closest_idx + 1}", self)
                delete_action.triggered.connect(lambda: self.step_deleted.emit(closest_idx))
                menu.addAction(delete_action)
        
        menu.exec(self.mapToGlobal(pos))
    
    def add_text_step(self, timestamp):
        new_step = Step(
            action_type="keyboard",
            description="Type text",
            timestamp=timestamp,
            keyboard_input="",
            keyboard_mode="text",
        )
        
        insert_idx = 0
        for i, step in enumerate(self.tutorial.steps):
            if step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self.tutorial.steps.insert(insert_idx, new_step)
        self.step_added.emit(timestamp)
        self.rebuild_scene()
        
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        from ..settings import Settings
        settings = Settings()
        
        # Helper to match key events against settings
        def matches(action):
            event_sequence = QKeySequence(event.keyCombination())
            return event_sequence == settings.get_key(action)
        
        if matches("toggle_play"):
            self.toggle_play()
            event.accept()
        elif matches("frame_start"):
            # Go to start
            self.current_position = 0
            self.update_time_label()
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            event.accept()
        elif matches("frame_end"):
            # Go to end
            self.current_position = self.video_duration
            self.update_time_label()
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            event.accept()
        elif matches("frame_prev"):
            self.move_playhead(-0.1)
            event.accept()
        elif matches("frame_next"):
            self.move_playhead(0.1)
            event.accept()
        else:
            super().keyPressEvent(event)


class TimelineGraphicsView(QGraphicsView):
    """Custom QGraphicsView with step selection, drag, and zoom support."""
    
    def __init__(self, scene, timeline_widget):
        super().__init__(scene)
        self.timeline_widget = timeline_widget
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_step_context_menu)
        
        # Drag state
        self.dragging_step = None
        self.dragging_audio = False
        self.dragging_audio_handle = None
        self.drag_start_x = 0
        self.drag_original_timestamp = 0
        self.drag_original_audio_offset = 0.0
        self.drag_original_audio_trim_start = 0.0
        self.drag_original_audio_trim_end = None
        
        # Clipboard for copy/paste
        self.clipboard_step = None
        
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+wheel = zoom horizontally
            delta = event.angleDelta().y()
            center_x = self.mapToScene(event.position().toPoint()).x()
            self.timeline_widget.apply_wheel_zoom(delta, center_x)
            event.accept()
        else:
            # Normal wheel = horizontal scroll
            scroll_bar = self.horizontalScrollBar()
            scroll_bar.setValue(scroll_bar.value() - event.angleDelta().y())
            event.accept()
            
    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.timeline_widget.snap_temporarily_disabled = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        self.timeline_widget.update_time_label()
        
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on a step clip
            item = self.itemAt(event.position().toPoint())
            handle_role = item.data(2) if item else None
            if handle_role in {"audio_handle_left", "audio_handle_right"}:
                self.dragging_audio_handle = handle_role
                self.drag_start_x = scene_pos.x()
                self.drag_original_audio_offset = float(getattr(self.timeline_widget.tutorial, "audio_offset", 0.0) or 0.0)
                self.drag_original_audio_trim_start = float(getattr(self.timeline_widget.tutorial, "audio_trim_start", 0.0) or 0.0)
                self.drag_original_audio_trim_end = getattr(self.timeline_widget.tutorial, "audio_trim_end", None)
            elif item and item.data(1) == "audio":
                self.dragging_audio = True
                self.drag_start_x = scene_pos.x()
                self.drag_original_audio_offset = float(getattr(self.timeline_widget.tutorial, "audio_offset", 0.0) or 0.0)
            elif item and item.data(0) is not None:
                step_idx = item.data(0)
                self.timeline_widget.selected_step_index = step_idx
                self.timeline_widget.step_selected.emit(step_idx)
                
                # Start drag
                self.dragging_step = step_idx
                self.drag_start_x = scene_pos.x()
                self.drag_original_timestamp = self.timeline_widget.tutorial.steps[step_idx].timestamp
                
                self.timeline_widget.refresh_step_items()
            else:
                # Clicked on empty area - deselect and move playhead
                self.timeline_widget.selected_step_index = -1
                self.dragging_step = None
                self.dragging_audio = False
                self.timeline_widget.refresh_step_items()
                position = self.timeline_widget.time_for_scene_x(scene_pos.x())
                self.timeline_widget.on_timeline_clicked(position)
                
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        self.timeline_widget.snap_temporarily_disabled = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if self.dragging_audio_handle:
            scene_pos = self.mapToScene(event.position().toPoint())
            delta_seconds = self.timeline_widget.snap_time(
                self.timeline_widget.time_for_scene_x(scene_pos.x()) - self.timeline_widget.time_for_scene_x(self.drag_start_x)
            )
            source_duration = self.timeline_widget.get_audio_source_duration()
            min_duration = self.timeline_widget.minimum_audio_clip_duration

            if self.dragging_audio_handle == "audio_handle_left":
                max_trim_start = (
                    float(self.drag_original_audio_trim_end) - min_duration
                    if self.drag_original_audio_trim_end is not None
                    else max(0.0, (source_duration or (self.drag_original_audio_trim_start + max(self.timeline_widget.video_duration, 1.0))) - min_duration)
                )
                new_trim_start = min(max(0.0, self.drag_original_audio_trim_start + delta_seconds), max_trim_start)
                applied_delta = new_trim_start - self.drag_original_audio_trim_start
                self.timeline_widget.tutorial.audio_trim_start = new_trim_start
                self.timeline_widget.tutorial.audio_offset = self.drag_original_audio_offset + applied_delta
            else:
                base_end = self.drag_original_audio_trim_end
                if base_end is None:
                    base_end = source_duration if source_duration is not None else (
                        self.drag_original_audio_trim_start + self.timeline_widget.get_effective_audio_duration()
                    )
                max_trim_end = source_duration if source_duration is not None else max(base_end, self.drag_original_audio_trim_start + max(self.timeline_widget.video_duration, 1.0))
                min_trim_end = float(getattr(self.timeline_widget.tutorial, "audio_trim_start", 0.0) or 0.0) + min_duration
                new_trim_end = min(max_trim_end, max(min_trim_end, float(base_end) + delta_seconds))
                self.timeline_widget.tutorial.audio_trim_end = new_trim_end

            self.timeline_widget._update_audio_item()
            self.timeline_widget.update_time_label()
            self.timeline_widget.audio_trim_preview.emit()
        elif self.dragging_audio:
            scene_pos = self.mapToScene(event.position().toPoint())
            pps = self.timeline_widget.pixels_per_second * self.timeline_widget.zoom_scale
            delta_seconds = (scene_pos.x() - self.drag_start_x) / pps
            new_offset = self.timeline_widget.snap_time(self.drag_original_audio_offset + delta_seconds)
            new_offset = max(-10.0, min(10.0, new_offset))
            self.timeline_widget.tutorial.audio_offset = new_offset
            self.timeline_widget._update_audio_item()
            self.timeline_widget.update_time_label()
            self.timeline_widget.audio_offset_preview.emit(new_offset)
        elif self.dragging_step is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            
            # Calculate new timestamp
            new_timestamp = self.timeline_widget.snap_time(self.timeline_widget.time_for_scene_x(scene_pos.x()))
            new_timestamp = max(0, new_timestamp)
            
            # Update step timestamp
            if 0 <= self.dragging_step < len(self.timeline_widget.tutorial.steps):
                self.timeline_widget.tutorial.steps[self.dragging_step].timestamp = new_timestamp
                self.timeline_widget._update_step_item(self.dragging_step)
        else:
            item = self.itemAt(event.position().toPoint())
            handle_role = item.data(2) if item else None
            if handle_role in {"audio_handle_left", "audio_handle_right"}:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif item and item.data(1) == "audio":
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        if self.dragging_audio_handle:
            self.timeline_widget.audio_trim_committed.emit()
            self.timeline_widget.rebuild_scene()
            self.dragging_audio_handle = None
        elif self.dragging_audio:
            self.timeline_widget.audio_offset_committed.emit(self.timeline_widget.tutorial.audio_offset)
            self.timeline_widget.rebuild_scene()
            self.dragging_audio = False
        elif self.dragging_step is not None:
            # Re-sort steps by timestamp after drag
            self.timeline_widget.tutorial.steps.sort(key=lambda s: s.timestamp)
            self.timeline_widget.rebuild_scene()
            
            # Emit reordered signal so Editor can refresh list
            self.timeline_widget.steps_reordered.emit()
            
            self.dragging_step = None
        self.timeline_widget.snap_temporarily_disabled = False
        self.timeline_widget.update_time_label()
        self.setCursor(Qt.CursorShape.ArrowCursor)
            
        super().mouseReleaseEvent(event)
        
    def show_step_context_menu(self, pos):
        scene_pos = self.mapToScene(pos)
        pps = self.timeline_widget.pixels_per_second * self.timeline_widget.zoom_scale
        
        menu = QMenu(self)
        
        # Check if right-clicked on a step
        item = self.itemAt(pos)
        if item and item.data(1) == "audio":
            step_idx = None
        else:
            step_idx = item.data(0) if item and item.data(0) is not None else None
        
        if step_idx is not None and 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            step = self.timeline_widget.tutorial.steps[step_idx]
            
            # Select the step
            self.timeline_widget.selected_step_index = step_idx
            self.timeline_widget.step_selected.emit(step_idx)
            self.timeline_widget.refresh_step_items()
            
            # Step info header
            menu.addAction(f"Step {step_idx + 1}: {step.description[:20]}...").setEnabled(False)
            menu.addSeparator()
            
            # Edit action - select in steps list
            edit_action = menu.addAction("Edit Properties")
            edit_action.triggered.connect(lambda: self.timeline_widget.step_selected.emit(step_idx))
            
            menu.addSeparator()
            
            # Copy
            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(lambda: self.copy_step(step_idx))
            
            # Duplicate
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(lambda: self.duplicate_step(step_idx))
            
            menu.addSeparator()
            
            # Move left/right
            if step_idx > 0:
                move_left = menu.addAction("Move Earlier")
                move_left.triggered.connect(lambda: self.move_step(step_idx, -0.5))
            
            move_right = menu.addAction("Move Later")
            move_right.triggered.connect(lambda: self.move_step(step_idx, 0.5))
            
            menu.addSeparator()
            
            # Delete
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.delete_step(step_idx))
            
        else:
            # Right-clicked on empty area
            current_position = scene_pos.x() / pps
            
            # Add new step
            add_click = menu.addAction("Add Click Step Here")
            # Add new step
            add_click = menu.addAction("Add Click Step Here")
            add_click.triggered.connect(lambda: self.timeline_widget.step_added_with_type.emit(current_position, "click"))
            
            add_keyboard = menu.addAction("Add Keyboard Step Here")
            add_keyboard = menu.addAction("Add Keyboard Step Here")
            add_keyboard.triggered.connect(lambda: self.timeline_widget.step_added_with_type.emit(current_position, "keyboard"))
            
            if self.clipboard_step:
                menu.addSeparator()
                paste_action = menu.addAction("Paste Step")
                paste_action.triggered.connect(lambda: self.paste_step(current_position))
        
        menu.exec(self.mapToGlobal(pos))
        
    def copy_step(self, step_idx):
        """Copy step to clipboard."""
        if 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            import copy
            self.clipboard_step = copy.deepcopy(self.timeline_widget.tutorial.steps[step_idx])
            print(f"Copied step {step_idx + 1}")
            
    def duplicate_step(self, step_idx):
        """Duplicate step right after the original."""
        self.timeline_widget.duplicate_step(step_idx)
            
    def paste_step(self, timestamp):
        """Paste copied step at given timestamp."""
        if self.clipboard_step:
            import copy
            new_step = copy.deepcopy(self.clipboard_step)
            new_step.timestamp = timestamp
            new_step.id = str(__import__('uuid').uuid4())
            
            self.timeline_widget.tutorial.steps.append(new_step)
            self.timeline_widget.tutorial.steps.sort(key=lambda s: s.timestamp)
            self.timeline_widget.rebuild_scene()
            self.timeline_widget.step_added.emit(timestamp)
            print(f"Pasted step at {timestamp:.2f}s")
            
    def move_step(self, step_idx, delta_seconds):
        """Move step by delta seconds."""
        if 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            step = self.timeline_widget.tutorial.steps[step_idx]
        if 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            step = self.timeline_widget.tutorial.steps[step_idx]
            step.timestamp = max(0, step.timestamp + delta_seconds)
            self.timeline_widget.tutorial.steps.sort(key=lambda s: s.timestamp)
            self.timeline_widget.rebuild_scene()
            self.timeline_widget.steps_reordered.emit()
            
    def delete_step(self, step_idx):
        """Delete step."""
        if 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            # Don't delete directly - emit signal
            # del self.timeline_widget.tutorial.steps[step_idx]
            self.timeline_widget.step_deleted.emit(step_idx)
            
    def duplicate_step(self, step_idx):
        """Duplicate the specified step."""
        if 0 <= step_idx < len(self.tutorial.steps):
            import copy
            import uuid
            
            original = self.tutorial.steps[step_idx]
            new_step = copy.deepcopy(original)
            new_step.id = str(uuid.uuid4())
            new_step.timestamp += 0.5  # Add 0.5s after original
            
            new_step.timestamp += 0.5  # Add 0.5s after original
            
            # Delegate to Editor (via signal?? No, simpler to just append here? 
            # Ideally Editor handles all structural changes. 
            # But duplicate is specific. Let's append but emit reordered?)
            # Plan says: "Remove direct append". 
            # So we should emit step_added or similar.
            # But duplicate needs to copy props. 
            # Let's keep direct append for duplicate/paste for now as partial fix?
            # No, sticking to plan: Editor should be authority.
            # But we don't have a "duplicate_step" signal.
            # Let's emit step_added_with_type? No, that creates new.
            
            # For now, let's keep duplicate HERE but ensure it emits reordered signals
            # and let Editor refresh.
            self.tutorial.steps.append(new_step)
            self.tutorial.steps.sort(key=lambda s: s.timestamp)
            
            self.update_scene()
            self.steps_reordered.emit() # Refresh editor list
            print(f"Duplicated step {step_idx + 1}")

    # add_step_at Removed - functionality moved to Editor via signals

class CollapsibleSection(QGroupBox):
    """A property section that can be collapsed while staying visible."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("sectionBody")
        self.control_height = 28
        self.label_width = 96

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 4, 0, 0)
        outer_layout.setSpacing(2)

        self.form_layout = QFormLayout(self.content_widget)
        self.form_layout.setContentsMargins(0, 6, 0, 0)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.form_layout.setHorizontalSpacing(8)
        self.form_layout.setVerticalSpacing(4)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        outer_layout.addWidget(self.content_widget)

        self.toggled.connect(self._toggle_content)
        self._toggle_content(True)
        self._apply_section_style()

    def _apply_section_style(self):
        from . import styles

        if styles.is_dark_mode():
            title_color = "#f3f6fb"
            label_color = "#93a4ba"
            body_border = "#263242"
            title_bg = "#121212"
            field_bg = "#2a2a2a"
            field_border = "#4a4f57"
            field_text = "#f3f6fb"
        else:
            title_color = "#1f2937"
            label_color = "#66758a"
            body_border = "#d9e2ec"
            title_bg = "#ffffff"
            field_bg = "#ffffff"
            field_border = "#bcc7d3"
            field_text = "#1f2937"

        self.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                margin-top: 10px;
                padding-top: 0px;
                background: transparent;
                font-weight: 700;
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: -1px;
                padding: 0 0 4px 0;
                color: {title_color};
                background: {title_bg};
            }}
            QWidget#sectionBody {{
                background: transparent;
                border: none;
                border-top: 1px solid {body_border};
                border-radius: 0px;
            }}
            QWidget#sectionBody QLabel {{
                color: {label_color};
            }}
            QWidget#sectionBody QLabel[rowLabel="true"] {{
                min-width: {self.label_width}px;
                max-width: {self.label_width}px;
                padding: 0 8px;
                border: 1px solid {body_border};
                background: {title_bg};
                border-radius: 0px;
            }}
            QWidget#sectionBody QLineEdit,
            QWidget#sectionBody QComboBox,
            QWidget#sectionBody QSpinBox,
            QWidget#sectionBody QPushButton {{
                min-height: {self.control_height}px;
                max-height: {self.control_height}px;
                color: {field_text};
                background: {field_bg};
                border: 1px solid {field_border};
                padding-top: 0px;
                padding-bottom: 0px;
                border-radius: 0px;
            }}
            QWidget#sectionBody QSpinBox {{
                font-weight: 600;
                padding-right: 28px;
            }}
            QWidget#sectionBody QSpinBox::up-button,
            QWidget#sectionBody QSpinBox::down-button {{
                width: 28px;
                min-width: 28px;
                border-left: 1px solid {field_border};
                color: {field_text};
                background: {field_bg};
                border-radius: 0px;
            }}
            QWidget#sectionBody QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                height: 14px;
                border-bottom: 1px solid {field_border};
            }}
            QWidget#sectionBody QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                height: 14px;
            }}
            QWidget#sectionBody QSpinBox::up-arrow,
            QWidget#sectionBody QSpinBox::down-arrow {{
                color: {title_color};
                width: 10px;
                height: 10px;
            }}
            QWidget#sectionBody QLineEdit,
            QWidget#sectionBody QComboBox,
            QWidget#sectionBody QSpinBox,
            QWidget#sectionBody QTextEdit,
            QWidget#sectionBody QPushButton {{
                border-radius: 0px;
            }}
            QWidget#sectionBody QTextEdit {{
                min-height: 56px;
                max-height: 56px;
                color: {field_text};
                background: {field_bg};
                border: 1px solid {field_border};
                border-radius: 0px;
            }}
        """)

    def _toggle_content(self, expanded: bool):
        self.content_widget.setVisible(expanded)

    def _normalize_field(self, field):
        if isinstance(field, QLayout):
            container = QWidget(self.content_widget)
            container.setContentsMargins(0, 0, 0, 0)
            container.setLayout(field)
            field.setContentsMargins(0, 0, 0, 0)
            if isinstance(field, QHBoxLayout):
                container.setMinimumHeight(self.control_height)
                container.setMaximumHeight(self.control_height)
            return container

        if isinstance(field, QWidget) and not isinstance(field, QTextEdit):
            field.setMinimumHeight(self.control_height)
            field.setMaximumHeight(self.control_height)
        return field

    def addRow(self, *args):
        if len(args) == 2 and isinstance(args[0], str):
            if not args[0].strip():
                self.form_layout.addRow(self._normalize_field(args[1]))
                return None
            label = QLabel(args[0], self.content_widget)
            label.setProperty("rowLabel", bool(args[0].strip()))
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setMinimumWidth(self.label_width)
            label.setMaximumWidth(self.label_width)
            label.setMinimumHeight(self.control_height)
            label.setMaximumHeight(self.control_height)
            self.form_layout.addRow(label, self._normalize_field(args[1]))
            return label
        normalized_args = list(args)
        if normalized_args:
            normalized_args[-1] = self._normalize_field(normalized_args[-1])
        self.form_layout.addRow(*normalized_args)
        return None


class PropertySpinBox(QSpinBox):
    """Spin box with explicit + / - glyphs for reliable visibility across styles."""

    def paintEvent(self, event):
        super().paintEvent(event)

        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        style = self.style()

        up_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            self,
        )
        down_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        text_color = self.palette().color(QPalette.ColorRole.Text)
        painter.setPen(text_color)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(up_rect, Qt.AlignmentFlag.AlignCenter, "+")
        painter.drawText(down_rect, Qt.AlignmentFlag.AlignCenter, "-")
        painter.end()


class DragGifPreviewWorker(QObject):
    preview_ready = Signal(int, str, object)

    def __init__(self, request_id: int, step_id: str, video_path: str, step_data: dict):
        super().__init__()
        self.request_id = request_id
        self.step_id = step_id
        self.video_path = video_path
        self.step_data = step_data
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        tutorial = Tutorial(title="Drag Preview", video_path=self.video_path, steps=[Step(**self.step_data)])
        gif_bytes = WebExporter(tutorial)._generate_drag_guide_gif_bytes(tutorial.steps[0])
        self.preview_ready.emit(self.request_id, self.step_id, gif_bytes)


class Editor(QMainWindow):
    def __init__(self, tutorial: Tutorial):
        super().__init__()
        self.tutorial = tutorial
        self.settings = Settings()
        self.video_cap = None
        self._drag_preview_movie = None
        self._drag_preview_temp_path = None
        self._drag_preview_request_id = 0
        self._drag_preview_workers = {}
        self._drag_preview_step_id = ""
        self.property_label_widgets = {}
        
        # Undo/Redo History
        self.history_stack = []  # List of tutorial state snapshots
        self.history_index = -1  # Current position in history
        self.max_history = 50    # Maximum history size
        
        self.init_ui()
        self.save_state()  # Save initial state

    def _configure_property_spinbox(self, spinbox: QSpinBox):
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        spinbox.setAccelerated(True)
        spinbox.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return spinbox

    def _configure_icon_button(self, button: QPushButton, icon: QStyle.StandardPixmap, tooltip: str):
        button.setText("")
        button.setToolTip(tooltip)
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(button.size())
        return button

    def _is_text_input_focus(self):
        focus_widget = QApplication.focusWidget()
        return isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit))

    def _normalize_keyboard_step(self, step: Step):
        if step.action_type != "keyboard":
            return

        mode = (step.keyboard_mode or "text").strip().lower()
        if mode not in {"text", "key"}:
            mode = "text"
        step.keyboard_mode = mode

        if mode == "key":
            normalized_input = (
                normalize_key_combo(step.keyboard_input)
                if "+" in (step.keyboard_input or "")
                else normalize_key_name(step.keyboard_input)
            )
            step.keyboard_input = normalized_input
            main_key = normalized_input.split("+")[-1] if normalized_input else ""
            step.keyboard_code = key_code_from_key_name(main_key) if main_key else ""
            if normalized_input:
                label = display_key_combo(normalized_input) if "+" in normalized_input else display_key_name(normalized_input)
                step.description = f"Press {label}"
            elif step.description.startswith("Press "):
                step.description = "Type text"
            return

        step.keyboard_code = ""
        if step.description.startswith("Press ") or not step.description:
            step.description = "Type text"

    def _ui_language(self) -> str:
        return self.settings.get_ui_language()

    def _tr(self, key: str) -> str:
        translations = {
            "en": {
                "properties": "Properties",
                "step_section": "Step",
                "description": "Description:",
                "instruction": "Instruction:",
                "instruction_placeholder": "Enter step-by-step instruction here...",
                "default_character": "Use default character",
                "enable_click_sound": "Enable Click Sound",
                "input_type": "Input Type:",
                "expected_input": "Expected Input:",
                "expected_input_placeholder": "Expected keyboard input",
                "space_key": "Space Key:",
                "text_style_section": "Text Style",
                "font": "Font:",
                "font_size": "Font Size:",
                "font_weight": "Font Weight:",
                "normal": "Normal",
                "bold": "Bold",
                "text_color": "Text Color:",
                "bg_color": "Bg Color:",
                "hitbox_style_section": "Hitbox Style",
                "shape": "Shape:",
                "rectangle": "Rectangle",
                "circle": "Circle",
                "line_width": "Line Width:",
                "line_style": "Line Style:",
                "line_color": "Line Color:",
                "fill_color": "Fill Color:",
                "fill_opacity": "Fill Opacity:",
                "drag_section": "Drag",
                "drag_button": "Drag Button:",
                "left": "Left",
                "middle": "Middle",
                "right": "Right",
                "min_distance": "Min Distance:",
                "auto_drag_gif": "Auto-create GIF from recorded video",
                "gif_lead": "GIF Lead:",
                "gif_tail": "GIF Tail:",
                "gif_fps": "GIF FPS:",
                "gif_size": "GIF Size:",
                "show_direction_arrow": "Show direction arrow",
                "arrow_size": "Arrow Size:",
                "preview": "Preview:",
                "drag_preview": "Drag GIF preview",
                "audio_section": "Audio",
                "input_device": "Input Device:",
                "test_mic": "Test Mic",
                "refresh_inputs": "Refresh Inputs",
                "audio_file": "Audio File:",
                "no_audio_loaded": "No audio loaded",
                "sync_offset": "Sync Offset:",
                "web_export_text_section": "Web Export Text",
                "tutorial_title": "Tutorial Title:",
                "start_subtitle": "Start Subtitle:",
                "start_button": "Start Button:",
                "completion_title": "Completion Title:",
                "completion_subtitle": "Completion Subtitle:",
                "restart_button": "Restart Button:",
                "guide_card_section": "Guide Card",
                "language": "Language:",
                "korean": "Korean",
                "english": "English",
                "default_image": "Default Image:",
                "step_card_image": "Step Card Image:",
                "no_character_image": "No character image",
                "character_size": "Character Size:",
                "card_anchor": "Card Anchor:",
                "fixed_top": "Fixed Top",
                "near_action": "Near Action",
                "card_direction": "Card Direction:",
                "auto": "Auto",
                "above": "Above",
                "below": "Below",
                "card_offset": "Card Offset:",
                "vertical_offset": "Vertical Offset:",
                "horizontal_offset": "Horizontal Offset:",
                "card_width": "Card Width:",
                "card_scale": "Card Scale:",
                "badge_size": "Badge Size:",
                "character_gap": "Character Gap:",
                "card_padding": "Card Padding:",
                "card_opacity": "Card Opacity:",
                "text_input": "Text Input",
                "key_input": "Key Input",
                "submit_step": "Submit Step",
                "insert_space": "Insert Space",
            },
            "ko": {
                "properties": "속성",
                "step_section": "단계",
                "description": "설명:",
                "instruction": "안내문:",
                "instruction_placeholder": "단계별 안내 문구를 입력하세요...",
                "default_character": "기본 캐릭터 사용",
                "enable_click_sound": "클릭 사운드 사용",
                "input_type": "입력 방식:",
                "expected_input": "입력 내용:",
                "expected_input_placeholder": "예상 키보드 입력",
                "space_key": "스페이스 키:",
                "text_style_section": "텍스트 스타일",
                "font": "글꼴:",
                "font_size": "글꼴 크기:",
                "font_weight": "글꼴 두께:",
                "normal": "보통",
                "bold": "굵게",
                "text_color": "텍스트 색상:",
                "bg_color": "배경 색상:",
                "hitbox_style_section": "히트박스 스타일",
                "shape": "도형:",
                "rectangle": "사각형",
                "circle": "원형",
                "line_width": "선 두께:",
                "line_style": "선 스타일:",
                "line_color": "선 색상:",
                "fill_color": "채우기 색상:",
                "fill_opacity": "채우기 투명도:",
                "drag_section": "드래그",
                "drag_button": "드래그 버튼:",
                "left": "왼쪽",
                "middle": "가운데",
                "right": "오른쪽",
                "min_distance": "최소 거리:",
                "auto_drag_gif": "녹화 영상으로 GIF 자동 생성",
                "gif_lead": "GIF 시작 여유:",
                "gif_tail": "GIF 종료 여유:",
                "gif_fps": "GIF FPS:",
                "gif_size": "GIF 크기:",
                "show_direction_arrow": "방향 화살표 표시",
                "arrow_size": "화살표 크기:",
                "preview": "미리보기:",
                "drag_preview": "드래그 GIF 미리보기",
                "audio_section": "오디오",
                "input_device": "입력 장치:",
                "test_mic": "마이크 테스트",
                "refresh_inputs": "장치 새로고침",
                "audio_file": "오디오 파일:",
                "no_audio_loaded": "불러온 오디오 없음",
                "sync_offset": "동기화 오프셋:",
                "web_export_text_section": "웹 내보내기 문구",
                "tutorial_title": "튜토리얼 제목:",
                "start_subtitle": "시작 부제목:",
                "start_button": "시작 버튼:",
                "completion_title": "완료 제목:",
                "completion_subtitle": "완료 부제목:",
                "restart_button": "다시 시작 버튼:",
                "guide_card_section": "가이드 카드",
                "language": "언어:",
                "korean": "한국어",
                "english": "영어",
                "default_image": "기본 이미지:",
                "step_card_image": "단계 카드 이미지:",
                "no_character_image": "캐릭터 이미지 없음",
                "character_size": "캐릭터 크기:",
                "card_anchor": "카드 기준 위치:",
                "fixed_top": "상단 고정",
                "near_action": "동작 근처",
                "card_direction": "카드 방향:",
                "auto": "자동",
                "above": "위",
                "below": "아래",
                "card_offset": "카드 간격:",
                "vertical_offset": "세로 오프셋:",
                "horizontal_offset": "가로 오프셋:",
                "card_width": "카드 너비:",
                "card_scale": "카드 배율:",
                "badge_size": "배지 크기:",
                "character_gap": "캐릭터 간격:",
                "card_padding": "카드 여백:",
                "card_opacity": "카드 투명도:",
                "text_input": "텍스트 입력",
                "key_input": "키 입력",
                "submit_step": "단계 제출",
                "insert_space": "공백 입력",
            },
        }
        language = self._ui_language()
        return translations.get(language, translations["en"]).get(key, key)

    def _register_property_label(self, key: str, label_widget):
        if label_widget is not None:
            self.property_label_widgets[key] = label_widget
        return label_widget

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]):
        current_data = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for text, data in items:
            combo.addItem(text, data)
        new_index = combo.findData(current_data)
        combo.setCurrentIndex(new_index if new_index >= 0 else 0)
        combo.blockSignals(False)

    def retranslate_properties_panel(self):
        self.props_dock.setWindowTitle(self._tr("properties"))
        section_titles = {
            "step": "step_section",
            "text_style": "text_style_section",
            "hitbox_style": "hitbox_style_section",
            "drag": "drag_section",
            "audio": "audio_section",
            "web_export_text": "web_export_text_section",
            "guide_card": "guide_card_section",
        }
        for key, title_key in section_titles.items():
            if key in self.property_sections:
                translated = self._tr(title_key)
                self.property_sections[key]["title"] = translated
                self.property_sections[key]["widget"].setTitle(translated)

        for key, widget in self.property_label_widgets.items():
            widget.setText(self._tr(key))

        if hasattr(self, "instruction_input"):
            self.instruction_input.setPlaceholderText(self._tr("instruction_placeholder"))
        if hasattr(self, "text_content"):
            self.text_content.setPlaceholderText(self._tr("expected_input_placeholder"))
        if hasattr(self, "chk_sound"):
            self.chk_sound.setText(self._tr("enable_click_sound"))
        if hasattr(self, "auto_drag_gif_checkbox"):
            self.auto_drag_gif_checkbox.setText(self._tr("auto_drag_gif"))
        if hasattr(self, "drag_arrow_enabled_checkbox"):
            self.drag_arrow_enabled_checkbox.setText(self._tr("show_direction_arrow"))
        if hasattr(self, "btn_test_audio_input"):
            self.btn_test_audio_input.setText(self._tr("test_mic"))
        if hasattr(self, "btn_refresh_audio_inputs"):
            self.btn_refresh_audio_inputs.setText(self._tr("refresh_inputs"))
        if hasattr(self, "keyboard_mode_combo"):
            self._set_combo_items(self.keyboard_mode_combo, [
                (self._tr("text_input"), "text"),
                (self._tr("key_input"), "key"),
            ])
        if hasattr(self, "keyboard_space_behavior_combo"):
            self._set_combo_items(self.keyboard_space_behavior_combo, [
                (self._tr("submit_step"), "submit_step"),
                (self._tr("insert_space"), "insert_space"),
            ])
        if hasattr(self, "font_weight_combo"):
            current_text = self.font_weight_combo.currentText()
            target_data = "Bold" if current_text in {"Bold", "굵게"} else "Normal"
            self._set_combo_items(self.font_weight_combo, [
                (self._tr("normal"), "Normal"),
                (self._tr("bold"), "Bold"),
            ])
            self.font_weight_combo.setCurrentIndex(self.font_weight_combo.findData(target_data))
        if hasattr(self, "drag_button_combo"):
            self._set_combo_items(self.drag_button_combo, [
                (self._tr("left"), "left"),
                (self._tr("middle"), "middle"),
                (self._tr("right"), "right"),
            ])
        if hasattr(self, "guide_language_combo"):
            self._set_combo_items(self.guide_language_combo, [
                (self._tr("korean"), "ko"),
                (self._tr("english"), "en"),
            ])
        if hasattr(self, "guide_card_anchor_combo"):
            self._set_combo_items(self.guide_card_anchor_combo, [
                (self._tr("fixed_top"), "top_fixed"),
                (self._tr("near_action"), "follow_action"),
            ])
        if hasattr(self, "guide_card_direction_combo"):
            self._set_combo_items(self.guide_card_direction_combo, [
                (self._tr("auto"), "auto"),
                (self._tr("right"), "right"),
                (self._tr("left"), "left"),
                (self._tr("above"), "top"),
                (self._tr("below"), "bottom"),
            ])

    def init_ui(self):
        # ==================== Central Widget (Canvas) ====================
        # Canvas directly as central widget - zoom controls will be overlay
        self.canvas = ZoomableImageCanvas()
        self.setCentralWidget(self.canvas)
        
        # Zoom control bar - floating overlay at bottom of canvas
        self.zoom_controls = ZoomControlBar(self.canvas, self.canvas)
        self.zoom_controls.move(10, 10)  # Will be repositioned in resizeEvent
        self.zoom_controls.raise_()
        
        # Dock features
        dock_features = QDockWidget.DockWidgetFeature.DockWidgetMovable | \
                       QDockWidget.DockWidgetFeature.DockWidgetFloatable | \
                       QDockWidget.DockWidgetFeature.DockWidgetClosable
        
        # ==================== Steps Panel (Left Dock) ====================
        self.steps_dock = QDockWidget("Steps", self)
        self.steps_dock.setFeatures(dock_features)
        
        steps_widget = QWidget()
        steps_layout = QVBoxLayout(steps_widget)
        
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_import_images = QPushButton("Import Images")
        self.btn_import_images.clicked.connect(self.import_images)
        self.btn_import_images.setStyleSheet("QPushButton { background: #2E7D32; color: white; border: none; padding: 5px; border-radius: 4px; } QPushButton:hover { background: #256628; }")
        
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.clicked.connect(self.duplicate_current_step)
        self.btn_duplicate.setStyleSheet("QPushButton { background: #0078D4; color: white; border: none; padding: 5px; border-radius: 4px; } QPushButton:hover { background: #106EBE; }")
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_current_step)
        self.btn_delete.setStyleSheet("QPushButton { background: #D93025; color: white; border: none; padding: 5px; border-radius: 4px; } QPushButton:hover { background: #C5221F; }")
        
        btn_layout.addWidget(self.btn_import_images)
        btn_layout.addWidget(self.btn_duplicate)
        btn_layout.addWidget(self.btn_delete)
        steps_layout.addLayout(btn_layout)

        self.step_list = QListWidget()
        self.step_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # Ctrl/Shift multi-select
        self.step_list.currentRowChanged.connect(self.load_step)
        self.step_list.itemSelectionChanged.connect(self.on_selection_changed)
        steps_layout.addWidget(self.step_list)
        
        # Video Frame mode is default (no toggle needed)
        self.view_mode = "video"
        
        self.steps_dock.setWidget(steps_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.steps_dock)
        
        # Set corners so Bottom Dock (Timeline) takes full width
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        
        # ==================== Properties Panel (Right Dock) ====================
        self.props_dock = QDockWidget("Properties", self)
        self.props_dock.setFeatures(dock_features)
        
        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_widget = QWidget()
        self.props_container_layout = QVBoxLayout(props_widget)
        self.props_container_layout.setContentsMargins(6, 6, 6, 6)
        self.props_container_layout.setSpacing(6)

        self.property_sections = {}
        self.property_section_visibility = {}

        step_section = self._create_property_section("step", "Step")
        self.desc_input = QLineEdit()
        self.desc_input.setFixedHeight(step_section.control_height)
        self.desc_input.textChanged.connect(self.update_desc_preview)
        self.desc_input.editingFinished.connect(self.save_state)
        self._register_property_label("description", step_section.addRow("Description:", self.desc_input))

        self.instruction_input = QTextEdit()
        self.instruction_input.setPlaceholderText("Enter step-by-step instruction here...")
        self.instruction_input.setMaximumHeight(56)
        self.instruction_input.textChanged.connect(self.update_instruction_preview)
        self.instruction_input.setTabChangesFocus(True)
        self._register_property_label("instruction", step_section.addRow("Instruction:", self.instruction_input))

        self.step_guide_image_layout = QHBoxLayout()
        self.step_guide_image_label = QLabel(self._tr("default_character"))
        self.step_guide_image_label.setStyleSheet("color: #666; font-style: italic;")
        self.step_guide_image_layout.addWidget(self.step_guide_image_label, 1)
        self.step_guide_image_browse_btn = QPushButton()
        self.step_guide_image_browse_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.step_guide_image_browse_btn,
            QStyle.StandardPixmap.SP_ArrowUp,
            "Import step guide image",
        )
        self.step_guide_image_browse_btn.clicked.connect(self.import_step_guide_image)
        self.step_guide_image_layout.addWidget(self.step_guide_image_browse_btn)
        self.remove_step_guide_image_btn = QPushButton()
        self.remove_step_guide_image_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.remove_step_guide_image_btn,
            QStyle.StandardPixmap.SP_TitleBarCloseButton,
            "Remove step guide image",
        )
        self.remove_step_guide_image_btn.clicked.connect(self.remove_step_guide_image)
        self.remove_step_guide_image_btn.setEnabled(False)
        self.step_guide_image_layout.addWidget(self.remove_step_guide_image_btn)

        self.chk_sound = QCheckBox("Enable Click Sound")
        self.chk_sound.toggled.connect(self.update_sound)
        step_section.addRow("", self.chk_sound)

        from PySide6.QtWidgets import QSpinBox
        self.keyboard_mode_combo = QComboBox()
        self.keyboard_mode_combo.addItem("Text Input", "text")
        self.keyboard_mode_combo.addItem("Key Input", "key")
        self.keyboard_mode_combo.currentIndexChanged.connect(self.update_keyboard_mode)
        self._register_property_label("input_type", step_section.addRow("Input Type:", self.keyboard_mode_combo))

        self.text_content = QLineEdit()
        self.text_content.setPlaceholderText("Expected keyboard input")
        self.text_content.textChanged.connect(self.update_keyboard_input_preview)
        self.text_content.editingFinished.connect(self.save_state)
        self._register_property_label("expected_input", step_section.addRow("Expected Input:", self.text_content))

        self.keyboard_space_behavior_combo = QComboBox()
        self.keyboard_space_behavior_combo.addItem("Submit Step", "submit_step")
        self.keyboard_space_behavior_combo.addItem("Insert Space", "insert_space")
        self.keyboard_space_behavior_combo.currentIndexChanged.connect(self.update_keyboard_space_behavior)
        self._register_property_label("space_key", step_section.addRow("Space Key:", self.keyboard_space_behavior_combo))

        text_style_section = self._create_property_section("text_style", "Text Style")
        from PySide6.QtGui import QFontDatabase
        self.font_family_combo = QComboBox()
        font_families = QFontDatabase.families()
        self.font_family_combo.addItems(font_families)
        arial_idx = self.font_family_combo.findText("Arial")
        if arial_idx >= 0:
            self.font_family_combo.setCurrentIndex(arial_idx)
        self.font_family_combo.currentTextChanged.connect(self.update_text_style_preview)
        self._register_property_label("font", text_style_section.addRow("Font:", self.font_family_combo))

        self.font_size_spinbox = PropertySpinBox()
        self._configure_property_spinbox(self.font_size_spinbox)
        self.font_size_spinbox.setMinimum(8)
        self.font_size_spinbox.setMaximum(200)
        self.font_size_spinbox.setValue(24)
        self.font_size_spinbox.setSuffix(" pt")
        self.font_size_spinbox.valueChanged.connect(self.update_text_style_preview)
        self._register_property_label("font_size", text_style_section.addRow("Font Size:", self.font_size_spinbox))

        self.font_weight_combo = QComboBox()
        self.font_weight_combo.addItems(["Normal", "Bold"])
        self.font_weight_combo.currentTextChanged.connect(self.update_text_style_preview)
        self._register_property_label("font_weight", text_style_section.addRow("Font Weight:", self.font_weight_combo))

        text_color_layout = QHBoxLayout()
        self.text_color_input = QLineEdit()
        self.text_color_input.setPlaceholderText("#FFFFFF")
        self.text_color_input.textChanged.connect(self.update_text_style_preview)
        self.text_color_input.editingFinished.connect(self.save_state)
        self.text_color_preview = QLabel()
        self.text_color_preview.setFixedSize(18, 18)
        self.text_color_preview.setStyleSheet("background: #FFFFFF; border: 1px solid #555; border-radius: 3px;")
        self.text_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.text_color_preview.mousePressEvent = lambda e: self.pick_text_color()
        text_color_layout.addWidget(self.text_color_input)
        text_color_layout.addWidget(self.text_color_preview)
        self._register_property_label("text_color", text_style_section.addRow("Text Color:", text_color_layout))

        bg_color_layout = QHBoxLayout()
        self.bg_color_input = QLineEdit()
        self.bg_color_input.setPlaceholderText("#000000")
        self.bg_color_input.textChanged.connect(self.update_text_style_preview)
        self.bg_color_input.editingFinished.connect(self.save_state)
        self.bg_color_preview = QLabel()
        self.bg_color_preview.setFixedSize(18, 18)
        self.bg_color_preview.setStyleSheet("background: #000000; border: 1px solid #555; border-radius: 3px;")
        self.bg_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_color_preview.mousePressEvent = lambda e: self.pick_bg_color()
        bg_color_layout.addWidget(self.bg_color_input)
        bg_color_layout.addWidget(self.bg_color_preview)
        self._register_property_label("bg_color", text_style_section.addRow("Bg Color:", bg_color_layout))

        hitbox_section = self._create_property_section("hitbox_style", "Hitbox Style")
        self.shape_group = QButtonGroup(self)
        self.radio_rect = QRadioButton("Rectangle")
        self.radio_circle = QRadioButton("Circle")
        self.shape_group.addButton(self.radio_rect)
        self.shape_group.addButton(self.radio_circle)
        shape_layout = QHBoxLayout()
        shape_layout.setContentsMargins(0, 0, 0, 0)
        shape_layout.setSpacing(8)
        shape_layout.addWidget(self.radio_rect)
        shape_layout.addWidget(self.radio_circle)
        shape_layout.addStretch()
        self._register_property_label("shape", hitbox_section.addRow("Shape:", shape_layout))
        self.radio_rect.toggled.connect(self.update_shape)
        self.radio_circle.toggled.connect(self.update_shape)

        hitbox_width_layout = QHBoxLayout()
        hitbox_width_layout.setSpacing(6)
        self.hitbox_line_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.hitbox_line_width_slider.setMinimum(1)
        self.hitbox_line_width_slider.setMaximum(10)
        self.hitbox_line_width_slider.setValue(2)
        self.hitbox_line_width_slider.valueChanged.connect(self.update_hitbox_line_width)
        self.hitbox_line_width_label = QLabel("2")
        self.hitbox_line_width_label.setFixedWidth(22)
        hitbox_width_layout.addWidget(self.hitbox_line_width_slider)
        hitbox_width_layout.addWidget(self.hitbox_line_width_label)
        self._register_property_label("line_width", hitbox_section.addRow("Line Width:", hitbox_width_layout))

        self.hitbox_line_style_combo = QComboBox()
        self.hitbox_line_style_combo.addItems(["solid", "dashed", "dotted"])
        self.hitbox_line_style_combo.currentTextChanged.connect(self.update_hitbox_line_style)
        self._register_property_label("line_style", hitbox_section.addRow("Line Style:", self.hitbox_line_style_combo))

        line_color_layout = QHBoxLayout()
        self.hitbox_line_color_input = QLineEdit()
        self.hitbox_line_color_input.setPlaceholderText("#FF0000")
        self.hitbox_line_color_input.textChanged.connect(self.update_hitbox_line_color)
        self.hitbox_line_color_input.editingFinished.connect(self.save_state)
        self.hitbox_line_color_preview = QLabel()
        self.hitbox_line_color_preview.setFixedSize(18, 18)
        self.hitbox_line_color_preview.setStyleSheet("background: #FF0000; border: 1px solid #555; border-radius: 3px;")
        self.hitbox_line_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hitbox_line_color_preview.mousePressEvent = lambda e: self.pick_hitbox_line_color()
        line_color_layout.addWidget(self.hitbox_line_color_input)
        line_color_layout.addWidget(self.hitbox_line_color_preview)
        self._register_property_label("line_color", hitbox_section.addRow("Line Color:", line_color_layout))

        fill_color_layout = QHBoxLayout()
        self.hitbox_fill_color_input = QLineEdit()
        self.hitbox_fill_color_input.setPlaceholderText("#FF0000")
        self.hitbox_fill_color_input.textChanged.connect(self.update_hitbox_fill_color)
        self.hitbox_fill_color_input.editingFinished.connect(self.save_state)
        self.hitbox_fill_color_preview = QLabel()
        self.hitbox_fill_color_preview.setFixedSize(18, 18)
        self.hitbox_fill_color_preview.setStyleSheet("background: rgba(255, 0, 0, 0.2); border: 1px solid #555; border-radius: 3px;")
        self.hitbox_fill_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hitbox_fill_color_preview.mousePressEvent = lambda e: self.pick_hitbox_fill_color()
        fill_color_layout.addWidget(self.hitbox_fill_color_input)
        fill_color_layout.addWidget(self.hitbox_fill_color_preview)
        self._register_property_label("fill_color", hitbox_section.addRow("Fill Color:", fill_color_layout))

        fill_opacity_layout = QHBoxLayout()
        fill_opacity_layout.setSpacing(6)
        self.hitbox_fill_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.hitbox_fill_opacity_slider.setMinimum(0)
        self.hitbox_fill_opacity_slider.setMaximum(100)
        self.hitbox_fill_opacity_slider.setValue(20)
        self.hitbox_fill_opacity_slider.valueChanged.connect(self.update_hitbox_fill_opacity)
        self.hitbox_fill_opacity_label = QLabel("20%")
        self.hitbox_fill_opacity_label.setFixedWidth(36)
        fill_opacity_layout.addWidget(self.hitbox_fill_opacity_slider)
        fill_opacity_layout.addWidget(self.hitbox_fill_opacity_label)
        self._register_property_label("fill_opacity", hitbox_section.addRow("Fill Opacity:", fill_opacity_layout))

        drag_section = self._create_property_section("drag", "Drag")
        self.drag_button_combo = QComboBox()
        self.drag_button_combo.addItem("Left", "left")
        self.drag_button_combo.addItem("Middle", "middle")
        self.drag_button_combo.addItem("Right", "right")
        self.drag_button_combo.currentIndexChanged.connect(self.update_drag_button)
        self._register_property_label("drag_button", drag_section.addRow("Drag Button:", self.drag_button_combo))

        self.drag_min_distance_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_min_distance_spin)
        self.drag_min_distance_spin.setRange(1, 500)
        self.drag_min_distance_spin.setSingleStep(1)
        self.drag_min_distance_spin.setSuffix(" px")
        self.drag_min_distance_spin.valueChanged.connect(self.update_drag_min_distance)
        self._register_property_label("min_distance", drag_section.addRow("Min Distance:", self.drag_min_distance_spin))

        self.auto_drag_gif_checkbox = QCheckBox("Auto-create GIF from recorded video")
        self.auto_drag_gif_checkbox.toggled.connect(self.update_auto_drag_gif_enabled)
        drag_section.addRow("", self.auto_drag_gif_checkbox)

        self.drag_gif_lead_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_gif_lead_spin)
        self.drag_gif_lead_spin.setRange(0, 500)
        self.drag_gif_lead_spin.setSingleStep(5)
        self.drag_gif_lead_spin.setSuffix(" ms")
        self.drag_gif_lead_spin.valueChanged.connect(self.update_drag_gif_timing)
        self._register_property_label("gif_lead", drag_section.addRow("GIF Lead:", self.drag_gif_lead_spin))

        self.drag_gif_tail_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_gif_tail_spin)
        self.drag_gif_tail_spin.setRange(0, 500)
        self.drag_gif_tail_spin.setSingleStep(5)
        self.drag_gif_tail_spin.setSuffix(" ms")
        self.drag_gif_tail_spin.valueChanged.connect(self.update_drag_gif_timing)
        self._register_property_label("gif_tail", drag_section.addRow("GIF Tail:", self.drag_gif_tail_spin))

        self.drag_gif_fps_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_gif_fps_spin)
        self.drag_gif_fps_spin.setRange(1, 24)
        self.drag_gif_fps_spin.setSingleStep(1)
        self.drag_gif_fps_spin.setSuffix(" fps")
        self.drag_gif_fps_spin.valueChanged.connect(self.update_drag_gif_fps)
        self._register_property_label("gif_fps", drag_section.addRow("GIF FPS:", self.drag_gif_fps_spin))

        self.drag_gif_size_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_gif_size_spin)
        self.drag_gif_size_spin.setRange(140, 520)
        self.drag_gif_size_spin.setSingleStep(4)
        self.drag_gif_size_spin.setSuffix(" px")
        self.drag_gif_size_spin.valueChanged.connect(self.update_drag_gif_size)
        self._register_property_label("gif_size", drag_section.addRow("GIF Size:", self.drag_gif_size_spin))

        self.drag_arrow_enabled_checkbox = QCheckBox("Show direction arrow")
        self.drag_arrow_enabled_checkbox.toggled.connect(self.update_drag_direction_arrow_enabled)
        drag_section.addRow("", self.drag_arrow_enabled_checkbox)

        self.drag_arrow_size_spin = PropertySpinBox()
        self._configure_property_spinbox(self.drag_arrow_size_spin)
        self.drag_arrow_size_spin.setRange(10, 40)
        self.drag_arrow_size_spin.setSingleStep(1)
        self.drag_arrow_size_spin.setSuffix(" px")
        self.drag_arrow_size_spin.valueChanged.connect(self.update_drag_direction_arrow_size)
        self._register_property_label("arrow_size", drag_section.addRow("Arrow Size:", self.drag_arrow_size_spin))

        self.drag_gif_preview = QLabel(self._tr("drag_preview"))
        self.drag_gif_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_gif_preview.setMinimumHeight(120)
        self.drag_gif_preview.setStyleSheet("border: 1px solid #444; background: #111; color: #888;")
        self._register_property_label("preview", drag_section.addRow("Preview:", self.drag_gif_preview))

        audio_section = self._create_property_section("audio", "Audio")
        audio_input_layout = QHBoxLayout()
        self.audio_input_combo = QComboBox()
        self.audio_input_combo.currentIndexChanged.connect(self.update_audio_input_selection)
        audio_input_layout.addWidget(self.audio_input_combo, 1)
        self.btn_test_audio_input = QPushButton("Test Mic")
        self.btn_test_audio_input.clicked.connect(self.test_audio_input)
        audio_input_layout.addWidget(self.btn_test_audio_input)
        self.btn_refresh_audio_inputs = QPushButton("Refresh Inputs")
        self.btn_refresh_audio_inputs.clicked.connect(self.refresh_audio_inputs)
        audio_input_layout.addWidget(self.btn_refresh_audio_inputs)
        self._register_property_label("input_device", audio_section.addRow("Input Device:", audio_input_layout))

        audio_file_layout = QHBoxLayout()
        self.audio_file_label = QLabel(self._tr("no_audio_loaded"))
        self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
        audio_file_layout.addWidget(self.audio_file_label, 1)

        self.import_audio_btn = QPushButton()
        self.import_audio_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.import_audio_btn,
            QStyle.StandardPixmap.SP_ArrowUp,
            "Import Audio File",
        )
        self.import_audio_btn.clicked.connect(self.import_audio)
        audio_file_layout.addWidget(self.import_audio_btn)

        self.remove_audio_btn = QPushButton()
        self.remove_audio_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.remove_audio_btn,
            QStyle.StandardPixmap.SP_TitleBarCloseButton,
            "Remove Audio",
        )
        self.remove_audio_btn.clicked.connect(self.remove_audio)
        self.remove_audio_btn.setEnabled(False)
        audio_file_layout.addWidget(self.remove_audio_btn)
        self._register_property_label("audio_file", audio_section.addRow("Audio File:", audio_file_layout))

        offset_layout = QHBoxLayout()
        offset_layout.setSpacing(6)
        self.audio_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_offset_slider.setMinimum(-100)
        self.audio_offset_slider.setMaximum(100)
        self.audio_offset_slider.setValue(0)
        self.audio_offset_slider.valueChanged.connect(self.update_audio_offset)
        self.audio_offset_label = QLabel("0.0s")
        self.audio_offset_label.setFixedWidth(40)
        offset_layout.addWidget(self.audio_offset_slider)
        offset_layout.addWidget(self.audio_offset_label)
        self._register_property_label("sync_offset", audio_section.addRow("Sync Offset:", offset_layout))

        export_text_section = self._create_property_section("web_export_text", "Web Export Text")
        self.tutorial_title_input = QLineEdit()
        self.tutorial_title_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("tutorial_title", export_text_section.addRow("Tutorial Title:", self.tutorial_title_input))

        self.start_subtitle_input = QLineEdit()
        self.start_subtitle_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("start_subtitle", export_text_section.addRow("Start Subtitle:", self.start_subtitle_input))

        self.start_button_input = QLineEdit()
        self.start_button_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("start_button", export_text_section.addRow("Start Button:", self.start_button_input))

        self.completion_title_input = QLineEdit()
        self.completion_title_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("completion_title", export_text_section.addRow("Completion Title:", self.completion_title_input))

        self.completion_subtitle_input = QLineEdit()
        self.completion_subtitle_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("completion_subtitle", export_text_section.addRow("Completion Subtitle:", self.completion_subtitle_input))

        self.restart_button_input = QLineEdit()
        self.restart_button_input.editingFinished.connect(self.update_export_text_fields)
        self._register_property_label("restart_button", export_text_section.addRow("Restart Button:", self.restart_button_input))

        guide_card_section = self._create_property_section("guide_card", "Guide Card")

        self.guide_language_combo = QComboBox()
        self.guide_language_combo.addItem("Korean", "ko")
        self.guide_language_combo.addItem("English", "en")
        self.guide_language_combo.currentIndexChanged.connect(self.update_export_text_fields)
        self._register_property_label("language", guide_card_section.addRow("Language:", self.guide_language_combo))

        guide_character_layout = QHBoxLayout()
        self.guide_character_label = QLabel(self._tr("no_character_image"))
        self.guide_character_label.setStyleSheet("color: #666; font-style: italic;")
        guide_character_layout.addWidget(self.guide_character_label, 1)
        self.guide_character_browse_btn = QPushButton()
        self.guide_character_browse_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.guide_character_browse_btn,
            QStyle.StandardPixmap.SP_ArrowUp,
            "Import guide character image",
        )
        self.guide_character_browse_btn.clicked.connect(self.import_guide_character_image)
        guide_character_layout.addWidget(self.guide_character_browse_btn)
        self.remove_guide_character_btn = QPushButton()
        self.remove_guide_character_btn.setFixedSize(28, 28)
        self._configure_icon_button(
            self.remove_guide_character_btn,
            QStyle.StandardPixmap.SP_TitleBarCloseButton,
            "Remove character image",
        )
        self.remove_guide_character_btn.clicked.connect(self.remove_guide_character_image)
        self.remove_guide_character_btn.setEnabled(False)
        guide_character_layout.addWidget(self.remove_guide_character_btn)
        self._register_property_label("default_image", guide_card_section.addRow("Default Image:", guide_character_layout))
        self._register_property_label("step_card_image", guide_card_section.addRow("Step Card Image:", self.step_guide_image_layout))

        self.guide_character_size_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_character_size_spin)
        self.guide_character_size_spin.setRange(48, 320)
        self.guide_character_size_spin.setSingleStep(1)
        self.guide_character_size_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("character_size", guide_card_section.addRow("Character Size:", self.guide_character_size_spin))

        self.guide_card_anchor_combo = QComboBox()
        self.guide_card_anchor_combo.addItem("Fixed Top", "top_fixed")
        self.guide_card_anchor_combo.addItem("Near Action", "follow_action")
        self.guide_card_anchor_combo.currentIndexChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_anchor", guide_card_section.addRow("Card Anchor:", self.guide_card_anchor_combo))

        self.guide_card_direction_combo = QComboBox()
        self.guide_card_direction_combo.addItem("Auto", "auto")
        self.guide_card_direction_combo.addItem("Right", "right")
        self.guide_card_direction_combo.addItem("Left", "left")
        self.guide_card_direction_combo.addItem("Above", "top")
        self.guide_card_direction_combo.addItem("Below", "bottom")
        self.guide_card_direction_combo.currentIndexChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_direction", guide_card_section.addRow("Card Direction:", self.guide_card_direction_combo))

        self.guide_card_offset_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_offset_spin)
        self.guide_card_offset_spin.setRange(0, 120)
        self.guide_card_offset_spin.setSingleStep(1)
        self.guide_card_offset_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_offset", guide_card_section.addRow("Card Offset:", self.guide_card_offset_spin))

        self.guide_card_top_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_top_spin)
        self.guide_card_top_spin.setRange(-200, 200)
        self.guide_card_top_spin.setSingleStep(1)
        self.guide_card_top_spin.setSuffix(" px")
        self.guide_card_top_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("vertical_offset", guide_card_section.addRow("Vertical Offset:", self.guide_card_top_spin))

        self.guide_card_left_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_left_spin)
        self.guide_card_left_spin.setRange(-400, 400)
        self.guide_card_left_spin.setSingleStep(1)
        self.guide_card_left_spin.setSuffix(" px")
        self.guide_card_left_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("horizontal_offset", guide_card_section.addRow("Horizontal Offset:", self.guide_card_left_spin))

        self.guide_card_width_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_width_spin)
        self.guide_card_width_spin.setRange(280, 1200)
        self.guide_card_width_spin.setSingleStep(4)
        self.guide_card_width_spin.setSuffix(" px")
        self.guide_card_width_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_width", guide_card_section.addRow("Card Width:", self.guide_card_width_spin))

        self.guide_card_scale_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_scale_spin)
        self.guide_card_scale_spin.setRange(50, 200)
        self.guide_card_scale_spin.setSingleStep(5)
        self.guide_card_scale_spin.setSuffix("%")
        self.guide_card_scale_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_scale", guide_card_section.addRow("Card Scale:", self.guide_card_scale_spin))

        self.guide_step_badge_size_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_step_badge_size_spin)
        self.guide_step_badge_size_spin.setRange(40, 180)
        self.guide_step_badge_size_spin.setSingleStep(1)
        self.guide_step_badge_size_spin.setSuffix(" px")
        self.guide_step_badge_size_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("badge_size", guide_card_section.addRow("Badge Size:", self.guide_step_badge_size_spin))

        self.guide_card_gap_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_gap_spin)
        self.guide_card_gap_spin.setRange(0, 80)
        self.guide_card_gap_spin.setSingleStep(1)
        self.guide_card_gap_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("character_gap", guide_card_section.addRow("Character Gap:", self.guide_card_gap_spin))

        self.guide_card_padding_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_padding_spin)
        self.guide_card_padding_spin.setRange(10, 48)
        self.guide_card_padding_spin.setSingleStep(1)
        self.guide_card_padding_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_padding", guide_card_section.addRow("Card Padding:", self.guide_card_padding_spin))

        self.guide_card_opacity_spin = PropertySpinBox()
        self._configure_property_spinbox(self.guide_card_opacity_spin)
        self.guide_card_opacity_spin.setRange(0, 100)
        self.guide_card_opacity_spin.setSingleStep(1)
        self.guide_card_opacity_spin.setSuffix("%")
        self.guide_card_opacity_spin.valueChanged.connect(self.update_export_text_fields)
        self._register_property_label("card_opacity", guide_card_section.addRow("Card Opacity:", self.guide_card_opacity_spin))

        self.props_container_layout.addStretch()
        props_scroll.setWidget(props_widget)
        self.props_dock.setWidget(props_scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_dock)
        self.retranslate_properties_panel()
        
        # ==================== Timeline Panel (Bottom Dock) ====================
        self.timeline_dock = QDockWidget("Timeline", self)
        self.timeline_dock.setFeatures(dock_features)
        self.timeline_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        
        self.timeline = TimelineWidget()
        self.timeline.position_changed.connect(self.on_timeline_position_changed)
        # Connect sync signals
        self.timeline.step_selected.connect(self.select_step)
        self.timeline.step_added.connect(self.on_add_step)
        self.timeline.step_added_with_type.connect(self.on_add_step) # Handle both
        self.timeline.step_deleted.connect(self.on_delete_step)
        self.timeline.steps_reordered.connect(self.on_steps_reordered)
        self.timeline.split_requested.connect(self.split_at_playhead)
        self.timeline.delete_gap_requested.connect(self.delete_selected_range)
        self.timeline.audio_offset_preview.connect(self.preview_audio_offset_from_timeline)
        self.timeline.audio_offset_committed.connect(self.commit_audio_offset_from_timeline)
        self.timeline.audio_trim_preview.connect(self.preview_audio_trim_from_timeline)
        self.timeline.audio_trim_committed.connect(self.commit_audio_trim_from_timeline)
        
        self.timeline_dock.setWidget(self.timeline)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.timeline_dock)

        self.refresh()

    def duplicate_current_step(self):
        """Duplicate all selected steps."""
        selected = self.get_selected_indices()
        if not selected:
            return
        
        import copy
        import uuid
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                original = self.tutorial.steps[idx]
                new_step = copy.deepcopy(original)
                new_step.id = str(uuid.uuid4())
                new_step.timestamp += 0.5
                self.tutorial.steps.append(new_step)
        
        self.tutorial.steps.sort(key=lambda s: s.timestamp)
        self.refresh()
        self.timeline.set_tutorial(self.tutorial)
        self.save_state()
            
    def delete_current_step(self):
        """Delete all selected steps."""
        selected = sorted(self.get_selected_indices(), reverse=True)  # Delete from end to preserve indices
        if not selected:
            return
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                del self.tutorial.steps[idx]
        
        self.refresh()
        self.timeline.set_tutorial(self.tutorial)
        self.save_state()

    def get_selected_indices(self):
        """Get list of selected step indices."""
        return [self.step_list.row(item) for item in self.step_list.selectedItems()]

    def set_tutorial(self, tutorial: Tutorial):
        self.tutorial = tutorial
        self.history_stack = []
        self.history_index = -1
        self.timeline.set_tutorial(tutorial)
        self._sync_audio_ui()
        self.refresh()
        self.save_state()

    def import_images(self):
        image_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Screenshots",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not image_paths:
            return

        has_existing_content = bool(
            self.tutorial.steps or
            (self.tutorial.video_path and os.path.exists(self.tutorial.video_path)) or
            self.tutorial.audio_path
        )
        if has_existing_content:
            result = QMessageBox.question(
                self,
                "Replace Current Tutorial?",
                "Importing screenshots will replace the current steps, video, and audio for this tutorial. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        imported_count = self.import_image_sequence(image_paths)
        if imported_count:
            QMessageBox.information(
                self,
                "Images Imported",
                f"Imported {imported_count} screenshots as tutorial steps.",
            )

    def import_image_sequence(self, image_paths):
        normalized_paths = []
        for path in image_paths:
            if path and os.path.exists(path):
                normalized_paths.append(os.path.abspath(path))

        if not normalized_paths:
            return 0

        if self.video_cap is not None:
            self.video_cap.release()
            self.video_cap = None

        self.tutorial.steps = []
        self.tutorial.video_path = None
        self.tutorial.audio_path = None
        self.tutorial.audio_offset = 0.0
        self.tutorial.audio_trim_start = 0.0
        self.tutorial.audio_trim_end = None

        imported_steps = []
        for index, image_path in enumerate(normalized_paths):
            image = QImage(image_path)
            image_width = image.width() if not image.isNull() else 0
            image_height = image.height() if not image.isNull() else 0

            hitbox_width = max(50, min(160, image_width // 4)) if image_width > 0 else 120
            hitbox_height = max(50, min(100, image_height // 5)) if image_height > 0 else 80
            hitbox_x = max(0, (image_width - hitbox_width) // 2) if image_width > 0 else 100
            hitbox_y = max(0, (image_height - hitbox_height) // 2) if image_height > 0 else 100

            step_name = os.path.splitext(os.path.basename(image_path))[0].replace("_", " ").replace("-", " ").strip()
            description = step_name or f"Step {index + 1}"

            imported_steps.append(
                Step(
                    image_path=image_path,
                    action_type="click",
                    click_button="left",
                    x=hitbox_x,
                    y=hitbox_y,
                    width=hitbox_width,
                    height=hitbox_height,
                    description=description,
                    instruction="Click the highlighted area",
                    timestamp=float(index),
                )
            )

        self.tutorial.steps = imported_steps
        self.view_mode = "screenshot"
        self.timeline.current_position = 0.0
        self.timeline.set_tutorial(self.tutorial)
        self._sync_audio_ui()
        self.refresh()
        if self.tutorial.steps:
            self.set_current_step(0)
        self.save_state()
        return len(imported_steps)

    def split_at_playhead(self):
        """Duplicate a nearby step at the current playhead to create an edit split point."""
        import copy
        import uuid

        if not self.tutorial.steps:
            self.on_add_step(self.timeline.current_position, "click")
            return

        selected_index = self.timeline.selected_step_index
        if not (0 <= selected_index < len(self.tutorial.steps)):
            selected_index = min(
                range(len(self.tutorial.steps)),
                key=lambda idx: abs(self.tutorial.steps[idx].timestamp - self.timeline.current_position),
            )

        source_step = self.tutorial.steps[selected_index]
        new_step = copy.deepcopy(source_step)
        new_step.id = str(uuid.uuid4())
        new_step.timestamp = self.timeline.current_position
        self.tutorial.steps.append(new_step)
        self.tutorial.steps.sort(key=lambda s: s.timestamp)

        self.refresh()
        actual_index = self.tutorial.steps.index(new_step)
        self.set_current_step(actual_index)
        self.timeline.rebuild_scene()
        self.save_state()

    def delete_selected_range(self, ripple: bool = False):
        """Delete steps inside the marked range and optionally close the gap."""
        edit_range = self.timeline.get_edit_range()
        if not edit_range:
            return

        start, end = edit_range
        duration = end - start
        kept_steps = []
        for step in self.tutorial.steps:
            if start <= step.timestamp <= end:
                continue
            if ripple and step.timestamp > end:
                step.timestamp = max(start, step.timestamp - duration)
            kept_steps.append(step)

        self.tutorial.steps = sorted(kept_steps, key=lambda s: s.timestamp)
        self.timeline.current_position = start
        self.timeline.clear_edit_range()
        self.refresh()
        if self.tutorial.steps:
            nearest_index = min(
                range(len(self.tutorial.steps)),
                key=lambda idx: abs(self.tutorial.steps[idx].timestamp - start),
            )
            self.set_current_step(nearest_index)
        else:
            self.timeline.selected_step_index = -1
            self.timeline.refresh_step_items()
        self.timeline.rebuild_scene()
        self.timeline.position_changed.emit(self.timeline.current_position)
        self.save_state()

    def _create_property_section(self, section_key: str, title: str) -> CollapsibleSection:
        section = CollapsibleSection(title, self)
        self.property_sections[section_key] = {"title": title, "widget": section}
        self.property_section_visibility[section_key] = True
        self.props_container_layout.addWidget(section)
        return section

    def get_property_sections(self):
        return {key: value["title"] for key, value in self.property_sections.items()}

    def set_property_section_visible(self, section_key: str, visible: bool):
        section = self.property_sections.get(section_key)
        if not section:
            return
        self.property_section_visibility[section_key] = visible
        section["widget"].setVisible(visible)

    def is_property_section_visible(self, section_key: str) -> bool:
        return self.property_section_visibility.get(section_key, True)

    def refresh_audio_inputs(self):
        self.audio_input_combo.blockSignals(True)
        self.audio_input_combo.clear()

        if not AUDIO_AVAILABLE:
            self.audio_input_combo.addItem("Mic unavailable: sounddevice missing", None)
            self.audio_input_combo.setEnabled(False)
            self.btn_refresh_audio_inputs.setEnabled(False)
            self.btn_test_audio_input.setEnabled(False)
            self.audio_input_combo.blockSignals(False)
            return

        self.audio_input_combo.setEnabled(True)
        self.btn_refresh_audio_inputs.setEnabled(True)
        self.btn_test_audio_input.setEnabled(True)
        self.audio_input_combo.addItem("Default Input [Windows Default]", None)

        for device in get_audio_input_devices():
            self.audio_input_combo.addItem(
                device.get("label") or f"{device['name']} ({device['channels']} ch)",
                device["id"],
            )

        selected_index = 0
        for index in range(self.audio_input_combo.count()):
            if self.audio_input_combo.itemData(index) == self.tutorial.audio_input_device:
                selected_index = index
                break
            if self.audio_input_combo.itemText(index) == self.tutorial.audio_input_name:
                selected_index = index

        self.audio_input_combo.setCurrentIndex(selected_index)
        self.audio_input_combo.blockSignals(False)

    def update_audio_input_selection(self):
        self.tutorial.audio_input_device = self.audio_input_combo.currentData()
        self.tutorial.audio_input_name = self.audio_input_combo.currentText() or "Default Input [Windows Default]"
        self.save_state()

    def get_selected_audio_input(self):
        return self.audio_input_combo.currentData(), self.audio_input_combo.currentText()

    def test_audio_input(self):
        """Record and play back a short sample from the selected microphone."""
        if not AUDIO_AVAILABLE:
            return

        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        from PySide6.QtCore import Qt, QCoreApplication
        import winsound

        device_id, device_name = self.get_selected_audio_input()
        temp_dir = os.path.join(tempfile.gettempdir(), "tutomake")
        sample_path = os.path.join(temp_dir, "mic_test.wav")

        progress = QProgressDialog(f"Recording 3 second mic test from {device_name}...", None, 0, 0, self)
        progress.setWindowTitle("Test Mic")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QCoreApplication.processEvents()

        success, result = record_test_audio_clip(sample_path, device=device_id, duration=3.0)
        progress.close()

        if not success:
            QMessageBox.warning(self, "Mic Test Failed", result)
            return

        winsound.PlaySound(result, winsound.SND_FILENAME)
        QMessageBox.information(self, "Mic Test", f"Playback finished for:\n{device_name}")

    def _sync_audio_ui(self):
        """Synchronize audio controls with the current tutorial state."""
        self.refresh_audio_inputs()

        if self.tutorial.audio_path:
            filename = os.path.basename(self.tutorial.audio_path)
            self.audio_file_label.setText(filename)
            self.audio_file_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_audio_btn.setEnabled(True)
        else:
            self.audio_file_label.setText(self._tr("no_audio_loaded"))
            self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
            self.remove_audio_btn.setEnabled(False)

        self.sync_audio_controls_from_model()
        self.timeline.rebuild_scene()

        self.tutorial_title_input.blockSignals(True)
        self.start_subtitle_input.blockSignals(True)
        self.start_button_input.blockSignals(True)
        self.completion_title_input.blockSignals(True)
        self.completion_subtitle_input.blockSignals(True)
        self.restart_button_input.blockSignals(True)
        self.guide_language_combo.blockSignals(True)
        self.guide_character_size_spin.blockSignals(True)
        self.guide_card_anchor_combo.blockSignals(True)
        self.guide_card_direction_combo.blockSignals(True)
        self.guide_card_offset_spin.blockSignals(True)
        self.guide_card_top_spin.blockSignals(True)
        self.guide_card_left_spin.blockSignals(True)
        self.guide_card_width_spin.blockSignals(True)
        self.guide_card_scale_spin.blockSignals(True)
        self.guide_step_badge_size_spin.blockSignals(True)
        self.guide_card_gap_spin.blockSignals(True)
        self.guide_card_padding_spin.blockSignals(True)
        self.guide_card_opacity_spin.blockSignals(True)

        self.tutorial_title_input.setText(self.tutorial.title)
        self.start_subtitle_input.setText(self.tutorial.start_subtitle)
        self.start_button_input.setText(self.tutorial.start_button_text)
        self.completion_title_input.setText(self.tutorial.completion_title)
        self.completion_subtitle_input.setText(self.tutorial.completion_subtitle)
        self.restart_button_input.setText(self.tutorial.restart_button_text)
        guide_language_index = self.guide_language_combo.findData(getattr(self.tutorial, "guide_language", "ko"))
        self.guide_language_combo.setCurrentIndex(guide_language_index if guide_language_index >= 0 else 0)
        self.guide_character_size_spin.setValue(int(getattr(self.tutorial, "guide_character_size", 112) or 112))
        guide_anchor_index = self.guide_card_anchor_combo.findData(getattr(self.tutorial, "guide_card_anchor", "top_fixed"))
        self.guide_card_anchor_combo.setCurrentIndex(guide_anchor_index if guide_anchor_index >= 0 else 0)
        guide_direction_index = self.guide_card_direction_combo.findData(getattr(self.tutorial, "guide_card_direction", "auto"))
        self.guide_card_direction_combo.setCurrentIndex(guide_direction_index if guide_direction_index >= 0 else 0)
        self.guide_card_offset_spin.setValue(int(getattr(self.tutorial, "guide_card_offset", 16) or 16))
        self.guide_card_top_spin.setValue(int(getattr(self.tutorial, "guide_card_top", 0) or 0))
        self.guide_card_left_spin.setValue(int(getattr(self.tutorial, "guide_card_left", 0) or 0))
        self.guide_card_width_spin.setValue(int(getattr(self.tutorial, "guide_card_width", 680) or 680))
        self.guide_card_scale_spin.setValue(int(getattr(self.tutorial, "guide_card_scale_percent", 100) or 100))
        self.guide_step_badge_size_spin.setValue(int(getattr(self.tutorial, "guide_step_badge_size", 96) or 96))
        self.guide_card_gap_spin.setValue(int(getattr(self.tutorial, "guide_card_gap", 18) or 18))
        self.guide_card_padding_spin.setValue(int(getattr(self.tutorial, "guide_card_padding", 22) or 22))
        self.guide_card_opacity_spin.setValue(int(getattr(self.tutorial, "guide_card_opacity", 94) or 94))
        if getattr(self.tutorial, "guide_character_image_path", ""):
            filename = os.path.basename(self.tutorial.guide_character_image_path)
            self.guide_character_label.setText(filename)
            self.guide_character_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_guide_character_btn.setEnabled(True)
        else:
            self.guide_character_label.setText(self._tr("no_character_image"))
            self.guide_character_label.setStyleSheet("color: #666; font-style: italic;")
            self.remove_guide_character_btn.setEnabled(False)

        self.tutorial_title_input.blockSignals(False)
        self.start_subtitle_input.blockSignals(False)
        self.start_button_input.blockSignals(False)
        self.completion_title_input.blockSignals(False)
        self.completion_subtitle_input.blockSignals(False)
        self.restart_button_input.blockSignals(False)
        self.guide_language_combo.blockSignals(False)
        self.guide_character_size_spin.blockSignals(False)
        self.guide_card_anchor_combo.blockSignals(False)
        self.guide_card_direction_combo.blockSignals(False)
        self.guide_card_offset_spin.blockSignals(False)
        self.guide_card_top_spin.blockSignals(False)
        self.guide_card_left_spin.blockSignals(False)
        self.guide_card_width_spin.blockSignals(False)
        self.guide_card_scale_spin.blockSignals(False)
        self.guide_step_badge_size_spin.blockSignals(False)
        self.guide_card_gap_spin.blockSignals(False)
        self.guide_card_padding_spin.blockSignals(False)
        self.guide_card_opacity_spin.blockSignals(False)

    def update_export_text_fields(self):
        """Update tutorial-level text used by web exports."""
        self.tutorial.title = self.tutorial_title_input.text() or "New Tutorial"
        self.tutorial.start_subtitle = self.start_subtitle_input.text()
        self.tutorial.start_button_text = self.start_button_input.text() or "시작하기"
        self.tutorial.completion_title = self.completion_title_input.text() or "튜토리얼 완료"
        self.tutorial.completion_subtitle = self.completion_subtitle_input.text()
        self.tutorial.restart_button_text = self.restart_button_input.text() or "다시 시작"
        self.tutorial.guide_language = self.guide_language_combo.currentData() or "ko"
        self.tutorial.guide_character_size = self.guide_character_size_spin.value()
        self.tutorial.guide_card_anchor = self.guide_card_anchor_combo.currentData() or "top_fixed"
        self.tutorial.guide_card_direction = self.guide_card_direction_combo.currentData() or "auto"
        self.tutorial.guide_card_offset = self.guide_card_offset_spin.value()
        self.tutorial.guide_card_top = self.guide_card_top_spin.value()
        self.tutorial.guide_card_left = self.guide_card_left_spin.value()
        self.tutorial.guide_card_width = self.guide_card_width_spin.value()
        self.tutorial.guide_card_scale_percent = self.guide_card_scale_spin.value()
        self.tutorial.guide_step_badge_size = self.guide_step_badge_size_spin.value()
        self.tutorial.guide_card_gap = self.guide_card_gap_spin.value()
        self.tutorial.guide_card_padding = self.guide_card_padding_spin.value()
        self.tutorial.guide_card_opacity = self.guide_card_opacity_spin.value()
        self.save_state()

    def refresh(self):
        previous_row = self.step_list.currentRow()
        self.step_list.clear()
        for i, step in enumerate(self.tutorial.steps):
            self.step_list.addItem(f"Step {i+1}: {step.description}")

        self._sync_audio_ui()
        
        # Always use video mode if video is available
        has_video = bool(self.tutorial.video_path and os.path.exists(self.tutorial.video_path))
        self.view_mode = "video" if has_video else "screenshot"
            
        if self.tutorial.steps:
            target_row = previous_row if 0 <= previous_row < len(self.tutorial.steps) else 0
            self.set_current_step(target_row)
        else:
            self.timeline.selected_step_index = -1
            self.timeline.refresh_step_items()
            
    def select_step(self, index):
        """Select step from timeline or other external source."""
        self.set_current_step(index)

    def set_current_step(self, index: int):
        """Synchronize selected step across list, timeline, and preview."""
        if index < 0 or index >= len(self.tutorial.steps) or index >= self.step_list.count():
            return

        with QSignalBlocker(self.step_list):
            self.step_list.clearSelection()
            self.step_list.setCurrentRow(index)

        item = self.step_list.item(index)
        if item is not None:
            item.setSelected(True)

        self.timeline.selected_step_index = index
        self.timeline.refresh_step_items()
        self.load_step(index)

    def load_step(self, index):
        if index < 0 or index >= len(self.tutorial.steps):
            self._clear_drag_gif_preview(self._tr("drag_preview"))
            return
        step = self.tutorial.steps[index]
        
        # Update the canvas content based on the current radio.
        self.update_view_source()
        
        # Update inputs
        self.desc_input.blockSignals(True)
        self.desc_input.setText(step.description)
        self.desc_input.blockSignals(False)
        
        self.instruction_input.blockSignals(True)
        self.instruction_input.setPlainText(step.instruction)
        self.instruction_input.blockSignals(False)
        self._sync_step_guide_image_ui(step)
        
        self.radio_rect.blockSignals(True)
        self.radio_circle.blockSignals(True)
        if step.shape == "circle":
            self.radio_circle.setChecked(True)
        else:
            self.radio_rect.setChecked(True)
        self.radio_rect.blockSignals(False)
        self.radio_circle.blockSignals(False)
        
        self.chk_sound.blockSignals(True)
        self.chk_sound.setChecked(step.sound_enabled)
        self.chk_sound.blockSignals(False)
        
        # Text settings
        is_keyboard = step.action_type == "keyboard"
        self.keyboard_mode_combo.blockSignals(True)
        mode_index = self.keyboard_mode_combo.findData(step.keyboard_mode)
        self.keyboard_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.keyboard_mode_combo.blockSignals(False)
        self.keyboard_mode_combo.setEnabled(is_keyboard)

        self.text_content.blockSignals(True)
        self.text_content.setText(step.keyboard_input)
        self.text_content.blockSignals(False)
        self.text_content.setEnabled(is_keyboard)

        self.keyboard_space_behavior_combo.blockSignals(True)
        space_behavior_index = self.keyboard_space_behavior_combo.findData(getattr(step, "keyboard_space_behavior", "submit_step"))
        self.keyboard_space_behavior_combo.setCurrentIndex(space_behavior_index if space_behavior_index >= 0 else 0)
        self.keyboard_space_behavior_combo.blockSignals(False)
        self.keyboard_space_behavior_combo.setEnabled(is_keyboard and step.keyboard_mode == "text")
        if is_keyboard:
            self.text_content.setPlaceholderText(
                "Literal text to type"
                if step.keyboard_mode == "text"
                else "Key name like esc, enter, f5, left"
            )
        
        self.font_size_spinbox.blockSignals(True)
        self.font_size_spinbox.setValue(step.text_font_size)
        self.font_size_spinbox.blockSignals(False)

        self.font_weight_combo.blockSignals(True)
        current_weight = "Bold" if (getattr(step, "text_font_weight", "normal") or "normal").lower() == "bold" else "Normal"
        weight_index = self.font_weight_combo.findData(current_weight)
        self.font_weight_combo.setCurrentIndex(weight_index if weight_index >= 0 else 0)
        self.font_weight_combo.blockSignals(False)
        self.font_size_spinbox.setEnabled(is_keyboard)
        
        self.text_color_input.blockSignals(True)
        self.text_color_input.setText(step.text_color)
        self.text_color_input.blockSignals(False)
        self.text_color_input.setEnabled(is_keyboard)
        
        self.bg_color_input.blockSignals(True)
        self.bg_color_input.setText(step.text_bg_color)
        self.bg_color_input.blockSignals(False)
        self.bg_color_input.setEnabled(is_keyboard)
        
        # Hitbox style settings (enabled for click steps)
        is_click = step.action_type == "click"
        
        self.hitbox_line_width_slider.blockSignals(True)
        self.hitbox_line_width_slider.setValue(step.hitbox_line_width)
        self.hitbox_line_width_label.setText(str(step.hitbox_line_width))
        self.hitbox_line_width_slider.blockSignals(False)
        self.hitbox_line_width_slider.setEnabled(is_click)
        
        self.hitbox_line_style_combo.blockSignals(True)
        idx_style = self.hitbox_line_style_combo.findText(step.hitbox_line_style)
        if idx_style >= 0:
            self.hitbox_line_style_combo.setCurrentIndex(idx_style)
        self.hitbox_line_style_combo.blockSignals(False)
        self.hitbox_line_style_combo.setEnabled(is_click)
        
        self.hitbox_line_color_input.blockSignals(True)
        self.hitbox_line_color_input.setText(step.hitbox_line_color)
        self.hitbox_line_color_input.blockSignals(False)
        self.hitbox_line_color_input.setEnabled(is_click)
        # Update line color preview
        if step.hitbox_line_color and step.hitbox_line_color.startswith("#") and len(step.hitbox_line_color) >= 7:
            self.hitbox_line_color_preview.setStyleSheet(f"background: {step.hitbox_line_color[:7]}; border: 1px solid #555; border-radius: 3px;")
        
        self.hitbox_fill_color_input.blockSignals(True)
        self.hitbox_fill_color_input.setText(step.hitbox_fill_color)
        self.hitbox_fill_color_input.blockSignals(False)
        self.hitbox_fill_color_input.setEnabled(is_click)
        
        self.hitbox_fill_opacity_slider.blockSignals(True)
        self.hitbox_fill_opacity_slider.setValue(step.hitbox_fill_opacity)
        self.hitbox_fill_opacity_label.setText(f"{step.hitbox_fill_opacity}%")
        self.hitbox_fill_opacity_slider.blockSignals(False)
        self.hitbox_fill_opacity_slider.setEnabled(is_click)

        # Update fill color preview with opacity
        if step.hitbox_fill_color and step.hitbox_fill_color.startswith("#") and len(step.hitbox_fill_color) >= 7:
            opacity = step.hitbox_fill_opacity / 100.0
            self.hitbox_fill_color_preview.setStyleSheet(f"background: {step.hitbox_fill_color[:7]}; opacity: {opacity}; border: 1px solid #555; border-radius: 3px;")

        is_drag = step.action_type == "mouse_drag"
        self.drag_button_combo.blockSignals(True)
        drag_button_index = self.drag_button_combo.findData(getattr(step, "drag_button", "left"))
        self.drag_button_combo.setCurrentIndex(drag_button_index if drag_button_index >= 0 else 0)
        self.drag_button_combo.blockSignals(False)
        self.drag_button_combo.setEnabled(is_drag)

        self.drag_min_distance_spin.blockSignals(True)
        self.drag_min_distance_spin.setValue(int(getattr(step, "drag_min_distance", 30) or 30))
        self.drag_min_distance_spin.blockSignals(False)
        self.drag_min_distance_spin.setEnabled(is_drag)

        auto_drag_gif_enabled = bool(getattr(step, "auto_drag_gif_enabled", True))
        self.auto_drag_gif_checkbox.blockSignals(True)
        self.auto_drag_gif_checkbox.setChecked(auto_drag_gif_enabled)
        self.auto_drag_gif_checkbox.blockSignals(False)
        self.auto_drag_gif_checkbox.setEnabled(is_drag)

        self.drag_gif_lead_spin.blockSignals(True)
        self.drag_gif_lead_spin.setValue(int(round(float(getattr(step, "drag_gif_lead_seconds", 0.6) or 0.0) * 1000)))
        self.drag_gif_lead_spin.blockSignals(False)
        self.drag_gif_lead_spin.setEnabled(is_drag and auto_drag_gif_enabled)

        self.drag_gif_tail_spin.blockSignals(True)
        self.drag_gif_tail_spin.setValue(int(round(float(getattr(step, "drag_gif_tail_seconds", 0.15) or 0.0) * 1000)))
        self.drag_gif_tail_spin.blockSignals(False)
        self.drag_gif_tail_spin.setEnabled(is_drag and auto_drag_gif_enabled)

        self.drag_gif_fps_spin.blockSignals(True)
        self.drag_gif_fps_spin.setValue(int(round(float(getattr(step, "drag_gif_fps", 8.0) or 8.0))))
        self.drag_gif_fps_spin.blockSignals(False)
        self.drag_gif_fps_spin.setEnabled(is_drag and auto_drag_gif_enabled)

        self.drag_gif_size_spin.blockSignals(True)
        self.drag_gif_size_spin.setValue(int(getattr(step, "drag_gif_preview_size", 260) or 260))
        self.drag_gif_size_spin.blockSignals(False)
        self.drag_gif_size_spin.setEnabled(is_drag)

        self.drag_arrow_enabled_checkbox.blockSignals(True)
        self.drag_arrow_enabled_checkbox.setChecked(bool(getattr(step, "drag_direction_arrow_enabled", True)))
        self.drag_arrow_enabled_checkbox.blockSignals(False)
        self.drag_arrow_enabled_checkbox.setEnabled(is_drag)

        self.drag_arrow_size_spin.blockSignals(True)
        self.drag_arrow_size_spin.setValue(int(getattr(step, "drag_direction_arrow_size", 16) or 16))
        self.drag_arrow_size_spin.blockSignals(False)
        self.drag_arrow_size_spin.setEnabled(is_drag and bool(getattr(step, "drag_direction_arrow_enabled", True)))

        self._update_drag_gif_preview(step)

    def update_view_source(self):
        idx = self.step_list.currentRow()
        if idx < 0: return
        step = self.tutorial.steps[idx]
        
        if self.view_mode == "video" and self.tutorial.video_path and os.path.exists(self.tutorial.video_path):
            # Load Video Frame
            self.show_video_frame(step)
        else:
            # Load Screenshot
            self.canvas.set_step(step) # This sets pixmap from step.image_path

    def show_video_frame(self, step):
        # We need to extract the frame using opencv
        import cv2
        import numpy as np
        
        cap = cv2.VideoCapture(self.tutorial.video_path)
        if not cap.isOpened():
            print("Failed to open video for preview")
            self.canvas.set_step(step) # Fallback
            return
            
        # Timestamp to Frame
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 24.0
        
        # Recorder saves timestamp based on frame_count / fps
        target_frame = int(step.timestamp * fps)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            # Convert to QPixmap
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            
            # Set to canvas manually (VideoCanvas logic needed? ImageCanvas is valid)
            # ImageCanvas expects a step. Logic in ImageCanvas:
            # set_step sets self.step and loads pixmap from file.
            # We want to override the pixmap but keep the step interactions.
            self.canvas.step = step
            self.canvas.setPixmap(pixmap)
            self.canvas.adjustSize()
            self.canvas.update()
        else:
            print("Failed to read frame")
            self.canvas.set_step(step) # Fallback

    def update_desc_preview(self, text):
        """Update UI preview only, no state save."""
        idx = self.step_list.currentRow()
        if idx >= 0:
            self.tutorial.steps[idx].description = text
            item = self.step_list.item(idx)
            item.setText(f"Step {idx+1}: {text}")
    
    def update_instruction_preview(self):
        """Update instruction text on the current step."""
        idx = self.step_list.currentRow()
        if idx >= 0:
            self.tutorial.steps[idx].instruction = self.instruction_input.toPlainText()
            self.save_state()

    def _sync_step_guide_image_ui(self, step):
        guide_image_path = getattr(step, "guide_image_path", "") if step else ""
        if guide_image_path:
            self.step_guide_image_label.setText(os.path.basename(guide_image_path))
            self.step_guide_image_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_step_guide_image_btn.setEnabled(True)
        else:
            self.step_guide_image_label.setText(self._tr("default_character"))
            self.step_guide_image_label.setStyleSheet("color: #666; font-style: italic;")
            self.remove_step_guide_image_btn.setEnabled(False)

    def _clear_drag_gif_preview(self, message=None):
        if message is None:
            message = self._tr("drag_preview")
        if self._drag_preview_movie is not None:
            self._drag_preview_movie.stop()
            self.drag_gif_preview.setMovie(None)
            self._drag_preview_movie = None
        if self._drag_preview_temp_path and os.path.exists(self._drag_preview_temp_path):
            try:
                os.remove(self._drag_preview_temp_path)
            except OSError:
                pass
        self._drag_preview_temp_path = None
        self.drag_gif_preview.clear()
        self.drag_gif_preview.setText(message)

    def _cancel_drag_preview_request(self):
        self._drag_preview_request_id += 1
        self._drag_preview_step_id = ""

    def _on_drag_gif_preview_ready(self, request_id: int, step_id: str, gif_bytes):
        worker = self._drag_preview_workers.pop(request_id, None)
        if worker is not None:
            worker.deleteLater()

        if request_id != self._drag_preview_request_id or step_id != self._drag_preview_step_id:
            return

        current_idx = self.step_list.currentRow()
        if not (0 <= current_idx < len(self.tutorial.steps)):
            self._clear_drag_gif_preview(self._tr("drag_preview"))
            return

        step = self.tutorial.steps[current_idx]
        if step.action_type != "mouse_drag" or step.id != step_id:
            return

        preview_size = int(getattr(step, "drag_gif_preview_size", 260) or 260)
        if gif_bytes:
            self._clear_drag_gif_preview("")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".gif")
            temp_file.write(gif_bytes)
            temp_file.close()
            self._drag_preview_temp_path = temp_file.name
            movie = QMovie(temp_file.name)
            movie.setScaledSize(QSize(preview_size, preview_size))
            self.drag_gif_preview.setMovie(movie)
            movie.start()
            self._drag_preview_movie = movie
            return

        self._clear_drag_gif_preview(self._tr("drag_preview"))

    def _update_drag_gif_preview(self, step):
        if not step or step.action_type != "mouse_drag":
            self._cancel_drag_preview_request()
            self._clear_drag_gif_preview(self._tr("drag_preview"))
            return

        preview_size = int(getattr(step, "drag_gif_preview_size", 260) or 260)
        self.drag_gif_preview.setFixedHeight(max(120, preview_size + 24))
        gif_path = getattr(step, "guide_image_path", "") or ""

        if gif_path and os.path.exists(gif_path) and gif_path.lower().endswith(".gif"):
            self._clear_drag_gif_preview("")
            movie = QMovie(gif_path)
            movie.setScaledSize(QSize(preview_size, preview_size))
            self.drag_gif_preview.setMovie(movie)
            movie.start()
            self._drag_preview_movie = movie
            return

        self._drag_preview_request_id += 1
        request_id = self._drag_preview_request_id
        self._drag_preview_step_id = step.id
        self._clear_drag_gif_preview("Generating drag GIF preview...")

        worker = DragGifPreviewWorker(
            request_id=request_id,
            step_id=step.id,
            video_path=getattr(self.tutorial, "video_path", "") or "",
            step_data=step.model_dump(),
        )
        worker.preview_ready.connect(self._on_drag_gif_preview_ready)
        self._drag_preview_workers[request_id] = worker
        worker.start()

    def import_step_guide_image(self):
        idx = self.step_list.currentRow()
        if idx < 0 or idx >= len(self.tutorial.steps):
            return

        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Step Card Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All Files (*)",
        )
        if image_path:
            self.tutorial.steps[idx].guide_image_path = image_path
            self._sync_step_guide_image_ui(self.tutorial.steps[idx])
            self.save_state()

    def remove_step_guide_image(self):
        idx = self.step_list.currentRow()
        if idx < 0 or idx >= len(self.tutorial.steps):
            return

        self.tutorial.steps[idx].guide_image_path = ""
        self._sync_step_guide_image_ui(self.tutorial.steps[idx])
        self.save_state()
            
    def get_selected_indices(self):
        """Get list of selected step indices."""
        return [self.step_list.row(item) for item in self.step_list.selectedItems()]
    
    def on_selection_changed(self):
        """Handle selection change for multi-select."""
        selected = self.get_selected_indices()
        count = len(selected)

        if count == 1:
            index = selected[0]
            self.timeline.selected_step_index = index
            self.timeline.refresh_step_items()
            if self.step_list.currentRow() != index:
                with QSignalBlocker(self.step_list):
                    self.step_list.setCurrentRow(index)
                self.load_step(index)
        elif count == 0:
            self.timeline.selected_step_index = -1
            self.timeline.refresh_step_items()
        
        # Update Properties panel title to show selection count
        if count > 1:
            self.props_dock.setWindowTitle(f"Properties ({count} selected)")
        else:
            self.props_dock.setWindowTitle("Properties")

    def update_shape(self):
        """Update shape for all selected steps."""
        selected = self.get_selected_indices()
        if not selected:
            return
            
        new_shape = "circle" if self.radio_circle.isChecked() else "rect"
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].shape = new_shape
        
        self.canvas.update()
        self.save_state()

    def update_sound(self):
        """Update sound setting for all selected steps."""
        selected = self.get_selected_indices()
        if not selected:
            return
        
        new_sound = self.chk_sound.isChecked()
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].sound_enabled = new_sound
        
        self.save_state()
    
    def update_keyboard_input_preview(self, text):
        """Update keyboard input for all selected steps."""
        selected = self.get_selected_indices()
        if not selected:
            return
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                step.keyboard_input = text
                self._normalize_keyboard_step(step)
        
        self.canvas.update()

    def update_keyboard_mode(self):
        """Switch selected keyboard steps between text input and key input."""
        selected = self.get_selected_indices()
        if not selected:
            return

        mode = self.keyboard_mode_combo.currentData()
        self.text_content.setPlaceholderText(
            "Literal text to type"
            if mode == "text"
            else "Key name like esc, enter, f5, left"
        )
        self.keyboard_space_behavior_combo.setEnabled(mode == "text")

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type != "keyboard":
                    continue
                step.keyboard_mode = mode
                self._normalize_keyboard_step(step)

        self.refresh()
        self.canvas.update()
        self.save_state()

    def update_keyboard_space_behavior(self):
        """Update whether space inserts a character or submits keyboard text steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        space_behavior = self.keyboard_space_behavior_combo.currentData() or "insert_space"
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type != "keyboard" or step.keyboard_mode != "text":
                    continue
                step.keyboard_space_behavior = space_behavior

        self.save_state()
    
    def update_text_style_preview(self):
        """Update text style for all selected steps."""
        selected = self.get_selected_indices()
        if not selected:
            return
        
        # Parse values once
        try:
            font_size = self.font_size_spinbox.value()
        except ValueError:
            font_size = 24
        font_weight = self.font_weight_combo.currentData() or "Normal"
        
        text_color = self.text_color_input.text() or "#FFFFFF"
        bg_color = self.bg_color_input.text() or "#000000"
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                step.text_font_size = font_size
                step.text_font_weight = "bold" if str(font_weight).lower() == "bold" else "normal"
                step.text_color = text_color
                step.text_bg_color = bg_color
        
        self.canvas.update()

    def update_hitbox_line_width(self, value):
        """Update hitbox line width for all selected steps."""
        self.hitbox_line_width_label.setText(str(value))
        selected = self.get_selected_indices()
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].hitbox_line_width = value
        self.canvas.update()
        self.save_state()
    
    def update_hitbox_line_style(self, style):
        """Update hitbox line style for all selected steps."""
        selected = self.get_selected_indices()
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].hitbox_line_style = style
        self.canvas.update()
        self.save_state()
    
    def update_hitbox_line_color(self, color):
        """Update hitbox line color for all selected steps."""
        selected = self.get_selected_indices()
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].hitbox_line_color = color
        # Update preview
        if color and color.startswith("#") and len(color) >= 7:
            self.hitbox_line_color_preview.setStyleSheet(f"background: {color[:7]}; border: 1px solid #555; border-radius: 3px;")
        self.canvas.update()
    
    def update_hitbox_fill_color(self, color):
        """Update hitbox fill color for all selected steps."""
        selected = self.get_selected_indices()
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].hitbox_fill_color = color
        # Update preview
        if color and color.startswith("#") and len(color) >= 7:
            self.hitbox_fill_color_preview.setStyleSheet(f"background: {color[:7]}; border: 1px solid #555; border-radius: 3px;")
        self.canvas.update()
    
    def update_hitbox_fill_opacity(self, value):
        """Update hitbox fill opacity for all selected steps."""
        self.hitbox_fill_opacity_label.setText(f"{value}%")
        selected = self.get_selected_indices()
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                self.tutorial.steps[idx].hitbox_fill_opacity = value
        self.canvas.update()
        self.save_state()

    def update_drag_button(self):
        """Update drag mouse button for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        drag_button = self.drag_button_combo.currentData() or "left"
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_button = drag_button
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_min_distance(self, value):
        """Update drag minimum distance for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_min_distance = int(value)
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_auto_drag_gif_enabled(self, checked):
        """Toggle automatic drag GIF generation for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.auto_drag_gif_enabled = bool(checked)

        current_is_drag = False
        current_idx = self.step_list.currentRow()
        if 0 <= current_idx < len(self.tutorial.steps):
            current_is_drag = self.tutorial.steps[current_idx].action_type == "mouse_drag"
        self.drag_gif_lead_spin.setEnabled(current_is_drag and bool(checked))
        self.drag_gif_tail_spin.setEnabled(current_is_drag and bool(checked))
        self.drag_gif_fps_spin.setEnabled(current_is_drag and bool(checked))
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_gif_timing(self):
        """Update automatic drag GIF lead/tail timing for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        lead_seconds = self.drag_gif_lead_spin.value() / 1000.0
        tail_seconds = self.drag_gif_tail_spin.value() / 1000.0
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_gif_lead_seconds = lead_seconds
                    step.drag_gif_tail_seconds = tail_seconds
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_gif_size(self, value):
        """Update drag GIF preview/export size for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_gif_preview_size = int(value)
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_gif_fps(self, value):
        """Update automatic drag GIF frame rate for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_gif_fps = float(value)
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_direction_arrow_enabled(self, checked):
        """Toggle drag direction arrow for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_direction_arrow_enabled = bool(checked)

        current_is_drag = False
        current_idx = self.step_list.currentRow()
        if 0 <= current_idx < len(self.tutorial.steps):
            current_is_drag = self.tutorial.steps[current_idx].action_type == "mouse_drag"
        self.drag_arrow_size_spin.setEnabled(current_is_drag and bool(checked))
        self.save_state()
        self.load_step(self.step_list.currentRow())

    def update_drag_direction_arrow_size(self, value):
        """Update drag direction arrow size for selected drag steps."""
        selected = self.get_selected_indices()
        if not selected:
            return

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type == "mouse_drag":
                    step.drag_direction_arrow_size = int(value)
        self.save_state()
        self.load_step(self.step_list.currentRow())
    
    def import_audio(self):
        """Import an audio file for the tutorial."""
        from PySide6.QtWidgets import QFileDialog
        audio_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Audio File",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.ogg *.flac);;All Files (*)"
        )
        if audio_path:
            self.tutorial.audio_path = audio_path
            self.tutorial.audio_trim_start = 0.0
            self.tutorial.audio_trim_end = None
            self._sync_audio_ui()
            self.save_state()
            print(f"Imported audio: {audio_path}")
    
    def remove_audio(self):
        """Remove the audio file from the tutorial."""
        self.tutorial.audio_path = None
        self.tutorial.audio_offset = 0.0
        self.tutorial.audio_trim_start = 0.0
        self.tutorial.audio_trim_end = None
        self.audio_file_label.setText(self._tr("no_audio_loaded"))
        self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
        self.remove_audio_btn.setEnabled(False)
        self.audio_offset_slider.setValue(0)
        self.timeline.rebuild_scene()
        self.save_state()
        print("Audio removed")

    def import_guide_character_image(self):
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Guide Character Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All Files (*)",
        )
        if image_path:
            self.tutorial.guide_character_image_path = image_path
            filename = os.path.basename(image_path)
            self.guide_character_label.setText(filename)
            self.guide_character_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_guide_character_btn.setEnabled(True)
            self.save_state()

    def remove_guide_character_image(self):
        self.tutorial.guide_character_image_path = ""
        self.guide_character_label.setText(self._tr("no_character_image"))
        self.guide_character_label.setStyleSheet("color: #666; font-style: italic;")
        self.remove_guide_character_btn.setEnabled(False)
        self.save_state()
    
    def update_audio_offset(self, value):
        """Update the audio sync offset."""
        offset_seconds = value / 10.0  # Slider value is in 0.1s units
        self.tutorial.audio_offset = offset_seconds
        self.sync_audio_controls_from_model()
        self.timeline.rebuild_scene()
        self.save_state()

    def sync_audio_controls_from_model(self):
        self.audio_offset_slider.blockSignals(True)
        self.audio_offset_slider.setValue(int(round(self.tutorial.audio_offset * 10)))
        self.audio_offset_slider.blockSignals(False)
        trim_start = float(getattr(self.tutorial, "audio_trim_start", 0.0) or 0.0)
        trim_end = getattr(self.tutorial, "audio_trim_end", None)
        trim_suffix = ""
        if trim_start > 0 or trim_end is not None:
            trim_suffix = f"  Trim {trim_start:.1f}s"
            if trim_end is not None:
                trim_suffix += f"-{float(trim_end):.1f}s"
        self.audio_offset_label.setText(f"{self.tutorial.audio_offset:+.1f}s{trim_suffix}")

    def preview_audio_offset_from_timeline(self, offset_seconds: float):
        self.tutorial.audio_offset = offset_seconds
        self.sync_audio_controls_from_model()

    def commit_audio_offset_from_timeline(self, offset_seconds: float):
        self.preview_audio_offset_from_timeline(offset_seconds)
        self.save_state()

    def preview_audio_trim_from_timeline(self):
        self.sync_audio_controls_from_model()

    def commit_audio_trim_from_timeline(self):
        self.preview_audio_trim_from_timeline()
        self.save_state()

    def pick_hitbox_line_color(self):
        """Open color picker dialog for line color."""
        from PySide6.QtWidgets import QColorDialog
        current_color = self.hitbox_line_color_input.text() or "#FF0000"
        color = QColorDialog.getColor(QColor(current_color), self, "Select Line Color")
        if color.isValid():
            hex_color = color.name()
            self.hitbox_line_color_input.setText(hex_color)
    
    def pick_hitbox_fill_color(self):
        """Open color picker dialog for fill color."""
        from PySide6.QtWidgets import QColorDialog
        current_text = self.hitbox_fill_color_input.text() or "#FF000033"
        current_color = QColor(current_text[:7]) if len(current_text) >= 7 else QColor("#FF0000")
        color = QColorDialog.getColor(current_color, self, "Select Fill Color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            # Convert to #RRGGBBAA format
            hex_color = color.name() + format(color.alpha(), '02x')
            self.hitbox_fill_color_input.setText(hex_color)
    
    def pick_text_color(self):
        """Open color picker dialog for text color."""
        from PySide6.QtWidgets import QColorDialog
        current_color = self.text_color_input.text() or "#FFFFFF"
        color = QColorDialog.getColor(QColor(current_color), self, "Select Text Color")
        if color.isValid():
            hex_color = color.name()
            self.text_color_input.setText(hex_color)
            self.text_color_preview.setStyleSheet(f"background: {hex_color}; border: 1px solid #555; border-radius: 3px;")
    
    def pick_bg_color(self):
        """Open color picker dialog for background color."""
        from PySide6.QtWidgets import QColorDialog
        current_color = self.bg_color_input.text() or "#000000"
        color = QColorDialog.getColor(QColor(current_color), self, "Select Background Color")
        if color.isValid():
            hex_color = color.name()
            self.bg_color_input.setText(hex_color)
            self.bg_color_preview.setStyleSheet(f"background: {hex_color}; border: 1px solid #555; border-radius: 3px;")


    def on_timeline_position_changed(self, position_seconds):
        """Called when timeline slider is moved. Show video frame at that position."""
        if not self.tutorial or not self.tutorial.video_path:
            return
            
        if not os.path.exists(self.tutorial.video_path):
            return
        
        # Throttle frame updates for smooth scrubbing
        # Only update if enough time has passed since last update
        current_time = cv2.getTickCount() / cv2.getTickFrequency()
        
        if not hasattr(self, '_last_frame_time'):
            self._last_frame_time = 0
            self._pending_position = None
            self._frame_update_timer = None
        
        # If less than 50ms since last update, schedule a delayed update
        if current_time - self._last_frame_time < 0.05:
            self._pending_position = position_seconds
            if self._frame_update_timer is None:
                self._frame_update_timer = QTimer(self)
                self._frame_update_timer.setSingleShot(True)
                self._frame_update_timer.timeout.connect(self._update_pending_frame)
            if not self._frame_update_timer.isActive():
                self._frame_update_timer.start(50)
            return
        
        self._update_frame_at_position(position_seconds)
    
    def _update_pending_frame(self):
        """Update to the last pending frame position."""
        if self._pending_position is not None:
            self._update_frame_at_position(self._pending_position)
            self._pending_position = None
    
    def _update_frame_at_position(self, position_seconds):
        """Actually update the video frame at the given position."""
        # Open video if not open
        if self.video_cap is None or not self.video_cap.isOpened():
            self.video_cap = cv2.VideoCapture(self.tutorial.video_path)
            
        fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 24.0
        frame_num = int(position_seconds * fps)
        
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.video_cap.read()
        
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            # Make a copy to ensure data persists
            frame_copy = frame.copy()
            qimg = QImage(frame_copy.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            self.canvas.setPixmap(pixmap)
            self.canvas.adjustSize()
        
        self._last_frame_time = cv2.getTickCount() / cv2.getTickFrequency()

    def closeEvent(self, event):
        self.timeline.play_timer.stop()
        self._cancel_drag_preview_request()
        self._clear_drag_gif_preview("")

        if getattr(self, "_frame_update_timer", None) is not None:
            self._frame_update_timer.stop()

        if self.video_cap is not None:
            self.video_cap.release()
            self.video_cap = None

        super().closeEvent(event)

    def on_add_step(self, timestamp, action_type=None):
        """Add a new step at the given timestamp."""
        # Create a new step with default values
        # We'll use the current video frame position for hitbox center
        
        # Decide type
        if action_type is None:
            action_type = "click"
            
        desc = "New Step" if action_type == "click" else "Type text"
            
        new_step = Step(
            image_path="",  # No screenshot for manually added steps
            action_type=action_type,
            x=100,
            y=100,
            width=50,
            height=50,
            description=desc,
            keyboard_mode="text",
            timestamp=timestamp
        )
        
        # Insert in sorted order by timestamp
        insert_idx = 0
        for i, step in enumerate(self.tutorial.steps):
            if step.timestamp > timestamp:
                break
            insert_idx = i + 1
        
        self.tutorial.steps.insert(insert_idx, new_step)
        self.tutorial.steps.sort(key=lambda s: s.timestamp) # Ensure sorted
        
        self.refresh()
        actual_index = self.tutorial.steps.index(new_step)
        self.set_current_step(actual_index)
        self.timeline.rebuild_scene()
        self.save_state()  # Save state after adding step
        
    def on_steps_reordered(self):
        """Handle steps reordered in timeline via drag-drop."""
        # Refresh list to match new order
        current_index = self.timeline.selected_step_index
        self.refresh()
        if 0 <= current_index < len(self.tutorial.steps):
            self.set_current_step(current_index)
        self.save_state()
        
    def on_delete_step(self, index):
        """Delete step at given index."""
        if 0 <= index < len(self.tutorial.steps):
            del self.tutorial.steps[index]
            self.refresh()
            if self.tutorial.steps:
                next_index = min(index, len(self.tutorial.steps) - 1)
                self.set_current_step(next_index)
            else:
                self.timeline.selected_step_index = -1
                self.timeline.refresh_step_items()
            self.save_state()  # Save state after deletion

    # ==================== Undo/Redo System ====================
    
    def save_state(self):
        """Save current tutorial state to history."""
        import copy
        
        # Remove any redo states if we're not at the end
        if self.history_index < len(self.history_stack) - 1:
            self.history_stack = self.history_stack[:self.history_index + 1]
        
        # Create a deep copy of steps
        state = {
            'steps': [step.model_dump() for step in self.tutorial.steps],
            'title': self.tutorial.title,
            'start_subtitle': self.tutorial.start_subtitle,
            'start_button_text': self.tutorial.start_button_text,
            'completion_title': self.tutorial.completion_title,
            'completion_subtitle': self.tutorial.completion_subtitle,
            'restart_button_text': self.tutorial.restart_button_text,
            'guide_language': getattr(self.tutorial, 'guide_language', 'ko'),
            'guide_character_image_path': getattr(self.tutorial, 'guide_character_image_path', ''),
            'guide_character_size': getattr(self.tutorial, 'guide_character_size', 112),
            'guide_card_anchor': getattr(self.tutorial, 'guide_card_anchor', 'top_fixed'),
            'guide_card_direction': getattr(self.tutorial, 'guide_card_direction', 'auto'),
            'guide_card_offset': getattr(self.tutorial, 'guide_card_offset', 16),
            'guide_card_top': getattr(self.tutorial, 'guide_card_top', 0),
            'guide_card_left': getattr(self.tutorial, 'guide_card_left', 0),
            'guide_card_width': getattr(self.tutorial, 'guide_card_width', 680),
            'guide_card_scale_percent': getattr(self.tutorial, 'guide_card_scale_percent', 100),
            'guide_step_badge_size': getattr(self.tutorial, 'guide_step_badge_size', 96),
            'guide_card_gap': getattr(self.tutorial, 'guide_card_gap', 18),
            'guide_card_padding': getattr(self.tutorial, 'guide_card_padding', 22),
            'guide_card_opacity': getattr(self.tutorial, 'guide_card_opacity', 94),
            'audio_input_device': self.tutorial.audio_input_device,
            'audio_input_name': self.tutorial.audio_input_name,
            'video_path': self.tutorial.video_path,
            'audio_path': self.tutorial.audio_path,
            'audio_offset': self.tutorial.audio_offset,
            'audio_trim_start': self.tutorial.audio_trim_start,
            'audio_trim_end': self.tutorial.audio_trim_end,
        }
        
        self.history_stack.append(state)
        self.history_index = len(self.history_stack) - 1
        
        # Limit history size
        if len(self.history_stack) > self.max_history:
            self.history_stack.pop(0)
            self.history_index -= 1
    
    def undo(self):
        """Restore previous state."""
        if self.history_index > 0:
            self.history_index -= 1
            self._restore_state(self.history_stack[self.history_index])
            print(f"Undo: history index = {self.history_index}")
    
    def redo(self):
        """Restore next state."""
        if self.history_index < len(self.history_stack) - 1:
            self.history_index += 1
            self._restore_state(self.history_stack[self.history_index])
            print(f"Redo: history index = {self.history_index}")
    
    def _restore_state(self, state):
        """Restore tutorial from state dict."""
        from ..model import Step
        
        self.tutorial.steps = [Step(**s) for s in state['steps']]
        self.tutorial.title = state.get('title', self.tutorial.title)
        self.tutorial.start_subtitle = state.get('start_subtitle', self.tutorial.start_subtitle)
        self.tutorial.start_button_text = state.get('start_button_text', self.tutorial.start_button_text)
        self.tutorial.completion_title = state.get('completion_title', self.tutorial.completion_title)
        self.tutorial.completion_subtitle = state.get('completion_subtitle', self.tutorial.completion_subtitle)
        self.tutorial.restart_button_text = state.get('restart_button_text', self.tutorial.restart_button_text)
        self.tutorial.guide_language = state.get('guide_language', getattr(self.tutorial, 'guide_language', 'ko'))
        self.tutorial.guide_character_image_path = state.get('guide_character_image_path', getattr(self.tutorial, 'guide_character_image_path', ''))
        self.tutorial.guide_character_size = state.get('guide_character_size', getattr(self.tutorial, 'guide_character_size', 112))
        self.tutorial.guide_card_anchor = state.get('guide_card_anchor', getattr(self.tutorial, 'guide_card_anchor', 'top_fixed'))
        self.tutorial.guide_card_direction = state.get('guide_card_direction', getattr(self.tutorial, 'guide_card_direction', 'auto'))
        self.tutorial.guide_card_offset = state.get('guide_card_offset', getattr(self.tutorial, 'guide_card_offset', 16))
        self.tutorial.guide_card_top = state.get('guide_card_top', getattr(self.tutorial, 'guide_card_top', 0))
        self.tutorial.guide_card_left = state.get('guide_card_left', getattr(self.tutorial, 'guide_card_left', 0))
        self.tutorial.guide_card_width = state.get('guide_card_width', getattr(self.tutorial, 'guide_card_width', 680))
        self.tutorial.guide_card_scale_percent = state.get('guide_card_scale_percent', getattr(self.tutorial, 'guide_card_scale_percent', 100))
        self.tutorial.guide_step_badge_size = state.get('guide_step_badge_size', getattr(self.tutorial, 'guide_step_badge_size', 96))
        self.tutorial.guide_card_gap = state.get('guide_card_gap', getattr(self.tutorial, 'guide_card_gap', 18))
        self.tutorial.guide_card_padding = state.get('guide_card_padding', getattr(self.tutorial, 'guide_card_padding', 22))
        self.tutorial.guide_card_opacity = state.get('guide_card_opacity', getattr(self.tutorial, 'guide_card_opacity', 94))
        self.tutorial.audio_input_device = state.get('audio_input_device', self.tutorial.audio_input_device)
        self.tutorial.audio_input_name = state.get('audio_input_name', self.tutorial.audio_input_name)
        self.tutorial.video_path = state['video_path']
        self.tutorial.audio_path = state.get('audio_path')
        self.tutorial.audio_offset = state.get('audio_offset', 0.0)
        self.tutorial.audio_trim_start = state.get('audio_trim_start', 0.0)
        self.tutorial.audio_trim_end = state.get('audio_trim_end')
        self._sync_audio_ui()
        self.refresh()
        self.timeline.update()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        from ..settings import Settings
        settings = Settings()

        if self._is_text_input_focus():
            super().keyPressEvent(event)
            return
        
        # Helper matches function (could be utility, but inline is fine)
        def matches(action):
            event_sequence = QKeySequence(event.keyCombination())
            return event_sequence == settings.get_key(action)
        
        # Undo/Redo
        if matches("undo"):
            self.undo()
            return
        elif matches("redo"):
            self.redo()
            return
        
        super().keyPressEvent(event)
