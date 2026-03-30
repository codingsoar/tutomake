from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, 
                             QLabel, QLineEdit, QTextEdit, QFormLayout, QScrollArea, QSizePolicy,
                             QRadioButton, QButtonGroup, QCheckBox, QSlider, QPushButton,
                             QMenu, QMainWindow, QDockWidget, QGraphicsView, QGraphicsScene,
                             QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QResizeEvent, QImage, QAction, QPolygon, QFont, QBrush, QWheelEvent
from PySide6.QtCore import Qt, QRect, QTimer, Signal, QPoint, QRectF, QPointF, QSignalBlocker
import os
import cv2
from ..key_utils import display_key_name
from ..model import Tutorial, Step

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
        
        self.btn_out = QPushButton("−")
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
        
        # Playback state
        self.is_playing = False
        self.play_timer = QTimer()
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
        btn_zoom_out = QPushButton("−")
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
        
        # Playback state
        self.is_playing = False
        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self.advance_frame)
    
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
            self.video_duration = 0
            self.fps = 24.0
        self.update_time_label()
        self.rebuild_scene()
    
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
        
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Home:
            self.current_position = 0
            self.update_playhead()
            self.position_changed.emit(self.current_position)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_End:
            self.current_position = self.video_duration
            self.update_playhead()
            self.position_changed.emit(self.current_position)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Left:
            self.current_position = max(0, self.current_position - 1)
            self.update_playhead()
            self.position_changed.emit(self.current_position)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Right:
            self.current_position = min(self.video_duration, self.current_position + 1)
            self.update_playhead()
            self.position_changed.emit(self.current_position)
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
        
        pps = self.pixels_per_second * self.zoom_scale
        duration = max(self.video_duration, 3600)  # Minimum 1 hour (feels infinite)
        total_width = int(duration * pps) + 100
        self.scene_duration = duration
        
        ruler_height = 25
        track_height = 40  # Taller tracks for 2-track layout
        total_height = ruler_height + 2 * track_height  # Only V1 and A1
        self.total_height = total_height
        self.track_clip_y = ruler_height + 2
        self.track_clip_h = track_height - 4
        
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
            x = int(t * pps)
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
            x = int(t * pps)
            
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
        
        # ===== Step Clips on V1 =====
        if self.tutorial and self.tutorial.steps:
            for i, step in enumerate(self.tutorial.steps):
                clip = self.scene.addRect(0, self.track_clip_y, 0, self.track_clip_h, QPen(), QBrush())
                clip.setData(0, i)
                clip.setFlag(clip.GraphicsItemFlag.ItemIsSelectable, True)
                text = self.scene.addText("", QFont("Arial", 9, QFont.Weight.Bold))
                text.setDefaultTextColor(QColor(255, 255, 255))
                self.step_rect_items[i] = clip
                self.step_text_items[i] = text
                self._update_step_item(i)

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
        x = int(step.timestamp * pps)

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
        playhead_x = int(self.current_position * pps)
        self.playhead_line_item.setLine(playhead_x, 0, playhead_x, self.total_height)
        self.playhead_triangle_item.setPos(playhead_x, 0)
        
    def on_timeline_clicked(self, position):
        """Called when timeline is clicked."""
        self.current_position = max(0, min(position, self.video_duration))
        self.update_time_label()
        self.position_changed.emit(self.current_position)
        self.update_playhead()
            
    def update_time_label(self):
        # Time label was removed - just update zoom label if needed
        pass
        
    def format_time(self, seconds):
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"
        
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
            playhead_x = int(self.current_position * pps)
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
            # Use strict integer conversion for PySide6 compatibility
            key_int = event.key()
            mod_int = int(event.modifiers())
            return QKeySequence(key_int | mod_int) == settings.get_key(action)
        
        if matches("toggle_play"):
            self.toggle_play()
            event.accept()
        elif matches("frame_start"):
            # Go to start
            self.current_position = 0
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            event.accept()
        elif matches("frame_end"):
            # Go to end
            self.current_position = self.video_duration
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            event.accept()
        elif matches("frame_prev"):
            # Move back 1 second
            self.current_position = max(0, self.current_position - 1.0)
            self.position_changed.emit(self.current_position)
            self.update_playhead()
            event.accept()
        elif matches("frame_next"):
            # Move forward 1 second
            self.current_position = min(self.video_duration, self.current_position + 1.0)
            self.position_changed.emit(self.current_position)
            self.update_playhead()
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
        self.drag_start_x = 0
        self.drag_original_timestamp = 0
        
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
        pps = self.timeline_widget.pixels_per_second * self.timeline_widget.zoom_scale
        
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on a step clip
            item = self.itemAt(event.position().toPoint())
            if item and item.data(0) is not None:
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
                self.timeline_widget.refresh_step_items()
                position = scene_pos.x() / pps
                self.timeline_widget.on_timeline_clicked(position)
                
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        if self.dragging_step is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            pps = self.timeline_widget.pixels_per_second * self.timeline_widget.zoom_scale
            
            # Calculate new timestamp
            new_timestamp = max(0, scene_pos.x() / pps)
            
            # Update step timestamp
            if 0 <= self.dragging_step < len(self.timeline_widget.tutorial.steps):
                self.timeline_widget.tutorial.steps[self.dragging_step].timestamp = new_timestamp
                self.timeline_widget._update_step_item(self.dragging_step)
                
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        if self.dragging_step is not None:
            # Re-sort steps by timestamp after drag
            self.timeline_widget.tutorial.steps.sort(key=lambda s: s.timestamp)
            self.timeline_widget.rebuild_scene()
            
            # Emit reordered signal so Editor can refresh list
            self.timeline_widget.steps_reordered.emit()
            
            self.dragging_step = None
            
        super().mouseReleaseEvent(event)
        
    def show_step_context_menu(self, pos):
        scene_pos = self.mapToScene(pos)
        pps = self.timeline_widget.pixels_per_second * self.timeline_widget.zoom_scale
        
        menu = QMenu(self)
        
        # Check if right-clicked on a step
        item = self.itemAt(pos)
        step_idx = item.data(0) if item and item.data(0) is not None else None
        
        if step_idx is not None and 0 <= step_idx < len(self.timeline_widget.tutorial.steps):
            step = self.timeline_widget.tutorial.steps[step_idx]
            
            # Select the step
            self.timeline_widget.selected_step_index = step_idx
            self.timeline_widget.step_selected.emit(step_idx)
            self.timeline_widget.refresh_step_items()
            
            # Step info header
            menu.addAction(f"📍 Step {step_idx + 1}: {step.description[:20]}...").setEnabled(False)
            menu.addSeparator()
            
            # Edit action - select in steps list
            edit_action = menu.addAction("✏️ Edit Properties")
            edit_action.triggered.connect(lambda: self.timeline_widget.step_selected.emit(step_idx))
            
            menu.addSeparator()
            
            # Copy
            copy_action = menu.addAction("📋 Copy")
            copy_action.triggered.connect(lambda: self.copy_step(step_idx))
            
            # Duplicate
            duplicate_action = menu.addAction("📑 Duplicate")
            duplicate_action.triggered.connect(lambda: self.duplicate_step(step_idx))
            
            menu.addSeparator()
            
            # Move left/right
            if step_idx > 0:
                move_left = menu.addAction("⬅️ Move Earlier")
                move_left.triggered.connect(lambda: self.move_step(step_idx, -0.5))
            
            move_right = menu.addAction("➡️ Move Later")
            move_right.triggered.connect(lambda: self.move_step(step_idx, 0.5))
            
            menu.addSeparator()
            
            # Delete
            delete_action = menu.addAction("🗑️ Delete")
            delete_action.triggered.connect(lambda: self.delete_step(step_idx))
            
        else:
            # Right-clicked on empty area
            current_position = scene_pos.x() / pps
            
            # Add new step
            add_click = menu.addAction("🖱️ Add Click Step Here")
            # Add new step
            add_click = menu.addAction("🖱️ Add Click Step Here")
            add_click.triggered.connect(lambda: self.timeline_widget.step_added_with_type.emit(current_position, "click"))
            
            add_keyboard = menu.addAction("⌨️ Add Keyboard Step Here")
            add_keyboard = menu.addAction("⌨️ Add Keyboard Step Here")
            add_keyboard.triggered.connect(lambda: self.timeline_widget.step_added_with_type.emit(current_position, "keyboard"))
            
            if self.clipboard_step:
                menu.addSeparator()
                paste_action = menu.addAction("📋 Paste Step")
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



class Editor(QMainWindow):
    def __init__(self, tutorial: Tutorial):
        super().__init__()
        self.tutorial = tutorial
        self.video_cap = None
        
        # Undo/Redo History
        self.history_stack = []  # List of tutorial state snapshots
        self.history_index = -1  # Current position in history
        self.max_history = 50    # Maximum history size
        
        self.init_ui()
        self.save_state()  # Save initial state

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
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.clicked.connect(self.duplicate_current_step)
        self.btn_duplicate.setStyleSheet("QPushButton { background: #0078D4; color: white; border: none; padding: 5px; border-radius: 4px; } QPushButton:hover { background: #106EBE; }")
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_current_step)
        self.btn_delete.setStyleSheet("QPushButton { background: #D93025; color: white; border: none; padding: 5px; border-radius: 4px; } QPushButton:hover { background: #C5221F; }")
        
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
        
        props_widget = QWidget()
        props_layout = QFormLayout(props_widget)
        
        self.desc_input = QLineEdit()
        self.desc_input.textChanged.connect(self.update_desc_preview)
        self.desc_input.editingFinished.connect(self.save_state)
        props_layout.addRow("Description:", self.desc_input)
        
        # Instruction (multi-line detailed guidance)
        self.instruction_input = QTextEdit()
        self.instruction_input.setPlaceholderText("Enter step-by-step instruction here...")
        self.instruction_input.setMaximumHeight(80)
        self.instruction_input.textChanged.connect(self.update_instruction_preview)
        self.instruction_input.setTabChangesFocus(True)
        props_layout.addRow("Instruction:", self.instruction_input)
        
        # Sound Checkbox
        self.chk_sound = QCheckBox("Enable Click Sound")
        self.chk_sound.toggled.connect(self.update_sound)
        props_layout.addRow("", self.chk_sound)
        
        # Text Input (for keyboard steps)
        from PySide6.QtWidgets import QComboBox, QSpinBox
        self.keyboard_mode_combo = QComboBox()
        self.keyboard_mode_combo.addItem("Text Input", "text")
        self.keyboard_mode_combo.addItem("Key Input", "key")
        self.keyboard_mode_combo.currentIndexChanged.connect(self.update_keyboard_mode)
        props_layout.addRow("Input Type:", self.keyboard_mode_combo)

        self.text_content = QLineEdit()
        self.text_content.setPlaceholderText("Expected keyboard input")
        self.text_content.textChanged.connect(self.update_keyboard_input_preview)
        self.text_content.editingFinished.connect(self.save_state)
        props_layout.addRow("Expected Input:", self.text_content)
        
        # ==================== Text Style Section ====================
        props_layout.addRow(QLabel(""))  # Spacer
        text_style_label = QLabel("── Text Style ──")
        text_style_label.setStyleSheet("font-weight: bold; color: #888;")
        props_layout.addRow(text_style_label)
        
        # Font Family Dropdown (all system fonts)
        from PySide6.QtGui import QFontDatabase
        self.font_family_combo = QComboBox()
        font_families = QFontDatabase.families()
        self.font_family_combo.addItems(font_families)
        # Set default to Arial if available
        arial_idx = self.font_family_combo.findText("Arial")
        if arial_idx >= 0:
            self.font_family_combo.setCurrentIndex(arial_idx)
        self.font_family_combo.currentTextChanged.connect(self.update_text_style_preview)
        props_layout.addRow("Font:", self.font_family_combo)
        
        # Font Size with SpinBox (up/down buttons)
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setMinimum(8)
        self.font_size_spinbox.setMaximum(200)
        self.font_size_spinbox.setValue(24)
        self.font_size_spinbox.setSuffix(" pt")
        self.font_size_spinbox.valueChanged.connect(self.update_text_style_preview)
        props_layout.addRow("Font Size:", self.font_size_spinbox)
        
        # Font Weight Dropdown
        self.font_weight_combo = QComboBox()
        self.font_weight_combo.addItems(["Normal", "Bold"])
        self.font_weight_combo.currentTextChanged.connect(self.update_text_style_preview)
        props_layout.addRow("Font Weight:", self.font_weight_combo)
        
        # Text Color with preview
        text_color_layout = QHBoxLayout()
        self.text_color_input = QLineEdit()
        self.text_color_input.setPlaceholderText("#FFFFFF")
        self.text_color_input.textChanged.connect(self.update_text_style_preview)
        self.text_color_input.editingFinished.connect(self.save_state)
        self.text_color_preview = QLabel()
        self.text_color_preview.setFixedSize(24, 24)
        self.text_color_preview.setStyleSheet("background: #FFFFFF; border: 1px solid #555; border-radius: 3px;")
        self.text_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.text_color_preview.mousePressEvent = lambda e: self.pick_text_color()
        text_color_layout.addWidget(self.text_color_input)
        text_color_layout.addWidget(self.text_color_preview)
        props_layout.addRow("Text Color:", text_color_layout)
        
        # Background Color with preview
        bg_color_layout = QHBoxLayout()
        self.bg_color_input = QLineEdit()
        self.bg_color_input.setPlaceholderText("#000000")
        self.bg_color_input.textChanged.connect(self.update_text_style_preview)
        self.bg_color_input.editingFinished.connect(self.save_state)
        self.bg_color_preview = QLabel()
        self.bg_color_preview.setFixedSize(24, 24)
        self.bg_color_preview.setStyleSheet("background: #000000; border: 1px solid #555; border-radius: 3px;")
        self.bg_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_color_preview.mousePressEvent = lambda e: self.pick_bg_color()
        bg_color_layout.addWidget(self.bg_color_input)
        bg_color_layout.addWidget(self.bg_color_preview)
        props_layout.addRow("Bg Color:", bg_color_layout)
        
        # ==================== Hitbox Style Section ====================
        props_layout.addRow(QLabel(""))  # Spacer
        hitbox_style_label = QLabel("── Hitbox Style ──")
        hitbox_style_label.setStyleSheet("font-weight: bold; color: #888;")
        props_layout.addRow(hitbox_style_label)
        
        # Shape Selection (moved into Hitbox Style)
        self.shape_group = QButtonGroup(self)
        self.radio_rect = QRadioButton("Rectangle")
        self.radio_circle = QRadioButton("Circle")
        self.shape_group.addButton(self.radio_rect)
        self.shape_group.addButton(self.radio_circle)
        shape_layout = QHBoxLayout()
        shape_layout.addWidget(self.radio_rect)
        shape_layout.addWidget(self.radio_circle)
        props_layout.addRow("Shape:", shape_layout)
        self.radio_rect.toggled.connect(self.update_shape)
        self.radio_circle.toggled.connect(self.update_shape)
        
        # Line Width Slider
        hitbox_width_layout = QHBoxLayout()
        self.hitbox_line_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.hitbox_line_width_slider.setMinimum(1)
        self.hitbox_line_width_slider.setMaximum(10)
        self.hitbox_line_width_slider.setValue(2)
        self.hitbox_line_width_slider.valueChanged.connect(self.update_hitbox_line_width)
        self.hitbox_line_width_label = QLabel("2")
        hitbox_width_layout.addWidget(self.hitbox_line_width_slider)
        hitbox_width_layout.addWidget(self.hitbox_line_width_label)
        props_layout.addRow("Line Width:", hitbox_width_layout)
        
        # Line Style Dropdown
        self.hitbox_line_style_combo = QComboBox()
        self.hitbox_line_style_combo.addItems(["solid", "dashed", "dotted"])
        self.hitbox_line_style_combo.currentTextChanged.connect(self.update_hitbox_line_style)
        props_layout.addRow("Line Style:", self.hitbox_line_style_combo)
        
        # Line Color Input with preview
        line_color_layout = QHBoxLayout()
        self.hitbox_line_color_input = QLineEdit()
        self.hitbox_line_color_input.setPlaceholderText("#FF0000")
        self.hitbox_line_color_input.textChanged.connect(self.update_hitbox_line_color)
        self.hitbox_line_color_input.editingFinished.connect(self.save_state)
        self.hitbox_line_color_preview = QLabel()
        self.hitbox_line_color_preview.setFixedSize(24, 24)
        self.hitbox_line_color_preview.setStyleSheet("background: #FF0000; border: 1px solid #555; border-radius: 3px;")
        self.hitbox_line_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hitbox_line_color_preview.mousePressEvent = lambda e: self.pick_hitbox_line_color()
        line_color_layout.addWidget(self.hitbox_line_color_input)
        line_color_layout.addWidget(self.hitbox_line_color_preview)
        props_layout.addRow("Line Color:", line_color_layout)
        
        # Fill Color Input with preview (with alpha)
        fill_color_layout = QHBoxLayout()
        self.hitbox_fill_color_input = QLineEdit()
        self.hitbox_fill_color_input.setPlaceholderText("#FF0000")
        self.hitbox_fill_color_input.textChanged.connect(self.update_hitbox_fill_color)
        self.hitbox_fill_color_input.editingFinished.connect(self.save_state)
        self.hitbox_fill_color_preview = QLabel()
        self.hitbox_fill_color_preview.setFixedSize(24, 24)
        self.hitbox_fill_color_preview.setStyleSheet("background: rgba(255, 0, 0, 0.2); border: 1px solid #555; border-radius: 3px;")
        self.hitbox_fill_color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hitbox_fill_color_preview.mousePressEvent = lambda e: self.pick_hitbox_fill_color()
        fill_color_layout.addWidget(self.hitbox_fill_color_input)
        fill_color_layout.addWidget(self.hitbox_fill_color_preview)
        props_layout.addRow("Fill Color:", fill_color_layout)
        
        # Fill Opacity Slider
        fill_opacity_layout = QHBoxLayout()
        self.hitbox_fill_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.hitbox_fill_opacity_slider.setMinimum(0)
        self.hitbox_fill_opacity_slider.setMaximum(100)
        self.hitbox_fill_opacity_slider.setValue(20)  # Default 20%
        self.hitbox_fill_opacity_slider.valueChanged.connect(self.update_hitbox_fill_opacity)
        self.hitbox_fill_opacity_label = QLabel("20%")
        fill_opacity_layout.addWidget(self.hitbox_fill_opacity_slider)
        fill_opacity_layout.addWidget(self.hitbox_fill_opacity_label)
        props_layout.addRow("Fill Opacity:", fill_opacity_layout)
        
        # ==================== Audio Section ====================
        props_layout.addRow(QLabel(""))  # Spacer
        audio_section_label = QLabel("── Audio ──")
        audio_section_label.setStyleSheet("font-weight: bold; color: #888;")
        props_layout.addRow(audio_section_label)
        
        # Audio File Display
        audio_file_layout = QHBoxLayout()
        self.audio_file_label = QLabel("No audio loaded")
        self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
        audio_file_layout.addWidget(self.audio_file_label, 1)
        
        # Import Audio Button
        self.import_audio_btn = QPushButton("📁")
        self.import_audio_btn.setToolTip("Import Audio File")
        self.import_audio_btn.setFixedWidth(30)
        self.import_audio_btn.clicked.connect(self.import_audio)
        audio_file_layout.addWidget(self.import_audio_btn)
        
        # Remove Audio Button
        self.remove_audio_btn = QPushButton("❌")
        self.remove_audio_btn.setToolTip("Remove Audio")
        self.remove_audio_btn.setFixedWidth(30)
        self.remove_audio_btn.clicked.connect(self.remove_audio)
        self.remove_audio_btn.setEnabled(False)
        audio_file_layout.addWidget(self.remove_audio_btn)
        
        props_layout.addRow("Audio File:", audio_file_layout)
        
        # Audio Offset Slider (-10 to +10 seconds)
        offset_layout = QHBoxLayout()
        self.audio_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_offset_slider.setMinimum(-100)  # -10 seconds (in 0.1s steps)
        self.audio_offset_slider.setMaximum(100)   # +10 seconds
        self.audio_offset_slider.setValue(0)
        self.audio_offset_slider.valueChanged.connect(self.update_audio_offset)
        self.audio_offset_label = QLabel("0.0s")
        self.audio_offset_label.setMinimumWidth(40)
        offset_layout.addWidget(self.audio_offset_slider)
        offset_layout.addWidget(self.audio_offset_label)
        props_layout.addRow("Sync Offset:", offset_layout)
        
        self.props_dock.setWidget(props_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_dock)
        
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

    def _sync_audio_ui(self):
        """Synchronize audio controls with the current tutorial state."""
        if self.tutorial.audio_path:
            filename = os.path.basename(self.tutorial.audio_path)
            self.audio_file_label.setText(filename)
            self.audio_file_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_audio_btn.setEnabled(True)
        else:
            self.audio_file_label.setText("No audio loaded")
            self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
            self.remove_audio_btn.setEnabled(False)

        self.audio_offset_slider.blockSignals(True)
        self.audio_offset_slider.setValue(int(round(self.tutorial.audio_offset * 10)))
        self.audio_offset_slider.blockSignals(False)
        self.audio_offset_label.setText(f"{self.tutorial.audio_offset:+.1f}s")

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
            self.step_list.setCurrentRow(index)

        item = self.step_list.item(index)
        if item is not None:
            item.setSelected(True)

        self.timeline.selected_step_index = index
        self.timeline.refresh_step_items()
        self.load_step(index)

    def load_step(self, index):
        if index < 0 or index >= len(self.tutorial.steps):
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
        if is_keyboard:
            self.text_content.setPlaceholderText(
                "Literal text to type"
                if step.keyboard_mode == "text"
                else "Key name like esc, enter, f5, left"
            )
        
        self.font_size_spinbox.blockSignals(True)
        self.font_size_spinbox.setValue(step.text_font_size)
        self.font_size_spinbox.blockSignals(False)
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
                if step.action_type == "keyboard" and step.keyboard_mode == "key" and text:
                    step.description = f"Press {display_key_name(text)}"
        
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

        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                if step.action_type != "keyboard":
                    continue
                step.keyboard_mode = mode
                if mode == "key" and step.keyboard_input:
                    step.description = f"Press {display_key_name(step.keyboard_input)}"
                elif mode == "text" and step.description.startswith("Press "):
                    step.description = "Type text"

        self.refresh_ui()
        self.canvas.update()
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
        
        text_color = self.text_color_input.text() or "#FFFFFF"
        bg_color = self.bg_color_input.text() or "#000000"
        
        for idx in selected:
            if 0 <= idx < len(self.tutorial.steps):
                step = self.tutorial.steps[idx]
                step.text_font_size = font_size
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
            filename = os.path.basename(audio_path)
            self.audio_file_label.setText(filename)
            self.audio_file_label.setStyleSheet("color: #0a0; font-style: normal;")
            self.remove_audio_btn.setEnabled(True)
            self.save_state()
            print(f"Imported audio: {audio_path}")
    
    def remove_audio(self):
        """Remove the audio file from the tutorial."""
        self.tutorial.audio_path = None
        self.tutorial.audio_offset = 0.0
        self.audio_file_label.setText("No audio loaded")
        self.audio_file_label.setStyleSheet("color: #666; font-style: italic;")
        self.remove_audio_btn.setEnabled(False)
        self.audio_offset_slider.setValue(0)
        self.save_state()
        print("Audio removed")
    
    def update_audio_offset(self, value):
        """Update the audio sync offset."""
        offset_seconds = value / 10.0  # Slider value is in 0.1s units
        self.audio_offset_label.setText(f"{offset_seconds:+.1f}s")
        self.tutorial.audio_offset = offset_seconds
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
                self._frame_update_timer = QTimer()
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
            'video_path': self.tutorial.video_path,
            'audio_path': self.tutorial.audio_path,
            'audio_offset': self.tutorial.audio_offset,
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
        self.tutorial.video_path = state['video_path']
        self.tutorial.audio_path = state.get('audio_path')
        self.tutorial.audio_offset = state.get('audio_offset', 0.0)
        self._sync_audio_ui()
        self.refresh()
        self.timeline.update()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        from ..settings import Settings
        settings = Settings()
        
        # Helper matches function (could be utility, but inline is fine)
        def matches(action):
            # Use strict integer conversion for PySide6 compatibility
            key_int = event.key()
            mod_int = int(event.modifiers())
            return QKeySequence(key_int | mod_int) == settings.get_key(action)
        
        # Undo/Redo
        if matches("undo"):
            self.undo()
            return
        elif matches("redo"):
            self.redo()
            return
        
        super().keyPressEvent(event)
