import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QStackedWidget, QMessageBox, QFileDialog, QLabel, QMenu)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QAction
from ..model import Tutorial
from ..recorder import Recorder
from ..recorder import AUDIO_AVAILABLE
from ..settings import Settings
from .recorder_overlay import RecorderOverlay
from .editor import Editor
# Player will be imported later when ready


class CountdownOverlay(QWidget):
    """Fullscreen countdown overlay (3-2-1) before recording starts."""
    
    countdown_finished = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.showFullScreen()
        
        self.count = 3
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Countdown label
        self.label = QLabel("3")
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 150);
                border-radius: 100px;
                padding: 50px;
            }
        """)
        self.label.setFont(QFont("Arial", 120, QFont.Weight.Bold))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedSize(250, 250)
        layout.addWidget(self.label)
        
        # Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
    
    def tick(self):
        self.count -= 1
        if self.count > 0:
            self.label.setText(str(self.count))
        elif self.count == 0:
            self.label.setText("●")
            self.label.setStyleSheet("""
                QLabel {
                    color: #FF4444;
                    background-color: rgba(0, 0, 0, 150);
                    border-radius: 100px;
                    padding: 50px;
                }
            """)
        else:
            self.timer.stop()
            self.close()
            self.countdown_finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tutorial = Tutorial(title="New TutoMake")
        self.recorder = None
        self.setWindowTitle("TutoMake")
        self.resize(1200, 800)
        
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Toolbar / Control Panel
        control_panel = QHBoxLayout()
        
        btn_new = QPushButton("📄 New")
        btn_new.clicked.connect(self.new_tutorial)
        control_panel.addWidget(btn_new)

        btn_save = QPushButton("💾 Save")
        btn_save.clicked.connect(self.save_tutorial)
        control_panel.addWidget(btn_save)

        btn_load = QPushButton("📂 Load")
        btn_load.clicked.connect(self.load_tutorial)
        control_panel.addWidget(btn_load)

        self.btn_record = QPushButton("🔴 Record")
        self.btn_record.clicked.connect(self.start_recording_mode)
        control_panel.addWidget(self.btn_record)
        
        self.btn_play = QPushButton("▶️ Play")
        self.btn_play.clicked.connect(self.play_tutorial)
        control_panel.addWidget(self.btn_play)

        # Export button with dropdown menu
        self.btn_export = QPushButton("📤 Export")
        self.export_menu = QMenu(self)
        
        # Video exports
        self.export_menu.addAction("🎬 MP4 Video", self.export_mp4)
        self.export_menu.addAction("🎞️ GIF Animation", self.export_gif)
        self.export_menu.addAction("📹 WebM Video", self.export_webm)
        self.export_menu.addAction("🎥 AVI Video", self.export_avi)
        self.export_menu.addSeparator()
        
        # Document exports
        self.export_menu.addAction("📕 PDF Guide", self.export_pdf)
        self.export_menu.addAction("📊 PowerPoint", self.export_pptx)
        self.export_menu.addAction("📝 Markdown", self.export_markdown)
        self.export_menu.addAction("🖼️ PNG Sequence", self.export_png)
        self.export_menu.addSeparator()
        
        # Web exports
        self.export_menu.addAction("🌐 HTML Webpage", self.export_html)
        self.export_menu.addAction("🎥 HTML + Video", self.export_video_html)
        self.export_menu.addAction("📦 Web Embed (JS)", self.export_iframe)
        self.export_menu.addAction("✨ Lottie Animation", self.export_lottie)
        self.export_menu.addSeparator()
        
        # Package exports
        self.export_menu.addAction("📚 SCORM Package", self.export_scorm)
        self.export_menu.addAction("💼 Portable Package", self.export_portable)
        
        self.btn_export.setMenu(self.export_menu)
        
        # Dynamically match menu width to button when shown
        def update_menu_width():
            self.export_menu.setMinimumWidth(self.btn_export.width())
        self.export_menu.aboutToShow.connect(update_menu_width)
        
        self.export_menu.setStyleSheet("""
            QMenu {
                padding: 5px;
            }
            QMenu::item {
                padding: 4px 20px 4px 10px;
            }
        """)
        control_panel.addWidget(self.btn_export)
        
        # Theme toggle button
        from . import styles
        self.btn_theme = QPushButton(styles.get_theme_icon())
        self.btn_theme.clicked.connect(self.toggle_theme)
        control_panel.addWidget(self.btn_theme)

        self.btn_view = QPushButton("View")
        self.btn_view.setToolTip("Show or hide property sections")
        control_panel.addWidget(self.btn_view)

        # Settings Button
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setToolTip("Settings / Shortcuts")
        self.btn_settings.clicked.connect(self.open_settings)
        control_panel.addWidget(self.btn_settings)

        main_layout.addLayout(control_panel)

        # Apply initial theme
        self.apply_theme()

        # Content Area (Stacked Widget)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # View 1: Editor (Default)
        self.editor = Editor(self.tutorial)
        self.stack.addWidget(self.editor)
        
        # View 2: Player (To be added)
        # self.player = Player(self.tutorial)
        # self.stack.addWidget(self.player)

        self._setup_shortcuts()
        self._setup_view_button()

    def _setup_shortcuts(self):
        settings = Settings()
        shortcut = settings.get_key("toggle_recording")
        if shortcut.isEmpty():
            return

        self.record_shortcut_action = QAction(self)
        self.record_shortcut_action.setShortcut(shortcut)
        self.record_shortcut_action.triggered.connect(self.handle_record_shortcut)
        self.addAction(self.record_shortcut_action)

    def handle_record_shortcut(self):
        if self.isHidden() or self.isMinimized():
            return
        self.start_recording_mode()

    def _setup_view_button(self):
        self.view_menu = QMenu(self)
        self.property_section_actions = {}

        for key, title in self.editor.get_property_sections().items():
            action = QAction(title, self, checkable=True)
            action.setChecked(self.editor.is_property_section_visible(key))
            action.toggled.connect(
                lambda checked, section_key=key: self.editor.set_property_section_visible(section_key, checked)
            )
            self.view_menu.addAction(action)
            self.property_section_actions[key] = action

        self.btn_view.setMenu(self.view_menu)

    def _refresh_view_menu_labels(self):
        if not hasattr(self, "property_section_actions"):
            return
        section_titles = self.editor.get_property_sections()
        for key, action in self.property_section_actions.items():
            if key in section_titles:
                action.setText(section_titles[key])

    def new_tutorial(self):
        self.tutorial = Tutorial()
        self.refresh_editor()

    def save_tutorial(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Tutorial", "", "TutoMake Files (*.tutomake)")
        if filepath:
            if not filepath.endswith('.tutomake'):
                filepath += '.tutomake'
            self.tutorial.save(filepath)
            QMessageBox.information(self, "Success", "Tutorial saved!")

    def load_tutorial(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Tutorial", "", "TutoMake Files (*.tutomake);;JSON Files (*.json)")
        if filepath:
            try:
                self.tutorial = Tutorial.load(filepath)
                self.refresh_editor()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def start_recording_mode(self):
        if not AUDIO_AVAILABLE:
            QMessageBox.warning(
                self,
                "Audio Input Unavailable",
                "sounddevice is not installed, so microphone selection and audio recording are disabled.",
            )

        # Minimize main window
        self.showMinimized()
        
        # Initialize recorder - always use video mode
        storage_dir = os.path.join(os.getcwd(), "captures")
        selected_device, selected_name = self.editor.get_selected_audio_input()
        self.recorder = Recorder(
            self.tutorial,
            storage_dir,
            video_mode=True,
            audio_device=selected_device,
            audio_device_name=selected_name,
        )
        
        # Show overlay (countdown will be triggered from RecorderOverlay)
        self.overlay = RecorderOverlay(self.recorder)
        self.overlay.stop_signal.connect(self.on_recording_finished)
        self.overlay.show()

    def on_recording_finished(self):
        self.showNormal()
        self.refresh_editor()
        
        msg = f"Recording finished. captured {len(self.tutorial.steps)} steps."
        if self.recorder and self.recorder.record_audio:
            msg += f"\nAudio input: {self.recorder.audio_device_name}"
        if hasattr(self.recorder, 'last_recording_stats'):
            msg += f"\n\nPerformance:\n{self.recorder.last_recording_stats}"
            
        QMessageBox.information(self, "Done", msg)

    def refresh_editor(self):
        self.editor.set_tutorial(self.tutorial)

    def play_tutorial(self):
        from .player import Player
        
        # Check which mode is selected in editor
        use_video_mode = self.editor.view_mode == "video"
        
        self.player_window = Player(self.tutorial, video_mode=use_video_mode)
        
        # Connect closed signal to restore main window
        self.player_window.closed.connect(self.on_player_closed)
        
        # Hide main window to prevent obstruction
        self.hide()
        
        self.player_window.showFullScreen()
        
    def on_player_closed(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ==================== Export Methods ====================
    
    def _get_export_path(self, title: str, filter: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, title, "", filter)
        return path
    
    def _get_export_dir(self, title: str) -> str:
        return QFileDialog.getExistingDirectory(self, title)
    
    def _run_export_with_progress(self, export_func, path, description: str):
        """Run export function with a progress dialog."""
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import Qt
        import threading
        
        progress = QProgressDialog(description, None, 0, 0, self)
        progress.setWindowTitle("Exporting...")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # No cancel
        progress.show()
        
        # Process events to show dialog immediately
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        
        result = False
        error = None
        
        def run_export():
            nonlocal result, error
            try:
                result = export_func(path)
            except Exception as e:
                error = str(e)
        
        # Run in thread
        thread = threading.Thread(target=run_export)
        thread.start()
        
        while thread.is_alive():
            QCoreApplication.processEvents()
            thread.join(0.1)
        
        progress.close()
        
        if error:
            QMessageBox.critical(self, "Export Error", f"Failed: {error}")
        elif result:
            QMessageBox.information(self, "Success", f"Exported to {path}")
        else:
            QMessageBox.warning(self, "Export Failed", "Export failed. Check console for details.")
    
    def export_mp4(self):
        path = self._get_export_path("Export MP4", "MP4 Video (*.mp4)")
        if path:
            from ..exporters.video_exporter import VideoExporter
            exporter = VideoExporter(self.tutorial)
            self._run_export_with_progress(exporter.export_mp4, path, "Exporting MP4 video...")
    
    def export_gif(self):
        path = self._get_export_path("Export GIF", "GIF Animation (*.gif)")
        if path:
            from ..exporters.video_exporter import VideoExporter
            exporter = VideoExporter(self.tutorial)
            if exporter.export_gif(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_webm(self):
        path = self._get_export_path("Export WebM", "WebM Video (*.webm)")
        if path:
            from ..exporters.video_exporter import VideoExporter
            exporter = VideoExporter(self.tutorial)
            if exporter.export_webm(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_avi(self):
        path = self._get_export_path("Export AVI", "AVI Video (*.avi)")
        if path:
            from ..exporters.video_exporter import VideoExporter
            exporter = VideoExporter(self.tutorial)
            if exporter.export_avi(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_pdf(self):
        path = self._get_export_path("Export PDF", "PDF Document (*.pdf)")
        if path:
            from ..exporters.document_exporter import DocumentExporter
            exporter = DocumentExporter(self.tutorial)
            if exporter.export_pdf(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_pptx(self):
        path = self._get_export_path("Export PowerPoint", "PowerPoint (*.pptx)")
        if path:
            from ..exporters.document_exporter import DocumentExporter
            exporter = DocumentExporter(self.tutorial)
            if exporter.export_pptx(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_markdown(self):
        path = self._get_export_path("Export Markdown", "Markdown (*.md)")
        if path:
            from ..exporters.document_exporter import DocumentExporter
            exporter = DocumentExporter(self.tutorial)
            if exporter.export_markdown(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_png(self):
        dir_path = self._get_export_dir("Export PNG Sequence")
        if dir_path:
            from ..exporters.document_exporter import DocumentExporter
            exporter = DocumentExporter(self.tutorial)
            if exporter.export_png_sequence(dir_path):
                QMessageBox.information(self, "Success", f"Exported to {dir_path}")
    
    def export_html(self):
        path = self._get_export_path("Export HTML", "HTML Webpage (*.html)")
        if path:
            from ..exporters.web_exporter import WebExporter
            exporter = WebExporter(self.tutorial)
            if exporter.export_html(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_video_html(self):
        if not self.tutorial.video_path:
            QMessageBox.warning(self, "No Video", "Video file is required for HTML + Video export")
            return
        path = self._get_export_path("Export HTML + Video", "HTML Webpage (*.html)")
        if path:
            from ..exporters.web_exporter import WebExporter
            exporter = WebExporter(self.tutorial)
            if exporter.export_video_html(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_iframe(self):
        path = self._get_export_path("Export Web Embed", "JavaScript (*.js)")
        if path:
            from ..exporters.web_exporter import WebExporter
            exporter = WebExporter(self.tutorial)
            if exporter.export_iframe_embed(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_lottie(self):
        path = self._get_export_path("Export Lottie", "Lottie JSON (*.json)")
        if path:
            from ..exporters.web_exporter import WebExporter
            exporter = WebExporter(self.tutorial)
            if exporter.export_lottie(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_scorm(self):
        path = self._get_export_path("Export SCORM", "SCORM Package (*.zip)")
        if path:
            from ..exporters.package_exporter import PackageExporter
            exporter = PackageExporter(self.tutorial)
            if exporter.export_scorm(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")
    
    def export_portable(self):
        path = self._get_export_path("Export Portable Package", "ZIP Archive (*.zip)")
        if path:
            from ..exporters.package_exporter import PackageExporter
            exporter = PackageExporter(self.tutorial)
            if exporter.create_portable_package(path):
                QMessageBox.information(self, "Success", f"Exported to {path}")

    # ==================== Theme Methods ====================
    
    def toggle_theme(self):
        """Toggle between dark and light theme."""
        from . import styles
        styles.toggle_theme()
        self.btn_theme.setText(styles.get_theme_icon())
        self.apply_theme()
    
    def apply_theme(self):
        """Apply current theme to all widgets."""
        from . import styles
        
        # Apply full stylesheet to main window
        self.setStyleSheet(styles.generate_full_stylesheet())
        
        # Apply to export menu
        self.export_menu.setStyleSheet(styles.generate_menu_stylesheet())
        
        # Refresh editor if it exists
        if hasattr(self, 'editor'):
            self.editor.setStyleSheet(styles.generate_full_stylesheet())
            # Update canvas and zoom controls theme
            if hasattr(self.editor, 'canvas'):
                self.editor.canvas.apply_theme()
            if hasattr(self.editor, 'zoom_controls'):
                self.editor.zoom_controls.apply_theme()

    def open_settings(self):
        """Open settings dialog."""
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        if dlg.exec():
            if hasattr(self, 'editor'):
                self.editor.retranslate_properties_panel()
            self._refresh_view_menu_labels()
