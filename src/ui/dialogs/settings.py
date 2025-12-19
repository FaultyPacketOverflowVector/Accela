import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from utils.helpers import get_base_path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from utils.helpers import is_running_in_pyinstaller, resource_path
from utils.settings import get_settings

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = get_settings()
        self.layout = QVBoxLayout(self)
        self.main_window = parent

        logger.debug("Opening SettingsDialog.")

        # --- Morrenus API Key ---
        form_layout = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Paste your Morrenus API key here")
        current_key = self.settings.value("morrenus_api_key", "", type=str)
        self.api_key_input.setText(current_key)
        form_layout.addRow("Morrenus API Key:", self.api_key_input)
        self.layout.addLayout(form_layout)
        # --- End API Key ---

        self.sls_mode_checkbox = QCheckBox("SLSsteam/GreenLuma Wrapper Mode")
        is_sls_mode = self.settings.value("slssteam_mode", False, type=bool)
        self.sls_mode_checkbox.setChecked(is_sls_mode)
        self.sls_mode_checkbox.setToolTip(
            "Enables special file handling for SLSsteam/GreenLuma compatibility."
        )
        self.layout.addWidget(self.sls_mode_checkbox)
        logger.debug(f"Initial SLSsteam mode setting is: {is_sls_mode}")

        is_library_mode = self.settings.value("library_mode", False, type=bool)
        self.library_mode_checkbox = QCheckBox("Limit Downloads to Steam Libraries")
        self.library_mode_checkbox.setChecked(is_library_mode)
        self.library_mode_checkbox.setToolTip("Detects steam libraries and lets you choose in which library to download.")
        self.layout.addWidget(self.library_mode_checkbox)

        self.sls_mode_checkbox.clicked.connect(self.library_mode_warning)
        self.library_mode_checkbox.clicked.connect(self.library_mode_warning)

        self.achievements_checkbox = QCheckBox("Generate Steam Achievements")
        achievements_enabled = self.settings.value(
            "generate_achievements", False, type=bool
        )
        self.achievements_checkbox.setChecked(achievements_enabled)
        self.achievements_checkbox.setToolTip(
            "Automatically generate Steam achievement stats using SLScheevo after successful downloads.\n"
            "Note: Steam credentials are automatically extracted from saved SLScheevo accounts."
        )
        self.layout.addWidget(self.achievements_checkbox)

        self.steamless_checkbox = QCheckBox("Remove Steam DRM with Steamless")
        steamless_enabled = self.settings.value("use_steamless", False, type=bool)
        self.steamless_checkbox.setChecked(steamless_enabled)
        self.steamless_checkbox.setToolTip(
            "Automatically remove Steam DRM from downloaded games using Steamless.\n"
            "This runs after the download completes and before achievement generation.\n"
            "Note: Requires Wine to be installed on Linux systems."
        )
        self.layout.addWidget(self.steamless_checkbox)

        # Proton version selection for Steamless (Linux only)
        if sys.platform == "linux":
            accent_color = self.settings.value("accent_color", "#C06C84")

            # Label to clarify this is only for Steamless prefix
            proton_label = QLabel("Proton Version (Steamless Prefix Only):")
            proton_label.setStyleSheet(f"color: {accent_color};")
            proton_label.setToolTip(
                "This Proton selection only applies when using Steamless DRM removal.\n"
                "It does NOT affect your system's default Proton installation."
            )
            self.layout.addWidget(proton_label)

            self.proton_version_combo = QComboBox()
            self.proton_version_combo.setToolTip(
                "Select which Proton version to use for Steamless DRM removal.\n"
                "'Auto-detect' will use the newest available Proton version.\n"
                "You can also select a specific Proton version if needed.\n\n"
                "Note: This only affects Steamless operations, not your system Proton."
            )
            self.layout.addWidget(self.proton_version_combo)

            # Populate Proton version dropdown
            self._populate_proton_versions()

        self.download_slssteam_button = QPushButton("Install latest SLSsteam")
        self.download_slssteam_button.setToolTip(
            "Download the latest SLSsteam tool from GitHub and install it.\n"
            "Required for SLSsteam Wrapper Mode.\n"
            "Note: Requires p7zip"
        )
        self.download_slssteam_button.clicked.connect(self.download_slssteam)

        # Update status indicator
        self.slssteam_status_label = QLabel()
        accent_color = self.settings.value("accent_color", "#C06C84")
        self.slssteam_status_label.setStyleSheet(
            f"color: {accent_color}; font-size: 12px;"
        )
        self._update_slssteam_status()

        # Only show on Linux
        if sys.platform == "linux":
            self.layout.addWidget(self.slssteam_status_label)
            self.layout.addWidget(self.download_slssteam_button)

        self.run_slscheevo_button = QPushButton("Run SLScheevo")
        self.run_slscheevo_button.setToolTip(
            "Launch SLScheevo in the terminal to generate Steam achievement stats.\n"
            "SLScheevo will handle Steam login and schema generation."
        )
        self.run_slscheevo_button.clicked.connect(self.run_slscheevo)
        self.layout.addWidget(self.run_slscheevo_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def library_mode_warning(self):
        if not self.sls_mode_checkbox.isChecked() and self.library_mode_checkbox.isChecked():
            QMessageBox.warning(self, "Warning", "SLSsteam/GreenLuma mode is disabled\nWhile ACCELA will download the games into the library you select, they won't be set up with Steam by ACCELA unless you enable SLSsteam/GreenLuma mode")

    def _populate_proton_versions(self):
        """Discover and populate available Proton versions."""
        # Import here to avoid circular imports
        from core.tasks.steamless_task import SteamlessIntegration

        try:
            # Create a temporary instance to discover Proton versions
            temp_integration = SteamlessIntegration()
            proton_versions = temp_integration.get_available_proton_versions()

            # Clear existing items
            self.proton_version_combo.clear()

            # Add auto-detect option
            self.proton_version_combo.addItem("Auto-detect (recommended)", "auto")

            # Deduplicate Proton versions by name, preferring paths from ~/.local/share/Steam
            # This handles the case where the same version exists in multiple Steam installations
            version_map = {}  # Maps version name to version info

            # Iterate through proton_versions in priority order (from SteamlessIntegration)
            for version_info in proton_versions:
                display_name = version_info["name"]
                version_path = version_info["path"]

                # If we haven't seen this version name, or if this path is from
                # ~/.local/share/Steam (preferred location), use it
                if display_name not in version_map:
                    version_map[display_name] = version_info
                else:
                    # Check if this path is preferred over the current one
                    current_path = version_map[display_name]["path"]
                    if (
                        ".local/share/Steam" in version_path
                        and ".local/share/Steam" not in current_path
                    ):
                        version_map[display_name] = version_info

            # Add unique versions to combo box in priority order
            # The proton_versions list is already sorted by priority from SteamlessIntegration
            for version_info in proton_versions:
                if version_info["name"] in version_map:
                    self.proton_version_combo.addItem(
                        version_info["name"], version_info["path"]
                    )

            # Load saved setting
            saved_version = self.settings.value(
                "steamless_proton_version", "auto", type=str
            )

            # Find and set the saved version
            for i in range(self.proton_version_combo.count()):
                data = self.proton_version_combo.itemData(i)
                if data == saved_version:
                    self.proton_version_combo.setCurrentIndex(i)
                    break
            else:
                # If saved version not found, select auto-detect
                self.proton_version_combo.setCurrentIndex(0)

            logger.debug(
                f"Populated unique Proton versions: {list(version_map.keys())}"
            )
        except Exception as e:
            logger.error(f"Failed to populate Proton versions: {e}", exc_info=True)
            # Fallback to just auto-detect
            self.proton_version_combo.clear()
            self.proton_version_combo.addItem("Auto-detect (recommended)", "auto")
            self.proton_version_combo.setCurrentIndex(0)

    def accept(self):
        is_sls_mode = self.sls_mode_checkbox.isChecked()
        self.settings.setValue("slssteam_mode", is_sls_mode)
        logger.info(f"SLSsteam mode setting changed to: {is_sls_mode}")

        is_library_mode = self.library_mode_checkbox.isChecked()
        self.settings.setValue("library_mode", is_library_mode)
        logger.info(f"SLSsteam mode setting changed to: {is_library_mode}")

        api_key = self.api_key_input.text().strip()
        self.settings.setValue("morrenus_api_key", api_key)
        if api_key:
            logger.info("Morrenus API key saved.")
        else:
            logger.info("Morrenus API key cleared.")

        achievements_enabled = self.achievements_checkbox.isChecked()
        self.settings.setValue("generate_achievements", achievements_enabled)
        logger.info(f"Generate Achievements is set to: {achievements_enabled}")

        steamless_enabled = self.steamless_checkbox.isChecked()
        self.settings.setValue("use_steamless", steamless_enabled)
        logger.info(f"Use Steamless is set to: {steamless_enabled}")

        # Save Proton version selection (only if it exists, i.e., on Linux)
        if (
            hasattr(self, "proton_version_combo")
            and self.proton_version_combo is not None
        ):
            selected_version = self.proton_version_combo.currentData()
            self.settings.setValue("steamless_proton_version", selected_version)
            logger.info(f"Proton version selection saved: {selected_version}")

        super().accept()

    def _get_slscheevo_path(self):
        """Get path to SLScheevo executable or Python script"""
        # If not running in PyInstaller, use the Python script
        if not is_running_in_pyinstaller():
            script_path = Path("src/deps/SLScheevo/SLScheevo.py").resolve()
            logger.info(f"Using SLScheevo Python script at: {script_path}")
            return script_path

        # Running in PyInstaller: use the compiled executable
        executable_name = "SLScheevo.exe" if sys.platform == "win32" else "SLScheevo"
        relative_path = f"deps/SLScheevo/{executable_name}"

        # For PyInstaller, use resource_path
        try:
            return Path(resource_path(relative_path))
        except Exception:
            # Fallback to absolute path based on current working directory
            return Path(os.path.abspath(relative_path))

    def _get_save_dir_path(self):
        """Get platform-specific save directory for SLScheevo credentials"""
        system = platform.system().lower()
        app_name = "ACCELA"

        if system == "linux":
            # Linux: ~/.local/share/ACCELA/SLScheevo
            xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
                "~/.local/share"
            )
            save_dir = Path(xdg_data_home) / app_name / "SLScheevo"
        elif system == "windows":
            # Windows: ./ACCELA/SLScheevo (relative to app directory)
            save_dir = (
                Path(os.path.dirname(os.path.abspath(sys.argv[0])))
                / app_name
                / "SLScheevo"
            )
        else:
            # Fallback: ~/.local/share/ACCELA/SLScheevo
            save_dir = Path.home() / ".local/share" / app_name / "SLScheevo"

        # Create directory if it doesn't exist
        save_dir.mkdir(parents=True, exist_ok=True)

        # Ensure UserGameStats_TEMPLATE.bin exists
        self._ensure_template_file(save_dir)

        logger.info(f"SLScheevo save directory: {save_dir}")
        return save_dir

    def _ensure_template_file(self, save_dir):
        """Ensure UserGameStats_TEMPLATE.bin exists in the save directory"""
        template_filename = "UserGameStats_TEMPLATE.bin"
        template_in_save_dir = save_dir / "data" / template_filename

        # If template already exists, no need to copy
        if template_in_save_dir.exists():
            return

        # Find the original template file
        template_source = None

        if is_running_in_pyinstaller():
            # In PyInstaller bundle, try to get from bundled resources
            try:
                template_source = Path(
                    resource_path(f"deps/SLScheevo/data/{template_filename}")
                )
            except Exception:
                pass
        else:
            # In development, use the script directory
            template_source = (
                Path("src/deps/SLScheevo/data").resolve() / template_filename
            )

        # If we found the source template, copy it
        if template_source and template_source.exists():
            # Create data directory if it doesn't exist
            (save_dir / "data").mkdir(exist_ok=True)
            # Copy the template file
            try:
                import shutil

                shutil.copy2(template_source, template_in_save_dir)
                logger.info(f"Copied {template_filename} to {template_in_save_dir}")
            except Exception as e:
                logger.warning(f"Failed to copy {template_filename}: {e}")
        else:
            logger.warning(f"Could not find {template_filename} source to copy")

    def _update_slssteam_status(self):
        """Check and display SLSsteam installation status"""
        from core.tasks.download_slssteam_task import DownloadSLSsteamTask

        try:
            # Run in a thread to avoid blocking UI
            import threading

            def check_status():
                status = DownloadSLSsteamTask.check_update_available()

                # Update UI in main thread
                self.slssteam_status_label.setText(self._format_status_text(status))

            thread = threading.Thread(target=check_status, daemon=True)
            thread.start()
        except Exception as e:
            logger.error(f"Failed to check SLSsteam status: {e}")
            self.slssteam_status_label.setText("Error checking status")

    def _format_status_text(self, status):
        """Format the status text for display"""
        if status.get("error"):
            return "Status: Unknown (error checking)"

        installed = status.get("installed", False)
        latest_version = status.get("latest_version", "Unknown")
        update_available = status.get("update_available", False)

        if not installed:
            return f"Not installed • Latest: {latest_version}"
        else:
            if update_available:
                return f"Update available • Latest: {latest_version}"
            else:
                installed_version = status.get("installed_version", "Unknown")
                return f"Up to date • Version: {installed_version}"

    def download_slssteam(self):
        """Download and install SLSsteam from GitHub releases"""
        if sys.platform != "linux":
            QMessageBox.warning(
                self,
                "Platform Not Supported",
                "SLSsteam download is only available on Linux.",
            )
            return

        # Check if 7z command is available
        import shutil

        if not shutil.which("7z") and not shutil.which("7za"):
            QMessageBox.critical(
                self,
                "Missing Dependency",
                "p7zip is not installed. Please install it first:\n\n"
                "After installation, restart ACCELA and try again.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Download SLSsteam",
            "This will download the latest SLSsteam from GitHub and install it.\n\n"
            "The download will run in the background.\n"
            "You will be notified when the installation is complete.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        try:
            if self.main_window and hasattr(self.main_window, "task_manager"):
                self.main_window.task_manager.download_slssteam()
                # Dialog can close now - download runs independently
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Error", "Could not access task manager. Please try again."
                )
        except Exception as e:
            error_msg = f"Failed to start SLSsteam download: {e}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "Error", error_msg)

    def run_slscheevo(self):
        """Launch SLScheevo in the terminal"""
        try:
            slscheevo_path = self._get_slscheevo_path()

            if not os.path.exists(slscheevo_path):
                QMessageBox.critical(
                    self, "Error", f"SLScheevo not found at:\n{slscheevo_path}"
                )
                return

            logger.info(f"Launching SLScheevo from: {slscheevo_path}")
            save_dir = self._get_save_dir_path()

            # Prepare command
            if str(slscheevo_path).endswith(".py"):
                py_exec = "python" if sys.platform == "win32" else "python3"
                command = [
                    py_exec,
                    str(slscheevo_path),
                    "--save-dir",
                    str(save_dir),
                    "--noclear",
                    "--max-tries",
                    "101",
                ]
            else:
                command = [
                    str(slscheevo_path),
                    "--save-dir",
                    str(save_dir),
                    "--noclear",
                    "--max-tries",
                    "101",
                ]

            working_dir = os.path.dirname(slscheevo_path)

            launched = False

            if sys.platform == "win32":
                # Try cmd and PowerShell
                windows_commands = [
                    ["cmd", "/c"] + command,
                    ["powershell", "-Command"] + command,
                ]
                for cmd in windows_commands:
                    try:
                        subprocess.Popen(cmd, cwd=working_dir)
                        launched = True
                        break
                    except FileNotFoundError:
                        continue
            else:
                linux_terminals = [
                    ["wezterm", "start", "--always-new-process", "--"] + command,
                    ["konsole", "-e"] + command,
                    ["gnome-terminal", "--"] + command,
                    ["alacritty", "-e"] + command,
                    ["tilix", "-e"] + command,
                    ["xfce4-terminal", "-e"] + command,
                    ["terminator", "-x"] + command,
                    ["mate-terminal", "-e"] + command,
                    ["lxterminal", "-e"] + command,
                    ["xterm", "-e"] + command,
                    ["kitty", "-e"] + command,
                ]
                for cmd in linux_terminals:
                    try:
                        subprocess.Popen(cmd, cwd=working_dir)
                        launched = True
                        break
                    except FileNotFoundError:
                        continue

            if not launched:
                # Show manual command in a copyable text box
                venv_command = [f"source {str(get_base_path() / '.venv' / 'bin' / 'activate')}", "&&"]
                venv_command.extend(command)
                command_text = f"bash -c \'{' '.join(venv_command)}\'"
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Terminal Not Found")
                msg_box.setText(
                    "Could not automatically launch a terminal.\n\n"
                    "Please run the following command manually:"
                )
                msg_box.setInformativeText(command_text)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

                text_edit = QTextEdit()
                text_edit.setReadOnly(True)
                text_edit.setText(command_text)
                text_edit.setMinimumSize(600, 80)
                msg_box.layout().addWidget(
                    text_edit, 1, 0, 1, msg_box.layout().columnCount()
                )
                msg_box.exec()

        except Exception as e:
            error_msg = f"Failed to launch SLScheevo: {e}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "Error", error_msg)
