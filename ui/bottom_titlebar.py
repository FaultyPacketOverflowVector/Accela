import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QMovie, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QWidget

from utils.helpers import resource_path, get_base_path
from utils.settings import get_settings

from .assets import GEAR_SVG, MAXIMIZE, MINIMIZE, PALETTE_SVG, POWER_SVG, SEARCH_SVG, BOOK_SVG, AUDIO_SVG

logger = logging.getLogger(__name__)


class BottomTitleBar(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.drag_pos = None
        self.setFixedHeight(32)

        # Remove hardcoded style and apply through parent
        self._apply_style()

        logger.debug("CustomTitleBar initialized.")

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)


        self.navi_label = QLabel()
        self.navi_movie = QMovie(str(get_base_path() / "gifs/colorized/navi.gif"))

        if self.navi_movie.isValid():
            self.navi_movie.jumpToFrame(0)
            orig = self.navi_movie.currentImage().size()
            h, w = 20, int(20 * (orig.width() / orig.height())) if orig.height() > 0 else 57 # fallback number 84x29 -> 57x20
            self.navi_movie.setScaledSize(QSize(w, h))
            self.navi_label.setFixedSize(w, h)
            self.navi_label.setMovie(self.navi_movie)
            self.navi_movie.start()

        left_layout.addWidget(self.navi_label, alignment=Qt.AlignmentFlag.AlignLeft)

        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self.search_button = self._create_svg_button(
            SEARCH_SVG, parent.open_fetch_dialog, "Fetch Manifest"
        )
        right_layout.addWidget(self.search_button)

        self.game_library_button = self._create_svg_button(
            BOOK_SVG, parent.open_game_library, "Game Library"
        )
        right_layout.addWidget(self.game_library_button)

        self.audio_button = self._create_svg_button(
            AUDIO_SVG, parent.open_audio_dialog, "Audio Settings"
        )
        right_layout.addWidget(self.audio_button)

        self.style_button = self._create_svg_button(
            PALETTE_SVG, parent.open_style_dialog, "Style Settings"
        )
        right_layout.addWidget(self.style_button)

        self.settings_button = self._create_svg_button(
            GEAR_SVG, parent.open_settings, "Open Settings"
        )
        right_layout.addWidget(self.settings_button)

        # Window control buttons (minimize, maximize)
        self.minimize_button = self._create_svg_button(
            MINIMIZE, self._minimize_window, "Minimize"
        )
        right_layout.addWidget(self.minimize_button)

        self.maximize_button = self._create_svg_button(
            MAXIMIZE, self._maximize_window, "Maximize/Restore"
        )
        right_layout.addWidget(self.maximize_button)

        self.close_button = self._create_svg_button(
            POWER_SVG, parent.close, "Close Application"
        )
        right_layout.addWidget(self.close_button)

        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setContentsMargins(10, 10, 10, 10)
        right_layout.addWidget(self.size_grip)

        version_file = resource_path("res/version")
        version = "ACCELA"

        try:
            with open(version_file, "r", encoding="utf-8") as f:
                version = f"ACCELA {f.read().strip() or ''}"
        except Exception as e:
            logger.warning(f"Failed to read version file: {e}")

        layout.addWidget(left_widget)
        layout.addStretch(1)
        self.title_label = QLabel(version)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(right_widget)

        left_width = left_widget.sizeHint().width()
        right_width = right_widget.sizeHint().width()
        if left_width > right_width:
            right_widget.setMinimumWidth(left_width)
        else:
            left_widget.setMinimumWidth(right_width)

        self.setLayout(layout)

    def _apply_style(self):
        """Apply style settings from the parent window"""
        settings = get_settings()
        bg_color = settings.value("background_color", "#000000")
        accent_color = settings.value("accent_color", "#C06C84")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
            }}
            QToolTip {{
                color: {accent_color};
                background-color: {bg_color};
                border: 1px solid {accent_color};
                padding: 2px;
            }}
        """)

        # Update title label color
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"color: {accent_color}; font-size: 14pt;")

    def update_style(self):
        """Update the style when colors change"""
        self._apply_style()
        self._update_button_colors()
        self._update_button_styles()

    def _update_button_styles(self):
        """Update all button styles with custom border and background color"""
        settings = get_settings()
        accent_color = QColor(settings.value("accent_color", "#C06C84"))
        background_color = QColor(settings.value("background_color", "#000000"))
        background_color_hover = background_color
        hover_lightness = 150
        if background_color == QColor("#000000"):
            background_color_hover = QColor("#282828")
            hover_lightness = 120

        button_style = f"""
            QPushButton {{
                background-color: {background_color.name()};
                border: none;
                border-radius: 3px;
                padding: 1px;
            }}
            QPushButton:hover {{
                background-color: {background_color_hover.lighter(hover_lightness).name()};
            }}
        """

        # Apply to all buttons
        buttons = [
            self.minimize_button,
            self.maximize_button,
            self.search_button,
            self.game_library_button,
            self.style_button,
            self.settings_button,
            self.close_button,
            self.audio_button,
        ]

        for button in buttons:
            if button:
                button.setStyleSheet(button_style)

    def _update_button_colors(self):
        """Update all SVG button colors to match the current accent color"""
        settings = get_settings()
        accent_color = settings.value("accent_color", "#C06C84")

        # Update all SVG buttons
        buttons = [
            (self.minimize_button, MINIMIZE),
            (self.maximize_button, MAXIMIZE),
            (self.search_button, SEARCH_SVG),
            (self.game_library_button, BOOK_SVG),
            (self.style_button, PALETTE_SVG),
            (self.settings_button, GEAR_SVG),
            (self.close_button, POWER_SVG),
            (self.audio_button, AUDIO_SVG),
        ]

        for button, svg_data in buttons:
            if button:
                self._update_svg_button_color(button, svg_data, accent_color)

    def _update_svg_button_color(self, button, svg_data, color):
        """Update a single SVG button's color"""
        try:
            renderer = QSvgRenderer(svg_data.encode("utf-8"))
            icon_size = QSize(16, 16)

            pixmap = QPixmap(icon_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(pixmap.rect(), QColor(color))
            painter.end()

            icon = QIcon(pixmap)
            button.setIcon(icon)

        except Exception as e:
            logger.error(f"Failed to update SVG button color: {e}", exc_info=True)

    def _create_svg_button(self, svg_data, on_click, tooltip):
        try:
            button = QPushButton()
            button.setToolTip(tooltip)

            settings = get_settings()
            accent_color = QColor(settings.value("accent_color", "#C06C84"))
            background_color = QColor(settings.value("background_color", "#000000"))
            if background_color == QColor("#000000"):
                background_color = QColor("#282828")

            # Create colors for button styling
            hover_bg_color = background_color.lighter(120).name()
            border_hover_color = accent_color.darker(110).name()

            renderer = QSvgRenderer(svg_data.encode("utf-8"))
            icon_size = QSize(16, 16)

            pixmap = QPixmap(icon_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(pixmap.rect(), accent_color)
            painter.end()

            icon = QIcon(pixmap)

            button.setIcon(icon)
            button.setIconSize(icon_size)
            button.setFixedSize(20, 20)

            button.clicked.connect(on_click)
            return button
        except Exception as e:
            logger.error(f"Failed to create SVG button: {e}", exc_info=True)
            fallback_button = QPushButton("X")
            fallback_button.setFixedSize(20, 20)
            fallback_button.clicked.connect(on_click)
            return fallback_button

    def _minimize_window(self):
        """Minimize the window"""
        self.parent.showMinimized()

    def _maximize_window(self):
        """Maximize or restore the window"""
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window().windowHandle()
            if window is not None:
                window.startSystemMove()
            event.accept()


"""
The wired might actually be thought of as a highly advanced upper layer of the real world. In other words, physical reality is nothing but an illusion, a hologram of the information that flows to us through the wired.
This is because the body, physical motion, the activity of the human brain is merely a physical phenomenon, simply caused by synapses delivering electrical impulses.
The physical body exists at a less evolved plane only to verify one's existence in the universe.
"""
