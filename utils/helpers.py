import sys
import os
import platform
import logging
from pathlib import Path

from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_path, relative_path)

def get_base_path(app_name="ACCELA"):
    """
    Return the base directory for the current platform, WITHOUT the logs directory.
    """
    system = platform.system().lower()

    if system == "linux":
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / app_name

        home = os.environ.get("HOME")
        if home:
            return Path(home) / ".local" / "share" / app_name

        tilde = os.path.expanduser("~")
        if tilde not in ("~", ""): # ensures it actually expanded
            return Path(tilde) / ".local" / "share" / app_name

        # If all fails resort to same dir save
        return Path(".") / app_name

    elif system == "windows":
        # Using the program directory
        return Path(os.path.dirname(os.path.abspath(sys.argv[0]))) / app_name

    elif system == "darwin":  # macOS
        # Standard macOS location
        return Path.home() / "Library" / "Logs" / app_name

    else:
        # Fallback directory for unknown platforms
        return Path.home() / ".logs" / app_name


def is_running_in_pyinstaller():
    """Check if the application is running as a PyInstaller bundle"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def add_gradient_border(element, accent_color: str, background_color: str):
    """Add a gradient border to a UI element"""

    accent_color = QColor(accent_color).darker().name()
    background_color = QColor(background_color).darker().name()

    element.setStyleSheet(f"""
        {element.styleSheet()}
        border-top: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_color}, stop:0.5 {background_color}, stop:1 {accent_color});
        border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_color}, stop:0.5 {background_color}, stop:1 {accent_color});
        border-left: 2px solid qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_color}, stop:0.5 {background_color}, stop:1 {accent_color});
        border-right: 2px solid qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_color}, stop:0.5 {background_color}, stop:1 {accent_color});
    """)
