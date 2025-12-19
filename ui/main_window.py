import atexit
import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from components.custom_widgets import ScaledFontLabel, ScaledLabel
from managers.audio_manager import AudioManager
from managers.game_manager import GameManager
from managers.job_queue_manager import JobQueueManager
from managers.task_manager import TaskManager
from managers.ui_state_manager import UIStateManager
from ui.bottom_titlebar import BottomTitleBar
from ui.dialogs.audio import AudioDialog
from ui.dialogs.fetchmanifest import FetchManifestDialog
from ui.dialogs.gamelibrary import GameLibraryDialog
from ui.dialogs.settings import SettingsDialog
from ui.dialogs.style import StyleDialog
from utils.helpers import resource_path
from utils.logger import qt_log_handler
from utils.settings import get_settings

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._setup_window_properties()
        self._initialize_managers()
        self._setup_ui()
        self._apply_style_settings()
        self._setup_audio()

    def _setup_window_properties(self):
        """Configure basic window properties"""
        self.setWindowTitle("ACCELA")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setGeometry(100, 100, 800, 600)

        # Set window icon
        icon_path = resource_path("res/logo/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning(f"Could not find window icon at: {icon_path}")

        # Windows-specific taskbar setup
        if sys.platform == "win32":
            self._setup_windows_taskbar()

    def _setup_windows_taskbar(self):
        """Windows-specific taskbar configuration"""
        try:
            import ctypes

            myappid = "god.is.in.the.wired.accela"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.warning(f"Could not set AppUserModelID: {e}")

    def _initialize_managers(self):
        """Initialize all manager classes"""
        self.settings = get_settings()

        # Initialize settings-dependent properties
        self.accent_color = self.settings.value("accent_color", "#C06C84")
        self.background_color = self.settings.value("background_color", "#000000")

        # Core managers
        self.task_manager = TaskManager(self)
        self.ui_state = UIStateManager(self)
        self.job_queue = JobQueueManager(self)
        self.audio_manager = AudioManager(self)
        self.game_manager = GameManager(self)

        logger.info("Starting initial game library scan in background...")
        self.game_manager.scan_steam_libraries()

    def _setup_ui(self):
        """Setup the main UI components"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self._create_main_content()
        self._create_bottom_section()

        self.setAcceptDrops(True)

    def _create_main_content(self):
        """Create the main content area with drop zone"""
        # Create a main container with a layout that will expand
        self.main_container = QWidget()
        self.main_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.layout.addWidget(self.main_container, 3)  # 3 parts of available space

        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Drop zone container - this will take most of the space
        self.drop_zone_container = QWidget()
        self.drop_zone_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.drop_zone_layout = QVBoxLayout(self.drop_zone_container)
        self.drop_zone_layout.setContentsMargins(0, 0, 0, 0)
        self.drop_zone_layout.setSpacing(0)

        # GIF display label
        self.drop_label = ScaledLabel()
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setMinimumHeight(100)
        self.drop_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.ui_state.setup_initial_gif(self.drop_label)

        # Instruction label
        self.drop_text_label = ScaledFontLabel("Drag and Drop Zip here")
        self.drop_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.drop_text_label.setMinimumHeight(16)
        self.drop_text_label.setMaximumHeight(48)

        # Add to drop zone layout
        self.drop_zone_layout.addWidget(
            self.drop_label, 9
        )  # main.gif / downloading gifs SIZE
        self.drop_zone_layout.addWidget(self.drop_text_label, 1)  # text below GIF

        # Add drop zone to main layout
        self.main_layout.addWidget(self.drop_zone_container, 10)

        # Progress indicators
        self.progress_container = QWidget()
        self.progress_layout = QVBoxLayout(self.progress_container)
        self.progress_layout.setContentsMargins(20, 5, 20, 5)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self._update_progress_bar_style()
        self.progress_layout.addWidget(self.progress_bar)

        self.speed_label = QLabel("")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.speed_label.setVisible(False)
        self.progress_layout.addWidget(self.speed_label)

        self.main_layout.addWidget(
            self.progress_container, 1
        )  # Minimal space for progress

    def _create_bottom_section(self):
        """Create the bottom section with queue and logs"""
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(5, 5, 5, 5)

        # Queue panel
        self.ui_state.setup_queue_panel()
        bottom_layout.addWidget(self.ui_state.queue_widget, 1)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        qt_log_handler.new_record.connect(self.log_output.append)
        bottom_layout.addWidget(self.log_output, 1)

        self.layout.addWidget(bottom_widget, 1)
        self.ui_state.queue_widget.setVisible(False)

        # Title bar
        self.bottom_titlebar = BottomTitleBar(self)
        self.layout.addWidget(self.bottom_titlebar)

    def _setup_audio(self):
        """Setup audio effects"""
        self.audio_manager.setup_sounds()

    def _apply_style_settings(self):
        """Apply the current style settings"""
        self.ui_state.apply_style_settings()

    def _apply_audio_settings(self):
        """Apply the current audio settings"""
        self.audio_manager.apply_audio_settings()

    def _update_progress_bar_style(self):
        """Update progress bar styling"""
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                max-height: 10px;
                border: 1px solid {self.accent_color};
                border-radius: 5px;
                text-align: center;
                color: #FFFFFF;
            }}
            QProgressBar::chunk {{
                background-color: {self.accent_color};
                border-radius: 5px;
            }}
        """)

    # Public methods for dialogs
    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def open_style_dialog(self):
        dialog = StyleDialog(self)
        if dialog.exec():
            self._apply_style_settings()

    def open_audio_dialog(self):
        dialog = AudioDialog(self)
        if dialog.exec():
            self._apply_audio_settings()

    def open_fetch_dialog(self):
        self.ui_state.fetch_dialog = FetchManifestDialog(self)
        self.ui_state.fetch_dialog.exec()
        self.ui_state.fetch_dialog = None

    def open_game_library(self):
        """Open the Game Library dialog"""
        dialog = GameLibraryDialog(self)
        dialog.exec()

    # Event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if all(
                url.isLocalFile() and url.toLocalFile().lower().endswith(".zip")
                for url in urls
            ):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        new_jobs = [
            url.toLocalFile()
            for url in urls
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".zip")
        ]

        if new_jobs:
            logger.info(f"Added {len(new_jobs)} file(s) to the queue via drag-drop.")
            for job_path in new_jobs:
                self.job_queue.add_job(job_path)

    def closeEvent(self, event):
        """Handle application shutdown"""
        try:
            self._cleanup_logging()
            self.task_manager.cleanup()
            self.job_queue.clear()
            self.game_manager.cleanup()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        super().closeEvent(event)

    def _cleanup_logging(self):
        """Clean up logging system"""
        try:
            atexit.unregister(logging.shutdown)
            logging.getLogger().removeHandler(qt_log_handler)
            qt_log_handler.close()
            logger.info("QtLogHandler removed and atexit hook unregistered.")
            logging.shutdown()
        except Exception as e:
            print(f"Error during custom logger shutdown: {e}")
