import logging
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QCheckBox,
    QGroupBox,
    QLabel,
    QHBoxLayout,
    QSlider,
    QPushButton,
    QWidget,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

from utils.settings import get_settings

logger = logging.getLogger(__name__)

def make_volume_row(name: str, slider: QSlider, value_label: QLabel, reset_button: QPushButton, current_volume: int):
    layout = QHBoxLayout()

    slider.setRange(0, 100)
    slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
    slider.setValue(current_volume)

    label = QLabel(f"{name}:")
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    label.setFixedWidth(105)

    value_label.setFixedWidth(30) # Percentage
    reset_button.setFixedHeight(25)

    layout.addWidget(label)
    layout.addWidget(slider, 1)
    layout.addWidget(value_label)
    layout.addWidget(reset_button)

    return layout

class AudioDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audio Settings")
        self.settings = get_settings()
        self.setMinimumSize(400, 300)
        self.layout = QVBoxLayout(self)

        logger.debug("Opening AudioDialog.")

        # Store current values for comparison/rollback
        self.current_master_volume = self.settings.value("master_volume", 80, type=int)
        self.current_music_volume = self.settings.value("music_volume", 80, type=int)
        self.current_effects_volume = self.settings.value("effects_volume", 50, type=int)
        self.current_hum_volume = self.settings.value("hum_volume", 20, type=int)

        # --- Audio Playback Settings ---
        audio_layout = QVBoxLayout()
        audio_label = QLabel("Audio Settings")
        audio_label.setStyleSheet("font-weight: bold;")
        audio_layout.addWidget(audio_label)

        # Play "Entering The Wired" on start
        self.play_etw_checkbox = QCheckBox("Play \"Entering The Wired\" on start")
        play_etw_value = self.settings.value("play_etw", True, type=bool)
        self.play_etw_checkbox.setChecked(play_etw_value)
        audio_layout.addWidget(self.play_etw_checkbox)

        # Play "Let's All Love Lain" on exit
        self.play_lall_checkbox = QCheckBox("Play \"Let's All Love Lain\" on exit")
        play_lall_value = self.settings.value("play_lall", True, type=bool)
        self.play_lall_checkbox.setChecked(play_lall_value)
        audio_layout.addWidget(self.play_lall_checkbox)

        # Play 50Hz hum noise loop
        self.play_50hz_hum_checkbox = QCheckBox("Play 50Hz hum noise loop")
        play_50hz_hum_value = self.settings.value("play_50hz_hum", True, type=bool)
        self.play_50hz_hum_checkbox.setChecked(play_50hz_hum_value)
        audio_layout.addWidget(self.play_50hz_hum_checkbox)

        self.layout.addLayout(audio_layout)

        # --- Volume Settings ---
        volume_layout = QVBoxLayout()
        volume_label = QLabel("Volume Settings")
        volume_label.setStyleSheet("font-weight: bold;")
        volume_layout.addWidget(volume_label)


        # Master Volume
        self.master_volume_slider = QSlider(Qt.Orientation.Horizontal)

        self.master_volume_value_label = QLabel(f"{self.current_master_volume}%")
        self.master_volume_reset = QPushButton("Reset")
        self.master_volume_reset.clicked.connect(
            lambda: self.reset_volume("master_volume", 80, self.master_volume_slider)
        )

        volume_layout.addLayout(make_volume_row(
            "Master Volume",
            self.master_volume_slider,
            self.master_volume_value_label,
            self.master_volume_reset,
            self.current_master_volume,
        ))


        # Music Volume
        self.music_volume_slider = QSlider(Qt.Orientation.Horizontal)

        self.music_volume_value_label = QLabel(f"{self.current_music_volume}%")
        self.music_volume_reset = QPushButton("Reset")
        self.music_volume_reset.clicked.connect(
            lambda: self.reset_volume("music_volume", 80, self.music_volume_slider)
        )

        #volume_layout.addLayout(make_volume_row(
        #    "Music Volume",
        #    self.music_volume_slider,
        #    self.music_volume_value_label,
        #    self.music_volume_reset,
        #    self.current_music_volume,
        #))


        # Effects Volume
        self.effects_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.effects_volume_slider.setRange(0, 100)
        self.effects_volume_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.effects_volume_slider.setTickInterval(10)

        self.effects_volume_value_label = QLabel(f"{self.current_effects_volume}%")
        self.effects_volume_reset = QPushButton("Reset")
        self.effects_volume_reset.clicked.connect(
            lambda: self.reset_volume("effects_volume", 50, self.effects_volume_slider)
        )

        volume_layout.addLayout(make_volume_row(
            "Effects Volume",
            self.effects_volume_slider,
            self.effects_volume_value_label,
            self.effects_volume_reset,
            self.current_effects_volume,
        ))


        # Hum Volume
        self.hum_volume_slider = QSlider(Qt.Orientation.Horizontal)

        self.hum_volume_value_label = QLabel(f"{self.current_hum_volume}%")
        self.hum_volume_reset = QPushButton("Reset")
        self.hum_volume_reset.clicked.connect(
            lambda: self.reset_volume("hum_volume", 20, self.hum_volume_slider)
        )

        volume_layout.addLayout(make_volume_row(
            "Hum Volume",
            self.hum_volume_slider,
            self.hum_volume_value_label,
            self.hum_volume_reset,
            self.current_hum_volume,
        ))


        self.layout.addLayout(volume_layout)

        # Connect slider signals to update functions (but don't save to settings)
        self.master_volume_slider.valueChanged.connect(self.on_master_volume_changed)
        self.music_volume_slider.valueChanged.connect(self.on_music_volume_changed)
        self.effects_volume_slider.valueChanged.connect(self.on_effects_volume_changed)
        self.hum_volume_slider.valueChanged.connect(self.on_hum_volume_changed)

        # Test buttons for ETW and LALL sounds
        test_layout = QHBoxLayout()
        self.test_etw_button = QPushButton("Test ETW Sound")
        self.test_lall_button = QPushButton("Test LALL Sound")
        self.test_etw_button.clicked.connect(self.test_etw_sound)
        self.test_lall_button.clicked.connect(self.test_lall_sound)
        test_layout.addWidget(self.test_etw_button)
        test_layout.addWidget(self.test_lall_button)
        self.layout.addLayout(test_layout)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def on_master_volume_changed(self, value):
        """Handle master volume changes in real-time (without saving to settings)"""
        self.master_volume_value_label.setText(f"{value}%")
        self.apply_master_volume_preview(value)

    def on_music_volume_changed(self, value):
        """Handle music volume changes in real-time (without saving to settings)"""
        self.music_volume_value_label.setText(f"{value}%")
        self.apply_music_volume_preview(value)

    def on_effects_volume_changed(self, value):
        """Handle effects volume changes in real-time (without saving to settings)"""
        self.effects_volume_value_label.setText(f"{value}%")
        self.apply_effects_volume_preview(value)

    def on_hum_volume_changed(self, value):
        """Handle hum volume changes in real-time (without saving to settings)"""
        self.hum_volume_value_label.setText(f"{value}%")
        self.apply_hum_volume_preview(value)

    def apply_master_volume_preview(self, value):
        """Apply master volume changes for preview only"""
        if hasattr(self.parent(), 'audio_manager'):
            # Temporarily apply the volume without saving to settings
            self.parent().audio_manager.apply_master_volume_preview(value)

    def apply_music_volume_preview(self, value):
        """Apply music volume changes for preview only"""
        if hasattr(self.parent(), 'audio_manager'):
            # Temporarily apply the volume without saving to settings
            self.parent().audio_manager.apply_music_volume_preview(value)

    def apply_effects_volume_preview(self, value):
        """Apply effects volume changes for preview only"""
        if hasattr(self.parent(), 'audio_manager'):
            # Temporarily apply the volume without saving to settings
            self.parent().audio_manager.apply_effects_volume_preview(value)

    def apply_hum_volume_preview(self, value):
        """Apply hum volume changes for preview only"""
        if hasattr(self.parent(), 'audio_manager'):
            # Temporarily apply the volume without saving to settings
            self.parent().audio_manager.apply_hum_volume_preview(value)

    def reset_volume(self, setting_key, default_value, slider):
        """Reset volume to default value (preview only)"""
        slider.setValue(default_value)
        # Update the label immediately
        if slider == self.master_volume_slider:
            self.master_volume_value_label.setText(f"{default_value}%")
            self.apply_master_volume_preview(default_value)
        elif slider == self.music_volume_slider:
            self.music_volume_value_label.setText(f"{default_value}%")
            self.apply_music_volume_preview(default_value)
        elif slider == self.effects_volume_slider:
            self.effects_volume_value_label.setText(f"{default_value}%")
            self.apply_effects_volume_preview(default_value)
        elif slider == self.hum_volume_slider:
            self.hum_volume_value_label.setText(f"{default_value}%")
            self.apply_hum_volume_preview(default_value)

    def test_etw_sound(self):
        """Test play the ETW sound"""
        if hasattr(self.parent(), 'audio_manager'):
            self.parent().audio_manager.test_etw_sound()

    def test_lall_sound(self):
        """Test play the LALL sound"""
        if hasattr(self.parent(), 'audio_manager'):
            self.parent().audio_manager.test_lall_sound()

    def accept(self):
        # Save checkbox settings
        self.settings.setValue("play_etw", self.play_etw_checkbox.isChecked())
        self.settings.setValue("play_lall", self.play_lall_checkbox.isChecked())
        self.settings.setValue("play_50hz_hum", self.play_50hz_hum_checkbox.isChecked())

        # Save volume settings only when applying
        self.settings.setValue("master_volume", self.master_volume_slider.value())
        self.settings.setValue("music_volume", self.music_volume_slider.value())
        self.settings.setValue("effects_volume", self.effects_volume_slider.value())
        self.settings.setValue("hum_volume", self.hum_volume_slider.value())

        # Apply final audio settings
        if hasattr(self.parent(), 'audio_manager'):
            self.parent().audio_manager.apply_audio_settings()

        logger.info("Audio settings saved.")
        super().accept()

    def reject(self):
        """Restores original volumes if cancelled"""
        if hasattr(self.parent(), 'audio_manager'):
            self.parent().audio_manager.apply_audio_settings()
        super().reject()
