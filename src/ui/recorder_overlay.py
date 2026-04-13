from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QAction
from ..recorder import Recorder
from ..settings import Settings

class RecorderOverlay(QWidget):
    stop_signal = Signal()
    
    def __init__(self, recorder: Recorder):
        super().__init__()
        self.recorder = recorder
        self.recorder.overlay = self
        self.blink_state = True
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Recorder")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Position at center-top of screen
        screen = QApplication.primaryScreen().geometry()
        
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(8)
        
        # Recording indicator (red circle)
        self.rec_indicator = QLabel("●")
        self.rec_indicator.setFont(QFont("Arial", 16))
        layout.addWidget(self.rec_indicator)
        
        # REC text
        self.rec_label = QLabel()
        self.rec_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.rec_label.setStyleSheet("color: white;")
        layout.addWidget(self.rec_label)
        
        self.setLayout(layout)
        
        # Blink timer
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.blink)
        
        # Click to stop
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Show start state
        self.show_ready_state()
        self.setup_shortcut()

    def setup_shortcut(self):
        shortcut = Settings().get_key("toggle_recording")
        if shortcut.isEmpty():
            return

        self.toggle_action = QAction(self)
        self.toggle_action.setShortcut(shortcut)
        self.toggle_action.triggered.connect(self.toggle_recording)
        self.addAction(self.toggle_action)
    
    def show_ready_state(self):
        """Show 'Click to Record' state."""
        self.rec_indicator.setStyleSheet("color: #888888;")
        self.rec_label.setText("Click or press shortcut to record")
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.85); border-radius: 18px;")
        self.adjustSize()
        
        # Position at bottom center (overlapping taskbar)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - self.width() // 2, screen.height() - self.height() - 10)
        self.setFocus()
        self.activateWindow()
    
    def show_recording_state(self):
        """Show minimal REC indicator with transparency."""
        self.rec_indicator.setStyleSheet("color: #ff4444;")
        self.rec_label.setText("REC")
        # More transparent during recording
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.5); border-radius: 18px;")
        self.adjustSize()
        
        # Position at bottom center (overlapping taskbar)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - self.width() // 2, screen.height() - self.height() - 10)
        
        # Start blinking
        self.blink_timer.start(500)
    
    def blink(self):
        """Blink the red indicator."""
        self.blink_state = not self.blink_state
        if self.blink_state:
            self.rec_indicator.setStyleSheet("color: #ff4444;")
        else:
            self.rec_indicator.setStyleSheet("color: #660000;")
            
        # Enforce visibility and top-most status
        self.raise_()
        if not self.isVisible():
            self.show()
    
    def mousePressEvent(self, event):
        """Click to toggle recording."""
        self.toggle_recording()
    
    def toggle_recording(self):
        if not self.recorder.is_recording:
            # Show countdown before recording
            self.hide()
            self.show_countdown()
        else:
            # Click to stop
            self.blink_timer.stop()
            self.recorder.stop()
            self.stop_signal.emit()
            self.close()
    
    def show_countdown(self):
        """Show 3-2-1 countdown before starting recording."""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtGui import QFont
        
        self.countdown_widget = QLabel("3")
        self.countdown_widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.countdown_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.countdown_widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.countdown_widget.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 150);
                border-radius: 100px;
                padding: 50px;
            }
        """)
        self.countdown_widget.setFont(QFont("Arial", 120, QFont.Weight.Bold))
        self.countdown_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_widget.setFixedSize(250, 250)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.countdown_widget.move(
            screen.width() // 2 - 125,
            screen.height() // 2 - 125
        )
        self.countdown_widget.show()
        
        self.countdown_value = 3
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._countdown_tick)
        self.countdown_timer.start(1000)
    
    def _countdown_tick(self):
        """Handle countdown tick."""
        self.countdown_value -= 1
        
        if self.countdown_value > 0:
            self.countdown_widget.setText(str(self.countdown_value))
        elif self.countdown_value == 0:
            self.countdown_widget.setText("●")
            self.countdown_widget.setStyleSheet("""
                QLabel {
                    color: #FF4444;
                    background-color: rgba(0, 0, 0, 150);
                    border-radius: 100px;
                    padding: 50px;
                }
            """)
        else:
            self.countdown_timer.stop()
            self.countdown_widget.close()
            
            # Start recording
            self.recorder.start()
            self.show_recording_state()
            self.show()
    
    def hide_for_capture(self):
        self.hide()
        QApplication.processEvents()
    
    def show_after_capture(self):
        self.show()
        QApplication.processEvents()



