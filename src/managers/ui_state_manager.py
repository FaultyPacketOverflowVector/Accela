import os
import random
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMovie, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QApplication, QFrame
)

from utils.helpers import get_base_path
from managers.gif_manager import process_gif_batch

logger = logging.getLogger(__name__)


class UIStateManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.settings = main_window.settings

        # UI state
        self.fetch_dialog = None
        self.depot_dialog = None
        self.current_movie = None
        self.random_gif_path = None
        self.download_movie = None
        self.main_movie = None

        # Queue UI elements
        self.queue_widget = None
        self.queue_list_widget = None
        self.queue_move_up_button = None
        self.queue_move_down_button = None
        self.queue_remove_button = None
        self.pause_button = None
        self.cancel_button = None

        self._initialize_gifs()

    def _initialize_gifs(self):
        """Initialize GIF resources"""
        colored_dir = str(get_base_path() / "gifs/colorized")
        os.makedirs(colored_dir, exist_ok=True)

        self.download_gifs = [
            str(get_base_path() / f"gifs/colorized/downloading{i}.gif")
            for i in range(1, 12)
        ]
        self._update_gifs()

    def _update_gifs(self):
        """Update GIFs with current accent color"""
        output_dir = str(get_base_path() / "gifs/colorized")
        process_gif_batch(output_dir, self.main_window.accent_color)
        self._reload_movies()

    def _reload_movies(self):
        """Reload movie objects with current GIFs"""
        main_gif_path = str(get_base_path() / "gifs/colorized/main.gif")
        if os.path.exists(main_gif_path):
            self.main_movie = QMovie(main_gif_path)

    def setup_initial_gif(self, drop_label):
        """Setup the initial GIF display"""
        if hasattr(self, 'main_movie') and self.main_movie and self.main_movie.isValid():
            drop_label.setMovie(self.main_movie)
            self.main_movie.start()
            self.current_movie = self.main_movie
        else:
            drop_label.setText("Drag and Drop ZIP File Here")

    def setup_queue_panel(self):
        """Setup the download queue panel"""
        self.queue_widget = QWidget()
        queue_layout = QVBoxLayout(self.queue_widget)
        queue_layout.setContentsMargins(0, 0, 5, 0)

        # Queue label
        queue_label = QLabel("Download Queue")
        queue_label.setStyleSheet(f"color: {self.main_window.accent_color};")
        queue_layout.addWidget(queue_label)

        # Queue list
        self.queue_list_widget = QListWidget()
        self.queue_list_widget.setToolTip("Current download queue. Select an item to move it.")
        queue_layout.addWidget(self.queue_list_widget)

        # Queue buttons
        self._setup_queue_buttons(queue_layout)

    def _setup_queue_buttons(self, parent_layout):
        """Setup queue control buttons"""
        queue_button_layout = QHBoxLayout()

        self.queue_move_up_button = QPushButton("Move Up")
        self.queue_move_up_button.clicked.connect(self.main_window.job_queue.move_item_up)
        queue_button_layout.addWidget(self.queue_move_up_button)

        self.queue_move_down_button = QPushButton("Move Down")
        self.queue_move_down_button.clicked.connect(self.main_window.job_queue.move_item_down)
        queue_button_layout.addWidget(self.queue_move_down_button)

        self.queue_remove_button = QPushButton("Remove")
        self.queue_remove_button.clicked.connect(self.main_window.job_queue.remove_item)
        queue_button_layout.addWidget(self.queue_remove_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.main_window.task_manager.toggle_pause)
        self.pause_button.setVisible(False)
        queue_button_layout.addWidget(self.pause_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.main_window.task_manager.cancel_current_job)
        self.cancel_button.setVisible(False)
        queue_button_layout.addWidget(self.cancel_button)

        parent_layout.addLayout(queue_button_layout)

    def apply_style_settings(self):
        """Apply current style settings to UI"""
        self.main_window.background_color = self.settings.value("background_color", "#000000")
        self.main_window.accent_color = self.settings.value("accent_color", "#C06C84")

        # Load font family
        font_family = self.settings.value("font", "TrixieCyrG-Plain")

        # Load size
        font_size = self.settings.value("font-size", 10, type=int)

        # Create font
        font = QFont(font_family)
        font.setPointSize(font_size)

        # Set font style
        font_style = self.settings.value("font-style", "Normal")
        if font_style == "Italic":
            font.setItalic(True)
        elif font_style == "Bold":
            font.setBold(True)
        elif font_style == "Bold Italic":
            font.setBold(True)
            font.setItalic(True)
        # "Normal" is the default, so no changes needed

        self.main_window.font = font

        # Update application appearance
        from main import update_appearance
        update_appearance(
            QApplication.instance(),
            self.main_window.accent_color,
            self.main_window.background_color,
            self.main_window.font,
        )

        # Apply styles to various UI elements
        self._apply_background_color()
        self._apply_accent_color()
        self._update_gifs()

    def _apply_background_color(self):
        """Apply background color to main content"""
        main_frame = self.main_window.central_widget.findChild(QFrame)
        if main_frame:
            main_frame.setStyleSheet(f"background-color: {self.main_window.background_color};")

    def _apply_accent_color(self):
        """Apply accent color to UI elements"""
        accent_style = f"color: {self.main_window.accent_color};"

        # Drop text label
        self.main_window.drop_text_label.setStyleSheet(accent_style)

        # Queue label
        if hasattr(self, 'queue_widget'):
            queue_label = self.queue_widget.findChild(QLabel)
            if queue_label:
                queue_label.setStyleSheet(accent_style)

        # Progress bar
        self.main_window._update_progress_bar_style()

        # Log output
        self.main_window.log_output.setStyleSheet(accent_style)

        # Bottom titlebar
        if hasattr(self.main_window, 'bottom_titlebar'):
            self.main_window.bottom_titlebar.update_style()

    def update_queue_visibility(self, is_processing, has_jobs):
        """Update queue visibility based on current state"""
        if not is_processing and not has_jobs:
            self.queue_widget.setVisible(False)
            self.main_window.drop_text_label.setText("Drag and Drop Zip here")
            self._show_main_gif()
        else:
            self.queue_widget.setVisible(True)
            if not is_processing:
                self.main_window.drop_text_label.setText("Queue idle. Ready for next job.")

    def _show_main_gif(self):
        """Show the main GIF animation"""
        if (self.current_movie != self.main_movie and
            self.main_movie and self.main_movie.isValid()):
            self.main_window.drop_label.setMovie(self.main_movie)
            self.main_movie.start()
            self.current_movie = self.main_movie

    def switch_to_download_gif(self):
        """Switch to a random download GIF"""
        if self.current_movie:
            self.current_movie.stop()

        self.random_gif_path = random.choice(self.download_gifs)
        self.download_movie = QMovie(self.random_gif_path)
        if self.download_movie.isValid():
            self.current_movie = self.download_movie
            self.main_window.drop_label.setMovie(self.current_movie)
            self.current_movie.start()
