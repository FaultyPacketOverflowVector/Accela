import os
import logging
import pygame
import time
from PyQt6.QtWidgets import QApplication

from utils.helpers import resource_path
from utils.settings import get_settings

logger = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.settings = get_settings()
        self.exit_sound_played = False

        # Store current preview values
        self.preview_master_volume = self.settings.value("master_volume", 80, type=int)
        self.preview_effects_volume = self.settings.value("effects_volume", 50, type=int)
        self.preview_hum_volume = self.settings.value("hum_volume", 20, type=int)

        # Initialize pygame mixer
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

        # Audio channels
        self.effects_channel = pygame.mixer.Channel(0)
        self.music_channel = pygame.mixer.Channel(1)
        self.hum_channel = pygame.mixer.Channel(2)

        self.setup_sounds()

    def check_audio_devices(self):
        """Check available audio output devices"""
        if not pygame.mixer.get_init():
            logger.warning("Audio system not initialized - audio will be disabled")
            return False

        logger.debug("Audio system initialized successfully")
        return True

    def validate_audio_files(self):
        """Validate that audio files exist and are accessible"""
        logger.debug("Validating audio files...")
        audio_files = [
            resource_path("res/etw.wav"),
            resource_path("res/lall.wav"),
            resource_path("res/50hz.wav")
        ]

        all_files_valid = True
        for file_path in audio_files:
            if not os.path.exists(file_path):
                logger.error(f"Audio file not found: {file_path}")
                all_files_valid = False
            elif os.path.getsize(file_path) == 0:
                logger.error(f"Audio file is empty: {file_path}")
                all_files_valid = False
            else:
                logger.debug(f"Audio file OK: {file_path}")

        return all_files_valid

    def applyVolume(self, volumeSliderValue):
        """Convert slider value to linear volume"""
        linear_volume = volumeSliderValue / 100.0
        logger.debug(f"Converting volume: {volumeSliderValue} -> {linear_volume:.3f}")
        return linear_volume

    def setup_sounds(self):
        """Setup all audio effects with volume control using PyGame"""
        logger.debug("Setting up audio sounds...")

        # Check for audio devices first
        if not self.check_audio_devices():
            logger.warning("Audio setup aborted - no audio devices available")
            self.open_sound = self.close_sound = self.loop_sound = None
            return

        # Validate audio files
        if not self.validate_audio_files():
            logger.warning("Some audio files are missing or invalid")

        try:
            # Open sound ("Entering The Wired")
            logger.debug("Setting up open sound...")
            open_sound_path = resource_path("res/etw.wav")
            if os.path.exists(open_sound_path):
                logger.debug(f"Loading open sound: {open_sound_path}")
                self.open_sound = pygame.mixer.Sound(open_sound_path)
                if self.settings.value("play_etw", True, type=bool) and not self.effects_channel.get_busy():
                    logger.debug("Playing open sound (ETW)")
                    self.effects_channel.play(self.open_sound)
            else:
                logger.warning(f"Could not find open sound: {open_sound_path}")
                self.open_sound = None

            # Close sound ("Let's All Love Lain")
            logger.debug("Setting up close sound...")
            close_sound_path = resource_path("res/lall.wav")
            if os.path.exists(close_sound_path):
                logger.debug(f"Loading close sound: {close_sound_path}")
                self.close_sound = pygame.mixer.Sound(close_sound_path)
                QApplication.instance().aboutToQuit.connect(self.on_app_about_to_quit)
            else:
                logger.warning(f"Could not find close sound: {close_sound_path}")
                self.close_sound = None

            # Loop sound (50Hz hum)
            logger.debug("Setting up loop sound...")
            loop_sound_path = resource_path("res/50hz.wav")
            if os.path.exists(loop_sound_path):
                logger.debug(f"Loading loop sound: {loop_sound_path}")
                self.loop_sound = pygame.mixer.Sound(loop_sound_path)

                # Only play if enabled in settings
                if self.settings.value("play_50hz_hum", True, type=bool) and not self.hum_channel.get_busy():
                    logger.debug("Starting loop sound playback")
                    self.hum_channel.set_volume(0.0)
                    self.hum_channel.play(self.loop_sound, loops=-1)
            else:
                logger.warning(f"Could not find loop sound: {loop_sound_path}")
                self.loop_sound = None

            # Apply initial audio settings
            logger.debug("Applying initial audio settings...")
            self.apply_audio_settings()
            logger.debug("Audio setup completed successfully")

        except Exception as e:
            logger.error(f"Error during audio setup: {e}")
            self.open_sound = self.close_sound = self.loop_sound = None

    def apply_audio_settings(self):
        """Applies all audio settings including volumes using saved settings"""
        if not any([self.open_sound, self.close_sound, self.loop_sound]):
            logger.debug("Audio not available, skipping settings application")
            return

        logger.debug("Applying audio settings...")

        # Get slider values from settings
        master_volume = self.applyVolume(self.settings.value("master_volume", 80, type=int))
        effects_volume = self.applyVolume(self.settings.value("effects_volume", 50, type=int))
        hum_volume = self.applyVolume(self.settings.value("hum_volume", 20, type=int))

        logger.debug(f"Volume levels - Master: {master_volume:.3f}, Effects: {effects_volume:.3f}, Hum: {hum_volume:.3f}")

        # Apply volumes to channels
        self.effects_channel.set_volume(master_volume * effects_volume)
        logger.debug(f"Effects volume: {master_volume * effects_volume:.3f}")

        self.hum_channel.set_volume(master_volume * hum_volume)
        logger.debug(f"Hum volume: {master_volume * hum_volume:.3f}")

        # Handle loop sound playback state
        play_loop = self.settings.value("play_50hz_hum", True, type=bool)
        if play_loop and not self.hum_channel.get_busy() and self.loop_sound:
            logger.debug("Starting loop sound playback")
            self.hum_channel.play(self.loop_sound, loops=-1)
        elif not play_loop and self.hum_channel.get_busy():
            logger.debug("Stopping loop sound playback")
            self.hum_channel.stop()

    def apply_preview_volumes(self, master=None, effects=None, hum=None):
        """Apply preview volumes using current slider values"""
        # Update preview values if provided
        if master is not None:
            self.preview_master_volume = master
        if effects is not None:
            self.preview_effects_volume = effects
        if hum is not None:
            self.preview_hum_volume = hum

        # Calculate volumes using current preview values
        master_volume = self.applyVolume(self.preview_master_volume)
        effects_volume = self.applyVolume(self.preview_effects_volume)
        hum_volume = self.applyVolume(self.preview_hum_volume)

        logger.debug(f"Preview volumes - Master: {self.preview_master_volume}, Effects: {self.preview_effects_volume}, Hum: {self.preview_hum_volume}")

        # Apply to channels
        self.effects_channel.set_volume(master_volume * effects_volume)
        self.hum_channel.set_volume(master_volume * hum_volume)

    def apply_master_volume_preview(self, value):
        """Apply master volume changes for preview only"""
        logger.debug(f"Preview master volume: {value}")
        self.apply_preview_volumes(master=value)

    def apply_effects_volume_preview(self, value):
        """Apply effects volume changes for preview only"""
        logger.debug(f"Preview effects volume: {value}")
        self.apply_preview_volumes(effects=value)

    def apply_hum_volume_preview(self, value):
        """Apply hum volume changes for preview only"""
        logger.debug(f"Preview hum volume: {value}")
        self.apply_preview_volumes(hum=value)

    def on_app_about_to_quit(self):
        """Handle application about to quit event - wait for sound to finish"""
        # Prevent double execution
        if self.exit_sound_played:
            logger.debug("Exit sound already played, skipping")
            return

        self.exit_sound_played = True
        logger.debug("Playing exit sound")

        # Stop the loop sound immediately
        if self.hum_channel.get_busy():
            logger.debug("Stopping loop sound")
            self.hum_channel.stop()

        # Play close sound and BLOCK until it finishes
        self.play_close_sound_and_wait()

    def play_close_sound_and_wait(self):
        """Play the close sound and wait with timeout protection"""
        if (self.close_sound and self.settings.value("play_lall", True, type=bool)):
            logger.debug("Starting close sound playback with blocking wait")

            # Play the sound
            self.effects_channel.play(self.close_sound)

            # Get sound length for timeout calculation
            sound_length = self.close_sound.get_length()
            max_wait_time = sound_length + 2.0  # Add 2 second buffer
            start_time = time.time()

            # Wait with timeout protection
            while self.effects_channel.get_busy():
                # Check for timeout (in case sound gets stuck)
                if time.time() - start_time > max_wait_time:
                    logger.warning("Sound playback timeout, continuing anyway")
                    break

                time.sleep(0.05)

            logger.debug("Close sound finished, continuing shutdown")
        else:
            logger.debug("Close sound disabled or player not available")

    def test_etw_sound(self):
        """Test play the ETW sound"""
        logger.debug("Testing ETW sound")
        if self.open_sound:
            # If already playing, stop and restart from beginning
            if self.effects_channel.get_busy():
                logger.debug("ETW sound already playing, restarting")
                self.effects_channel.stop()
            self.effects_channel.play(self.open_sound)
        else:
            logger.warning("ETW sound not available for testing")

    def test_lall_sound(self):
        """Test play the LALL sound"""
        logger.debug("Testing LALL sound")
        if self.close_sound:
            # If already playing, stop and restart from beginning
            if self.effects_channel.get_busy():
                logger.debug("LALL sound already playing, restarting")
                self.effects_channel.stop()
            self.effects_channel.play(self.close_sound)
        else:
            logger.warning("LALL sound not available for testing")

    def audio_diagnostics(self):
        """Run audio system diagnostics"""
        logger.debug("=== Audio Diagnostics ===")

        if pygame.mixer.get_init():
            logger.debug("Pygame mixer initialized")
            logger.debug(f"Frequency: {pygame.mixer.get_init()[0]}")
            logger.debug(f"Format: {pygame.mixer.get_init()[1]}")
            logger.debug(f"Channels: {pygame.mixer.get_init()[2]}")
        else:
            logger.debug("Pygame mixer not initialized")

        # Check channels
        channels = [
            ("Effects", self.effects_channel),
            ("Music", self.music_channel),
            ("Hum", self.hum_channel)
        ]

        for name, channel in channels:
            if channel:
                busy = channel.get_busy()
                volume = channel.get_volume()
                logger.debug(f"{name} Channel - Busy: {busy}, Volume: {volume:.3f}")
            else:
                logger.debug(f"{name} Channel - Not available")

        # Check sounds
        sounds = [
            ("Open", self.open_sound),
            ("Close", self.close_sound),
            ("Loop", self.loop_sound)
        ]

        for name, sound in sounds:
            if sound:
                logger.debug(f"{name} Sound - Loaded: Yes")
            else:
                logger.debug(f"{name} Sound - Loaded: No")
