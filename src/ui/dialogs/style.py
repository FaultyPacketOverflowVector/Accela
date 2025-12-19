import logging
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QColorDialog,
    QFontDialog,
)

from utils.settings import get_settings

logger = logging.getLogger(__name__)


class StyleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Style Settings")
        self.settings = get_settings()
        self.layout = QVBoxLayout(self)

        logger.debug("Opening StyleDialog.")

        # Color Settings
        color_group = QVBoxLayout()
        color_label = QLabel("Color Settings")
        color_label.setStyleSheet("font-weight: bold;")
        color_group.addWidget(color_label)

        # Accent color
        accent_color_layout = QHBoxLayout()
        accent_color_label = QLabel("Accent Color:")

        self.accent_color_button = QPushButton()
        accent_color_value = self.settings.value("accent_color", "#C06C84")
        self.accent_color_button.setStyleSheet(f"background-color: {accent_color_value};")
        self.accent_color_button.clicked.connect(self.choose_accent_color)

        # Reset Button
        self.accent_reset_button = QPushButton("Reset")
        self.accent_reset_button.clicked.connect(self.reset_accent_color)

        accent_color_layout.addWidget(accent_color_label)
        accent_color_layout.addWidget(self.accent_color_button)
        accent_color_layout.addWidget(self.accent_reset_button)
        accent_color_layout.addStretch()
        color_group.addLayout(accent_color_layout)

        # Background color
        bg_color_layout = QHBoxLayout()
        bg_color_label = QLabel("Background Color:")
        self.bg_color_button = QPushButton()
        bg_color_value = self.settings.value("background_color", "#000000")
        self.bg_color_button.setStyleSheet(f"background-color: {bg_color_value};")
        self.bg_color_button.clicked.connect(self.choose_bg_color)

        self.bg_reset_button = QPushButton("Reset")
        self.bg_reset_button.clicked.connect(self.reset_bg_color)

        bg_color_layout.addWidget(bg_color_label)
        bg_color_layout.addWidget(self.bg_color_button)
        bg_color_layout.addWidget(self.bg_reset_button)
        bg_color_layout.addStretch()

        color_group.addLayout(bg_color_layout)
        self.layout.addLayout(color_group)

        # Font Settings
        font_group = QVBoxLayout()
        font_label = QLabel("Font Settings")
        font_label.setStyleSheet("font-weight: bold;")
        font_group.addWidget(font_label)

        # Font chooser
        font_layout = QHBoxLayout()
        font_chooser_label = QLabel("Font:")

        self.font_button = QPushButton("Choose Font")

        # Load current font settings
        current_font = QFont()
        current_font.setFamily(self.settings.value("font", "TrixieCyrG-Plain"))
        current_font.setPointSize(int(self.settings.value("font-size", 10)))

        # Set font style
        font_style = self.settings.value("font-style", "Normal")
        if font_style == "Italic":
            current_font.setItalic(True)
        elif font_style == "Bold":
            current_font.setBold(True)
        elif font_style == "Bold Italic":
            current_font.setBold(True)
            current_font.setItalic(True)

        self.current_font = current_font
        self.update_font_button_text()

        self.font_button.clicked.connect(self.choose_font)

        self.font_reset_button = QPushButton("Reset")
        self.font_reset_button.clicked.connect(self.reset_font)

        font_layout.addWidget(font_chooser_label)
        font_layout.addWidget(self.font_button)
        font_layout.addWidget(self.font_reset_button)
        font_layout.addStretch()
        font_group.addLayout(font_layout)

        self.layout.addLayout(font_group)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def update_font_button_text(self):
        """Update the font button text to show current font details"""
        font_text = f"{self.current_font.family()} {self.current_font.pointSize()}pt"
        if self.current_font.bold() and self.current_font.italic():
            font_text += " Bold Italic"
        elif self.current_font.bold():
            font_text += " Bold"
        elif self.current_font.italic():
            font_text += " Italic"

        self.font_button.setText(font_text)
        self.font_button.setFont(self.current_font)

    def reset_accent_color(self):
        default = "#C06C84"
        self.settings.setValue("accent_color", default)
        self.accent_color_button.setStyleSheet(f"background-color: {default};")

    def reset_bg_color(self):
        default = "#000000"
        self.settings.setValue("background_color", default)
        self.bg_color_button.setStyleSheet(f"background-color: {default};")

    def reset_font(self):
        default_font = QFont()
        default_font.setFamily("TrixieCyrG-Plain")
        default_font.setPointSize(10)
        default_font.setBold(False)
        default_font.setItalic(False)

        self.current_font = default_font
        self.update_font_button_text()

        self.settings.setValue("font", "TrixieCyrG-Plain")
        self.settings.setValue("font-size", 10)
        self.settings.setValue("font-style", "Normal")

    def is_too_dark(self, color: QColor) -> bool:
        # Calculate perceived brightness (0–255 range)
        brightness = (color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114)
        return brightness < 20  # Darker than ~15%, tweak if needed

    def is_too_close_to_accent_color(self, accent_color: QColor, background_color: QColor, threshold: int = 100) -> bool:
        """Return True if background color is too close to accent color"""

        # Calculate color distance using Euclidean distance in RGB space
        r_diff = background_color.red() - accent_color.red()
        g_diff = background_color.green() - accent_color.green()
        b_diff = background_color.blue() - accent_color.blue()

        distance = (r_diff ** 2 + g_diff ** 2 + b_diff ** 2) ** 0.5

        return distance < threshold

    def choose_accent_color(self):
        color = QColorDialog.getColor()

        if not color.isValid():
            return

        if self.is_too_dark(color):
            QMessageBox.warning(
                self,
                "Invalid Color",
                "This color is too dark and would make the UI unusable."
            )
            return

        hex_color = color.name()
        self.settings.setValue("accent_color", hex_color)
        self.accent_color_button.setStyleSheet(f"background-color: {hex_color};")

    def choose_bg_color(self):
        color = QColorDialog.getColor()
        if not color.isValid():
            return

        hex_color = color.name()
        self.bg_color_button.setStyleSheet(f"background-color: {hex_color};")

    def choose_font(self):
        font, ok = QFontDialog.getFont(self.current_font, self)
        if ok:
            self.current_font = font
            self.update_font_button_text()

            # Save font settings immediately
            self.settings.setValue("font", font.family())
            self.settings.setValue("font-size", font.pointSize())

            # Determine font style
            if font.bold() and font.italic():
                font_style = "Bold Italic"
            elif font.bold():
                font_style = "Bold"
            elif font.italic():
                font_style = "Italic"
            else:
                font_style = "Normal"

            self.settings.setValue("font-style", font_style)

    def accept(self):
        # Save settings
        accent_color = (self.accent_color_button.styleSheet().split("background-color: ")[1].split(";")[0])
        bg_color = (self.bg_color_button.styleSheet().split("background-color: ")[1].split(";")[0])

        # Check if background color is too close to accent color
        if self.is_too_close_to_accent_color(QColor(accent_color), QColor(bg_color)):
            QMessageBox.warning(
                self,
                "Invalid Color",
                "The background color is too similar to the accent color and would reduce contrast."
            )
            return

        # Save settings
        self.settings.setValue("accent_color", accent_color)
        self.settings.setValue("background_color", bg_color)

        # Font settings are already saved when chosen, but we ensure they're current
        self.settings.setValue("font", self.current_font.family())
        self.settings.setValue("font-size", self.current_font.pointSize())

        # Determine and save font style
        if self.current_font.bold() and self.current_font.italic():
            font_style = "Bold Italic"
        elif self.current_font.bold():
            font_style = "Bold"
        elif self.current_font.italic():
            font_style = "Italic"
        else:
            font_style = "Normal"
        self.settings.setValue("font-style", font_style)

        logger.info("Style settings saved.")
        super().accept()
