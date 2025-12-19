import logging
import os
import subprocess
import tempfile
import shutil
import json
import stat
from pathlib import Path

import requests
import yaml

from PyQt6.QtCore import QObject, pyqtSignal

from utils.helpers import get_base_path

logger = logging.getLogger(__name__)


class DownloadSLSsteamTask(QObject):
    progress = pyqtSignal(str)
    progress_percentage = pyqtSignal(int)
    completed = pyqtSignal(str)
    error = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        """Download and install SLSsteam from GitHub releases"""
        logger.info("Starting SLSsteam download task")

        try:
            slssteam_dir = get_base_path() / "SLSsteam"

            self.progress.emit("Fetching latest SLSsteam release information...")
            release_data = self._fetch_latest_release()

            if not release_data:
                self.progress.emit("Error: Could not fetch release information from GitHub")
                self.error.emit()
                return

            self.progress.emit(f"Latest release: {release_data.get('tag_name', 'Unknown')}")

            download_url = self._find_7z_download_url(release_data)
            if not download_url:
                self.progress.emit("Error: Could not find SLSsteam-Any.7z in releases")
                self.error.emit()
                return

            self.progress.emit(f"Downloading {download_url}")
            temp_dir = tempfile.mkdtemp()

            try:
                downloaded_file = self._download_file(download_url, temp_dir)

                self.progress.emit(f"Extracting archive to {slssteam_dir}")

                # Create directory if it doesn't exist
                slssteam_dir.mkdir(parents=True, exist_ok=True)

                if os.path.exists(slssteam_dir):
                    self.progress.emit("Removing old SLSsteam installation...")
                    shutil.rmtree(slssteam_dir)
                    slssteam_dir.mkdir(parents=True, exist_ok=True)

                self._extract_7z(downloaded_file, slssteam_dir)

                # Look for setup.sh in the extracted files (may be at root or in subdirs)
                setup_script = self._find_setup_script(slssteam_dir)
                if not setup_script:
                    self.progress.emit("Error: setup.sh not found in archive")
                    self.error.emit()
                    return

                self.progress.emit(f"Found setup.sh at: {setup_script}")
                self.progress.emit("Setting up SLSsteam...")
                self._run_setup_script(setup_script, slssteam_dir)

                # Ensure PlayNotOwnedGames is enabled in config
                self.progress.emit("Configuring PlayNotOwnedGames setting...")
                self._ensure_play_not_owned_games_enabled()

                # Save version info
                self._save_version_info(slssteam_dir, release_data.get("tag_name", "Unknown"))

                self.progress.emit("SLSsteam installation completed successfully!")
                self.completed.emit("SLSsteam has been successfully downloaded and installed.")

            finally:
                self._cleanup_temp_dir(temp_dir)

        except Exception as e:
            logger.error(f"SLSsteam download task failed: {e}", exc_info=True)
            self.progress.emit(f"Error: {e}")
            self.error.emit()
            raise

    def _fetch_latest_release(self):
        """Fetch the latest release from GitHub API"""
        url = "https://api.github.com/repos/AceSLS/SLSsteam/releases/latest"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch GitHub release: {e}")
            return None

    def _find_7z_download_url(self, release_data):
        """Find the SLSsteam-Any.7z download URL from release data"""
        assets = release_data.get("assets", [])
        for asset in assets:
            if asset.get("name") == "SLSsteam-Any.7z":
                return asset.get("browser_download_url")
        return None

    def _download_file(self, url, dest_dir):
        """Download file from URL with progress tracking"""
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        filename = "SLSsteam-Any.7z"
        dest_path = os.path.join(dest_dir, filename)

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if not self._is_running:
                    raise Exception("Download cancelled")

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        percentage = int((downloaded / total_size) * 100)
                        self.progress_percentage.emit(percentage)

        return dest_path

    def _extract_7z(self, archive_path, dest_dir):
        """Extract 7z archive using system 7z command"""
        logger.info(f"Extracting {archive_path} to {dest_dir}")

        # Try both 7z and 7za (p7zip command)
        for cmd in ["7z", "7za"]:
            result = subprocess.run(
                [cmd, "x", archive_path, f"-o{dest_dir}", "-y"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"Archive extracted successfully using {cmd}")
                return

        # If both failed
        logger.error(f"7z extraction failed. stderr: {result.stderr}")
        raise Exception(f"7z extraction failed. Please ensure p7zip is installed: {result.stderr}")

    @staticmethod
    def check_update_available():
        """Check if an update is available for SLSsteam"""
        try:
            response = requests.get(
                "https://api.github.com/repos/AceSLS/SLSsteam/releases/latest",
                timeout=10
            )
            response.raise_for_status()
            release_data = response.json()

            latest_version = release_data.get("tag_name", "Unknown")
            latest_date = release_data.get("published_at", "")

            # Check if SLSsteam is installed (check both ACCELA installation and manual installation)
            xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
            slssteam_dir = Path(xdg_data_home) / "ACCELA" / "SLSsteam"
            slssteam_manual = Path(xdg_data_home) / "SLSsteam" / "SLSsteam.so"

            # Check if SLSsteam is installed either through ACCELA or manually
            accela_installed = slssteam_dir.exists()
            manual_installed = slssteam_manual.exists()

            if not accela_installed and not manual_installed:
                return {
                    "update_available": True,
                    "latest_version": latest_version,
                    "latest_date": latest_date,
                    "installed": False,
                    "installed_version": None
                }

            # Check for version file in ACCELA installation
            installed_version = None
            is_accela_install = False
            if accela_installed:
                version_file = slssteam_dir / "VERSION"
                if version_file.exists():
                    with open(version_file, 'r') as f:
                        installed_version = f.read().strip()
                    is_accela_install = True

            # Only compare versions if we have a version file (ACCELA installation)
            # For manual installations, we can't determine the version, so don't show update available
            if is_accela_install and installed_version:
                update_available = installed_version != latest_version
            else:
                # Manual installation or no version file - assume up to date
                # (we can't easily determine the version of manually installed SLSsteam)
                update_available = False
                installed_version = "Unknown (manual install)" if not is_accela_install else "Unknown"

            return {
                "update_available": update_available,
                "latest_version": latest_version,
                "latest_date": latest_date,
                "installed": True,
                "installed_version": installed_version
            }

        except Exception as e:
            logger.error(f"Failed to check for SLSsteam updates: {e}")
            return {
                "update_available": False,
                "latest_version": "Unknown",
                "latest_date": "",
                "installed": False,
                "installed_version": None,
                "error": str(e)
            }

    def _find_setup_script(self, base_dir):
        """Recursively search for setup.sh in the extracted directory"""
        for root, dirs, files in os.walk(base_dir):
            if "setup.sh" in files:
                return os.path.join(root, "setup.sh")
        return None

    def _save_version_info(self, slssteam_dir, version):
        """Save the installed version to a VERSION file"""
        try:
            version_file = slssteam_dir / "VERSION"
            with open(version_file, 'w') as f:
                f.write(version)
            logger.info(f"Saved version {version} to VERSION file")
        except Exception as e:
            logger.warning(f"Failed to save version info: {e}")

    def _run_setup_script(self, script_path, work_dir):
        """Execute setup.sh script"""
        st = os.stat(script_path)
        os.chmod(script_path, st.st_mode | stat.S_IEXEC)

        self.progress.emit("Running setup.sh install...")

        process = subprocess.Popen(
            [script_path, "install"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=work_dir
        )

        for line in iter(process.stdout.readline, ""):
            if not self._is_running:
                process.terminate()
                raise Exception("Setup cancelled")
            self.progress.emit(f"setup.sh: {line.strip()}")

        process.wait()

        if process.returncode != 0:
            raise Exception(f"setup.sh failed with exit code {process.returncode}")

    def _cleanup_temp_dir(self, temp_dir):
        """Clean up temporary directory"""
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp dir {temp_dir}: {e}")

    def _ensure_play_not_owned_games_enabled(self):
        """Ensure PlayNotOwnedGames is enabled in SLSsteam config.yaml"""
        try:
            # Use XDG_CONFIG_HOME if set, otherwise default to ~/.config
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
            if xdg_config_home:
                config_path = Path(xdg_config_home) / "SLSsteam" / "config.yaml"
            else:
                config_path = Path.home() / ".config" / "SLSsteam" / "config.yaml"

            if not config_path.exists():
                logger.info(f"SLSsteam config.yaml not found at {config_path}, skipping PlayNotOwnedGames check")
                return

            logger.info(f"Checking SLSsteam config at {config_path}")

            # Read existing config
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}

            # Check if PlayNotOwnedGames is already True
            play_not_owned = config_data.get('PlayNotOwnedGames', False)

            if play_not_owned:
                logger.info("PlayNotOwnedGames is already enabled")
                return

            # Set PlayNotOwnedGames to True
            config_data['PlayNotOwnedGames'] = True

            # Write back to file
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            logger.info("Successfully enabled PlayNotOwnedGames in SLSsteam config")
            self.progress.emit("PlayNotOwnedGames setting enabled in SLSsteam config")

        except Exception as e:
            logger.warning(f"Failed to enable PlayNotOwnedGames setting: {e}")
            # Don't emit error - this is not critical for the installation

    def stop(self):
        """Stop the task"""
        logger.info("SLSsteam download task received stop signal")
        self._is_running = False
