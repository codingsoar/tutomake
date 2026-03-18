"""
Theme System for TutoMake
Supports Dark Mode (black) and Light Mode (white) themes
"""


class DarkColors:
    """Dark mode color palette (black theme)"""
    # Background colors
    BG_PRIMARY = "#121212"
    BG_SECONDARY = "#1e1e1e"
    BG_TERTIARY = "#2d2d2d"
    BG_HOVER = "#3d3d3d"
    BG_SELECTED = "#404040"
    
    # Text colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#b3b3b3"
    TEXT_DISABLED = "#666666"
    
    # Accent colors
    ACCENT = "#0096FF"
    ACCENT_HOVER = "#33aaff"
    SUCCESS = "#4CAF50"
    WARNING = "#FF9800"
    ERROR = "#f44336"
    
    # Border colors
    BORDER = "#3d3d3d"
    BORDER_FOCUS = "#0096FF"
    
    # Input colors
    INPUT_BG = "#2d2d2d"
    INPUT_BORDER = "#404040"


class LightColors:
    """Light mode color palette (white theme)"""
    # Background colors
    BG_PRIMARY = "#ffffff"
    BG_SECONDARY = "#f5f5f5"
    BG_TERTIARY = "#e8e8e8"
    BG_HOVER = "#e0e0e0"
    BG_SELECTED = "#d0d0d0"
    
    # Text colors
    TEXT_PRIMARY = "#1a1a1a"
    TEXT_SECONDARY = "#666666"
    TEXT_DISABLED = "#999999"
    
    # Accent colors
    ACCENT = "#0078D4"
    ACCENT_HOVER = "#106EBE"
    SUCCESS = "#2E7D32"
    WARNING = "#F57C00"
    ERROR = "#C62828"
    
    # Border colors
    BORDER = "#d0d0d0"
    BORDER_FOCUS = "#0078D4"
    
    # Input colors
    INPUT_BG = "#ffffff"
    INPUT_BORDER = "#cccccc"


# Global theme state
_is_dark_mode = True


def toggle_theme():
    """Toggle between dark and light mode."""
    global _is_dark_mode
    _is_dark_mode = not _is_dark_mode
    return _is_dark_mode


def is_dark_mode():
    """Check if currently in dark mode."""
    return _is_dark_mode


def set_dark_mode(dark: bool):
    """Set theme mode directly."""
    global _is_dark_mode
    _is_dark_mode = dark


def get_current_theme():
    """Get current theme color class."""
    return DarkColors if _is_dark_mode else LightColors


def get_theme_icon():
    """Get icon for theme toggle button."""
    return "☀️ Light" if _is_dark_mode else "🌙 Dark"


# ==================== Stylesheet Generators ====================

def generate_main_window_stylesheet():
    """Generate stylesheet for main window."""
    c = get_current_theme()
    return f"""
        QMainWindow, QWidget {{
            background-color: {c.BG_PRIMARY};
            color: {c.TEXT_PRIMARY};
        }}
    """


def generate_button_stylesheet():
    """Generate stylesheet for buttons."""
    c = get_current_theme()
    return f"""
        QPushButton {{
            background-color: {c.BG_TERTIARY};
            color: {c.TEXT_PRIMARY};
            border: 1px solid {c.BORDER};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {c.BG_HOVER};
            border-color: {c.ACCENT};
        }}
        QPushButton:pressed {{
            background-color: {c.BG_SELECTED};
        }}
        QPushButton:disabled {{
            background-color: {c.BG_SECONDARY};
            color: {c.TEXT_DISABLED};
        }}
    """


def generate_accent_button_stylesheet():
    """Generate stylesheet for accent/primary buttons."""
    c = get_current_theme()
    return f"""
        QPushButton {{
            background-color: {c.ACCENT};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {c.ACCENT_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {c.ACCENT};
        }}
    """


def generate_input_stylesheet():
    """Generate stylesheet for input fields."""
    c = get_current_theme()
    return f"""
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {c.INPUT_BG};
            color: {c.TEXT_PRIMARY};
            border: 1px solid {c.INPUT_BORDER};
            border-radius: 4px;
            padding: 6px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {c.BORDER_FOCUS};
        }}
    """


def generate_list_stylesheet():
    """Generate stylesheet for list widgets."""
    c = get_current_theme()
    return f"""
        QListWidget {{
            background-color: {c.BG_SECONDARY};
            color: {c.TEXT_PRIMARY};
            border: 1px solid {c.BORDER};
            border-radius: 4px;
        }}
        QListWidget::item {{
            padding: 8px;
            border-bottom: 1px solid {c.BORDER};
        }}
        QListWidget::item:selected {{
            background-color: {c.BG_SELECTED};
            color: {c.TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: {c.BG_HOVER};
        }}
    """


def generate_label_stylesheet():
    """Generate stylesheet for labels."""
    c = get_current_theme()
    return f"""
        QLabel {{
            color: {c.TEXT_PRIMARY};
        }}
    """


def generate_panel_stylesheet():
    """Generate stylesheet for panels/frames."""
    c = get_current_theme()
    return f"""
        QFrame, QGroupBox {{
            background-color: {c.BG_SECONDARY};
            border: 1px solid {c.BORDER};
            border-radius: 8px;
        }}
        QGroupBox::title {{
            color: {c.TEXT_PRIMARY};
            font-weight: bold;
        }}
    """


def generate_menu_stylesheet():
    """Generate stylesheet for menus."""
    c = get_current_theme()
    return f"""
        QMenu {{
            background-color: {c.BG_SECONDARY};
            color: {c.TEXT_PRIMARY};
            border: 1px solid {c.BORDER};
            border-radius: 4px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 8px 20px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {c.BG_HOVER};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {c.BORDER};
            margin: 4px 0;
        }}
    """


def generate_scrollbar_stylesheet():
    """Generate stylesheet for scrollbars."""
    c = get_current_theme()
    return f"""
        QScrollBar:vertical {{
            background-color: {c.BG_SECONDARY};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c.BG_HOVER};
            border-radius: 6px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {c.BORDER};
        }}
        QScrollBar:horizontal {{
            background-color: {c.BG_SECONDARY};
            height: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {c.BG_HOVER};
            border-radius: 6px;
            min-width: 30px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
        }}
    """


def generate_checkbox_stylesheet():
    """Generate stylesheet for checkboxes."""
    c = get_current_theme()
    return f"""
        QCheckBox {{
            color: {c.TEXT_PRIMARY};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {c.BORDER};
            border-radius: 4px;
            background-color: {c.INPUT_BG};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c.ACCENT};
            border-color: {c.ACCENT};
        }}
    """


def generate_radio_stylesheet():
    """Generate stylesheet for radio buttons."""
    c = get_current_theme()
    return f"""
        QRadioButton {{
            color: {c.TEXT_PRIMARY};
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {c.BORDER};
            border-radius: 9px;
            background-color: {c.INPUT_BG};
        }}
        QRadioButton::indicator:checked {{
            background-color: {c.ACCENT};
            border-color: {c.ACCENT};
        }}
    """


def generate_slider_stylesheet():
    """Generate stylesheet for sliders."""
    c = get_current_theme()
    return f"""
        QSlider::groove:horizontal {{
            background-color: {c.BG_TERTIARY};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background-color: {c.ACCENT};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {c.ACCENT_HOVER};
        }}
    """


def generate_full_stylesheet():
    """Generate complete stylesheet for all widgets."""
    return (
        generate_main_window_stylesheet() +
        generate_button_stylesheet() +
        generate_input_stylesheet() +
        generate_list_stylesheet() +
        generate_label_stylesheet() +
        generate_panel_stylesheet() +
        generate_menu_stylesheet() +
        generate_scrollbar_stylesheet() +
        generate_checkbox_stylesheet() +
        generate_radio_stylesheet() +
        generate_slider_stylesheet()
    )
