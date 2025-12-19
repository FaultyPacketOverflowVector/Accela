import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox

try:
    import psutil
except ImportError:
    psutil = None

from core import steam_helpers
from core.tasks.download_depots_task import DownloadDepotsTask
from core.tasks.download_slssteam_task import DownloadSLSsteamTask
from core.tasks.generate_achievements_task import GenerateAchievementsTask
from core.tasks.monitor_speed_task import SpeedMonitorTask
from core.tasks.process_zip_task import ProcessZipTask
from core.tasks.steamless_task import SteamlessTask
from ui.dialogs.depotselection import DepotSelectionDialog
from ui.dialogs.dlcselection import DlcSelectionDialog
from ui.dialogs.steamlibrary import SteamLibraryDialog
from utils.helpers import get_base_path
from utils.task_runner import TaskRunner

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.settings = main_window.settings

        # Task state
        self.speed_monitor_task = None
        self.speed_monitor_runner = None
        self.is_awaiting_speed_monitor_stop = False

        self.zip_task = None
        self.zip_task_runner = None
        self.is_awaiting_zip_task_stop = False

        self.download_task = None
        self.download_runner = None
        self.achievement_task = None
        self.achievement_task_runner = None
        self.achievement_worker = None
        self.steamless_task = None
        self.slssteam_download_task = None
        self.slssteam_download_runner = None

        # Processing state
        self.is_processing = False
        self.is_download_paused = False
        self.is_cancelling = False
        self.current_job = None
        self.game_data = None
        self.current_dest_path = None
        self.slssteam_mode_was_active = False
        self._steamless_success = None

    def start_zip_processing(self, zip_path):
        """Start processing a ZIP file"""
        self.is_processing = True
        self.current_job = zip_path

        self.main_window.progress_bar.setVisible(True)
        self.main_window.progress_bar.setRange(0, 0)
        self.main_window.drop_text_label.setText(
            f"Processing: {os.path.basename(zip_path)}"
        )

        self.zip_task = ProcessZipTask()
        self.zip_task_runner = TaskRunner()
        self.is_awaiting_zip_task_stop = True
        self.zip_task_runner.cleanup_complete.connect(self._on_zip_task_stopped)

        worker = self.zip_task_runner.run(self.zip_task.run, zip_path)
        worker.finished.connect(self._on_zip_processed)
        worker.error.connect(self._handle_task_error)

    def _on_zip_processed(self, game_data):
        """Handle completed ZIP processing"""
        self.main_window.progress_bar.setRange(0, 100)
        self.main_window.progress_bar.setValue(100)
        self.game_data = game_data

        if self.game_data and self.game_data.get("depots"):
            self._show_depot_selection_dialog()
        else:
            QMessageBox.warning(
                self.main_window,
                "No Depots Found",
                "Zip file processed, but no downloadable depots were found.",
            )
            self.job_finished()

    def _show_depot_selection_dialog(self):
        """Show depot selection dialog"""
        self.main_window.ui_state.depot_dialog = DepotSelectionDialog(
            self.game_data["appid"],
            self.game_data["game_name"],
            self.game_data["depots"],
            self.game_data.get("header_url"),
            self.main_window,
        )

        if self.main_window.ui_state.depot_dialog.exec():
            selected_depots = (
                self.main_window.ui_state.depot_dialog.get_selected_depots()
            )

            # Store selected depots for ACF generation
            if self.game_data:
                self.game_data["selected_depots_list"] = selected_depots

            if not selected_depots:
                self.job_finished()
                return

            dest_path = self._get_destination_path()
            if dest_path:
                self._start_download(selected_depots, dest_path)
            else:
                self.job_finished()
        else:
            self.job_finished()

    def _get_destination_path(self):
        """Get destination path based on current mode"""
        slssteam_mode = self.settings.value("slssteam_mode", False, type=bool)
        library_mode = self.settings.value("library_mode", False, type=bool)

        if slssteam_mode:
            self._handle_slssteam_mode()
            return self._get_library_destination_path()
        elif library_mode:
            return self._get_library_destination_path()
        else:
            return QFileDialog.getExistingDirectory(
                self.main_window, "Select Destination Folder"
            )

    def _get_library_destination_path(self):
        libraries = steam_helpers.get_steam_libraries()
        if libraries:
            dialog = SteamLibraryDialog(libraries, self.main_window)
            if dialog.exec():
                return dialog.get_selected_path()
            else:
                return None
        else:
            return QFileDialog.getExistingDirectory(
                self.main_window, "Select Destination Folder"
            )

    def _handle_slssteam_mode(self):
        """Handle SLSsteam mode specific setup"""
        if sys.platform == "win32" and self.game_data.get("dlcs"):
            logger.info(
                "Windows detected in SLSsteam mode, showing DLC selection dialog for GreenLuma."
            )
            dlc_dialog = DlcSelectionDialog(self.game_data["dlcs"], self.main_window)
            if dlc_dialog.exec():
                self.game_data["selected_dlcs"] = dlc_dialog.get_selected_dlcs()
        elif self.game_data.get("dlcs"):
            logger.info(
                "SLSsteam mode active on non-Windows OS, skipping DLC selection."
            )

    def _start_download(self, selected_depots, dest_path):
        """Start the download process"""
        self.current_dest_path = dest_path
        self.slssteam_mode_was_active = self.settings.value(
            "slssteam_mode", False, type=bool
        )
        self.is_cancelling = False

        self.main_window.ui_state.switch_to_download_gif()
        self.main_window.drop_text_label.setText(f"Downloading: {self.game_data.get("game_name", "")}")

        self.main_window.progress_bar.setVisible(True)
        self.main_window.progress_bar.setValue(0)
        self.main_window.speed_label.setVisible(True)

        self.download_task = DownloadDepotsTask()
        self.download_task.progress.connect(logger.info)
        self.download_task.progress_percentage.connect(self.main_window.progress_bar.setValue)
        self.download_task.completed.connect(self._on_download_complete)
        self.download_task.error.connect(self._handle_task_error)

        self.download_runner = TaskRunner()
        worker = self.download_runner.run(self.download_task.run, self.game_data, selected_depots, dest_path)
        worker.error.connect(self._handle_task_error)

        self._start_speed_monitor()
        self.is_download_paused = False
        self.main_window.ui_state.pause_button.setText("Pause")
        self.main_window.ui_state.pause_button.setVisible(True)
        self.main_window.ui_state.cancel_button.setVisible(True)

    def _start_speed_monitor(self):
        """Start speed monitoring task"""
        self.speed_monitor_task = SpeedMonitorTask()
        self.speed_monitor_task.speed_update.connect(
            self.main_window.speed_label.setText
        )

        self.speed_monitor_runner = TaskRunner()
        self.speed_monitor_runner.cleanup_complete.connect(
            self._on_speed_monitor_stopped
        )
        self.speed_monitor_runner.run(self.speed_monitor_task.run)

    def _stop_speed_monitor(self):
        """Stop speed monitoring task"""
        if self.speed_monitor_task:
            logger.debug("Sending stop signal to SpeedMonitorTask.")
            self.speed_monitor_task.stop()
            self.speed_monitor_task = None
        else:
            if self.is_awaiting_speed_monitor_stop:
                logger.debug("Speed monitor was already stopped. Updating flag.")
                self.is_awaiting_speed_monitor_stop = False
                self.main_window.job_queue._check_if_safe_to_start_next_job()

    def _on_speed_monitor_stopped(self):
        """Handle speed monitor cleanup completion"""
        logger.debug("SpeedMonitorTask's worker has officially completed cleanup.")
        self.speed_monitor_runner = None
        self.is_awaiting_speed_monitor_stop = False
        self.main_window.job_queue._check_if_safe_to_start_next_job()

    def _on_zip_task_stopped(self):
        """Handle ZIP task cleanup completion"""
        logger.debug("ProcessZipTask's worker has officially completed cleanup.")
        self.zip_task_runner = None
        self.is_awaiting_zip_task_stop = False
        self.main_window.job_queue._check_if_safe_to_start_next_job()

    def _on_download_complete(self):
        """Handle download completion"""
        if self.is_cancelling:
            logger.info("Download complete signal received, job was cancelled. Cleaning up...")
            self._cleanup_cancelled_job_files()
            self.job_finished()
            return

        self._stop_speed_monitor()
        self.main_window.progress_bar.setValue(100)

        if not self.game_data:
            logger.warning("_on_download_complete called, but game_data is None. Job was likely cancelled or errored.")
            if self.is_processing:
                self.job_finished()
            return

        # Get total size for ACF file
        size_on_disk = 0
        if self.download_task:
            size_on_disk = self.download_task.total_download_size_for_this_job
            logger.info(f"Retrieved SizeOnDisk from download task: {size_on_disk}")
        else:
            logger.warning("Download task object is gone, SizeOnDisk will be 0.")
        self._create_acf_file(size_on_disk)
        self._move_manifests_to_depotcache()

        # Save main depot info to persistent file
        if self.game_data:
            selected_depots = self.game_data.get("selected_depots_list", [])
            all_manifests = self.game_data.get("manifests", {})
            if selected_depots and all_manifests:
                self._save_main_depot_info(
                    self.game_data, selected_depots, all_manifests
                )

        # Set executable permissions for Linux binaries
        if sys.platform == "linux":
            self._set_linux_binary_permissions()

        # Check if Steamless is enabled - run before achievements
        steamless_enabled = self.settings.value("use_steamless", False, type=bool)

        if steamless_enabled and not self.is_cancelling:
            logger.info("Steamless is enabled, starting DRM removal after download completion")
            self.main_window.drop_text_label.setText(f"Running Steamless: {self.game_data.get("game_name", "")}")
            self._start_steamless_processing()
            return

        # If Steamless is not enabled, check for achievements
        achievements_enabled = self.settings.value("generate_achievements", False, type=bool)
        if achievements_enabled and not self.is_cancelling:
            logger.info("Achievement generation is enabled, starting after download completion")
            self.main_window.drop_text_label.setText(f"Generating Achievements: {self.game_data.get("game_name", "")}")
            self._start_achievement_generation()
            return

        if self.slssteam_mode_was_active:
            if sys.platform == "win32":
                logger.info("Windows Wrapper Mode active. Creating GreenLuma AppList files...")
                self.main_window.drop_text_label.setText(f"Creating GreenLuma AppList")
                steam_path = steam_helpers.find_steam_install()
                if steam_path:
                    self._create_greenluma_applist_files(steam_path)
                else:
                    logger.error("Could not find Steam path. Skipping GreenLuma file creation.")

            self.main_window.job_queue.slssteam_prompt_pending = True

        self.main_window.job_queue.jobs_completed_count += 1

        # Auto-scan the game library after download completes
        if not self.is_cancelling:
            logger.info("Auto-scanning game library for updated games...")
            self.main_window.game_manager.scan_steam_libraries()

        self.job_finished()

    def _save_main_depot_info(self, game_data, selected_depots, all_manifests):
        """
        Save main depot ID and manifest to persistent file.

        Args:
            game_data: Dictionary containing game metadata
            selected_depots: List of selected depot IDs
            all_manifests: Dictionary mapping depot_id → manifest_gid
        """
        try:
            # Get appid from game_data
            appid = game_data.get("appid")
            if not appid:
                logger.warning("Cannot save depot info: missing appid")
                return

            # Get the main depot (first in selected list)
            if not selected_depots:
                logger.warning(f"Cannot save depot info for app {appid}: no selected depots")
                return

            main_depot_id = str(selected_depots[0])  # Convert to string for consistency

            # Get manifest_id for the main depot
            manifest_id = all_manifests.get(main_depot_id)
            if not manifest_id:
                logger.warning(f"Cannot save depot info for app {appid}: no manifest found for depot {main_depot_id}")
                return

            # Construct file path
            depots_dir = Path(get_base_path()) / "depots"
            depots_dir.mkdir(parents=True, exist_ok=True)

            depot_file = depots_dir / f"{appid}.depot"

            # Write the depot info file
            with open(depot_file, "w") as f:
                f.write(f"{main_depot_id}: {manifest_id}\n")

            logger.info(f"Saved main depot info: {appid}:{manifest_id} → {depot_file}")

        except Exception as e:
            # Log error but don't fail the download
            logger.error(f"Failed to save depot info: {e}")

    def _create_acf_file(self, size_on_disk):
        """Create Steam ACF manifest file"""
        logger.info("Generating Steam .acf manifest file...")

        safe_game_name_fallback = (
            re.sub(r"[^\w\s-]", "", self.game_data.get("game_name", ""))
            .strip()
            .replace(" ", "_")
        )
        install_folder_name = self.game_data.get("installdir", safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{self.game_data['appid']}"

        self.main_window.drop_text_label.setText(f"Generating .acf for {safe_game_name_fallback}")

        acf_path = os.path.join(
            self.current_dest_path,
            "steamapps",
            f"appmanifest_{self.game_data['appid']}.acf",
        )

        # Build depot string
        buildid = self.game_data.get("buildid", "0")
        depots_content = ""
        selected_depots = self.game_data.get("selected_depots_list", [])
        all_manifests = self.game_data.get("manifests", {})
        all_depots = self.game_data.get("depots", {})

        # Platform configuration logic
        platform_config = ""
        empty_platform_config = (
            '\t"UserConfig"\n'
            '\t{\n'
            '\t}\n'
            '\t"MountedConfig"\n'
            '\t{\n'
            '\t}'
        )

        # Determine platform-specific configuration
        if sys.platform == "linux":
            downloading_windows_depots = False
            downloading_linux_depots = False

            logger.info(f"Checking depot platforms for {len(selected_depots)} selected depots...")

            for depot_id in selected_depots:
                depot_id_str = str(depot_id)  # Ensure it's a string lookup
                depot_info = all_depots.get(depot_id_str, {})
                try:
                    platform = (depot_info.get("oslist") or "").lower() or "unknown"
                except Exception:
                    platform = "unknown"

                logger.info(f"Depot {depot_id_str}: platform='{platform}', config={depot_info.get('config', {})}")

                # Check both platform field and config for platform information
                if platform == "windows":
                    downloading_windows_depots = True
                    logger.info(f"  -> Identified as Windows depot")
                elif platform == "linux":
                    downloading_linux_depots = True
                    logger.info(f"  -> Identified as Linux depot")

            logger.info(f"Platform detection summary - Windows: {downloading_windows_depots}, Linux: {downloading_linux_depots}")

            # Configure based on depot types
            if downloading_windows_depots:
                logger.info("Windows depots on Linux - adding Proton configuration")
                platform_config = (
                    '\t"UserConfig"\n'
                    '\t{\n'
                    '\t\t"platform_override_dest"\t\t"linux"\n'
                    '\t\t"platform_override_source"\t\t"windows"\n'
                    '\t}\n'
                    '\t"MountedConfig"\n'
                    '\t{\n'
                    '\t\t"platform_override_dest"\t\t"linux"\n'
                    '\t\t"platform_override_source"\t\t"windows"\n'
                    '\t}'
                )
            elif downloading_linux_depots:
                logger.info("Linux depots on Linux - adding empty platform config")
                platform_config = empty_platform_config
            else:
                logger.info("No platform-specific depots detected - adding empty platform config")
                platform_config = empty_platform_config
        else:
            platform_config = empty_platform_config
            logger.info(f"Non-Linux platform ({sys.platform}) - adding empty platform config")

        # Build depot content
        if selected_depots and all_manifests:
            for depot_id in selected_depots:
                depot_id_str = str(depot_id)
                manifest_gid = all_manifests.get(depot_id_str)
                depot_info = all_depots.get(depot_id_str, {})
                depot_size = depot_info.get("size", "0")

                if manifest_gid:
                    depots_content += (
                        f'\t\t"{depot_id_str}"\n'
                        f'\t\t{{\n'
                        f'\t\t\t"manifest"\t\t"{manifest_gid}"\n'
                        f'\t\t\t"size"\t\t"{depot_size}"\n'
                        f'\t\t}}\n'
                    )
                else:
                    logger.warning(f"Could not find manifest GID for selected depot {depot_id_str}")

        # Format installed depots section
        if depots_content and sys.platform == "win32":
            installed_depots_str = f'\t"InstalledDepots"\n\t{{\n{depots_content}\t}}'
        else:
            installed_depots_str = '\t"InstalledDepots"\n\t{\n\t}'

        acf_content = (
            f'"AppState"\n'
            f'{{\n'
            f'\t"appid"\t\t"{self.game_data["appid"]}"\n'
            f'\t"Universe"\t\t"1"\n'
            f'\t"name"\t\t"{self.game_data["game_name"]}"\n'
            f'\t"StateFlags"\t\t"4"\n'
            f'\t"installdir"\t\t"{install_folder_name}"\n'
            f'\t"SizeOnDisk"\t\t"{size_on_disk}"\n'
            f'\t"buildid"\t\t"{buildid}"\n'
            f'{installed_depots_str}'
        )

        if platform_config:
            acf_content += f'\n{platform_config}'

        # Final bracket
        acf_content += '\n}'

        try:
            with open(acf_path, "w", encoding="utf-8") as f:
                f.write(acf_content)
            logger.info(f"Created .acf file at {acf_path}")
        except IOError as e:
            logger.error(f"Error creating .acf file: {e}")

    def _move_manifests_to_depotcache(self):
        if not self.game_data or not self.current_dest_path:
            logger.error("Missing game data or destination path. Cannot move manifests.")
            return

        temp_manifest_dir = os.path.join(tempfile.gettempdir(), "mistwalker_manifests")

        if not os.path.exists(temp_manifest_dir):
            logger.warning(f"Temp manifest directory not found, nothing to move: {temp_manifest_dir}")
            return

        target_depotcache_dir = os.path.join(self.current_dest_path, "depotcache")

        try:
            os.makedirs(target_depotcache_dir, exist_ok=True)
            logger.info(f"Ensured depotcache directory exists at: {target_depotcache_dir}")
            manifests_map = self.game_data.get("manifests", {})

            if not manifests_map:
                logger.info("No manifest information found in game data.")
                # Clean up the empty temp dir anyway
                shutil.rmtree(temp_manifest_dir)
                logger.info(f"Removed temporary manifest directory (no manifests to move): {temp_manifest_dir}")
                return

            moved_count = 0
            for depot_id, manifest_gid in manifests_map.items():
                manifest_filename = f"{depot_id}_{manifest_gid}.manifest"
                source_path = os.path.join(temp_manifest_dir, manifest_filename)
                dest_path = os.path.join(target_depotcache_dir, manifest_filename)
                if os.path.exists(source_path):
                    shutil.move(source_path, dest_path)
                    logger.info(f"Moved {manifest_filename} to {target_depotcache_dir}")
                    moved_count += 1
                else:
                    # This case can happen if a manifest wasn't in the zip but was in the LUA
                    logger.warning(f"Manifest file not found in temp, skipping: {source_path}")
            logger.info(f"Moved {moved_count} manifest files to depotcache.")
            # Clean up the now (hopefully) empty temp manifest directory
            shutil.rmtree(temp_manifest_dir)
            logger.info(f"Removed temporary manifest directory: {temp_manifest_dir}")
        except Exception as e:
            logger.error(f"Failed to move manifests to depotcache: {e}", exc_info=True)
            logger.info(f"Error moving manifests: {e}")

    def _set_linux_binary_permissions(self):
        """Set executable permissions for Linux binaries after download"""
        if not self.game_data or not self.current_dest_path:
            logger.warning("Missing game data or destination path. Cannot set binary permissions.")
            return

        # Get the game directory using the same logic as download task
        safe_game_name_fallback = (
            re.sub(r"[^\w\s-]", "", self.game_data.get("game_name", ""))
            .strip()
            .replace(" ", "_")
        )
        install_folder_name = self.game_data.get("installdir", safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{self.game_data['appid']}"

        game_directory = os.path.join(
            self.current_dest_path, "steamapps", "common", install_folder_name
        )

        if not os.path.exists(game_directory):
            logger.warning(f"Game directory not found at {game_directory}, skipping permission setup")
            return

        logger.info(f"Setting executable permissions for Linux binaries in: {game_directory}")

        # Common Linux binary extensions
        linux_binary_extensions = {".sh", ".x86", ".x86_64", ".bin"}

        # ELF magic bytes
        elf_magic = b"\x7fELF"

        chmod_count = 0

        for root, dirs, files in os.walk(game_directory):
            for file in files:
                file_path = os.path.join(root, file)
                file_lower = file.lower()

                # Skip very small files (unlikely to be game binaries)
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size < 1024:  # Less than 1KB
                        continue
                except OSError:
                    continue

                should_chmod = False

                # Check by extension first
                if any(file_lower.endswith(ext) for ext in linux_binary_extensions):
                    should_chmod = True
                # Check if file has no extension (common for Linux binaries)
                elif "." not in file:
                    # Only check extensionless files that might be binaries
                    # Check for ELF header
                    try:
                        with open(file_path, "rb") as f:
                            header = f.read(4)
                            if header == elf_magic:
                                should_chmod = True
                    except (IOError, OSError):
                        continue

                if should_chmod:
                    try:
                        # Check if already executable
                        current_mode = os.stat(file_path).st_mode
                        if not (current_mode & 0o111):  # Not executable
                            os.chmod(file_path, current_mode | 0o755)
                            logger.debug(f"Set executable: {file_path}")
                            chmod_count += 1
                    except OSError as e:
                        logger.warning(f"Could not set permissions for {file_path}: {e}")

        if chmod_count > 0:
            logger.info(f"Set executable permissions for {chmod_count} Linux binary files")
        else:
            logger.info("No Linux binaries found that needed permission changes")

    def _start_steamless_processing(self):
        """Start Steamless DRM removal after download completion"""
        if not self.current_dest_path or not self.game_data:
            logger.warning("No destination path or game data found, skipping Steamless processing")
            # Continue to achievements check
            achievements_enabled = self.settings.value("generate_achievements", False, type=bool)
            if achievements_enabled and not self.is_cancelling:
                self._start_achievement_generation()
            else:
                self._continue_after_download()
            return

        # Get the game directory using the same logic as download task
        safe_game_name_fallback = (
            re.sub(r"[^\w\s-]", "", self.game_data.get("game_name", ""))
            .strip()
            .replace(" ", "_")
        )
        install_folder_name = self.game_data.get("installdir", safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{self.game_data['appid']}"

        game_directory = os.path.join(
            self.current_dest_path, "steamapps", "common", install_folder_name
        )

        if not os.path.exists(game_directory):
            logger.warning(f"Game directory not found at {game_directory}, skipping Steamless processing")
            # Continue to achievements check
            achievements_enabled = self.settings.value("generate_achievements", False, type=bool)
            if achievements_enabled and not self.is_cancelling:
                self._start_achievement_generation()
            else:
                self._continue_after_download()
            return

        logger.info("\n" + "=" * 40)
        logger.info("Starting Steamless DRM Removal...")
        logger.info(f"Processing directory: {game_directory}")

        self.steamless_task = SteamlessTask()
        self.steamless_task.progress.connect(logger.info)
        self.steamless_task.result.connect(self._on_steamless_complete)
        self.steamless_task.finished.connect(self._on_steamless_finished)
        self.steamless_task.error.connect(self._handle_steamless_task_error)
        self.steamless_task.set_game_directory(game_directory)
        self.steamless_task.start()

    def _on_steamless_complete(self, success):
        """Handle Steamless processing completion"""
        logger.info("\n" + "=" * 40)
        if success:
            logger.info("Steamless processing completed successfully")
        else:
            logger.info("Steamless processing completed with warnings or no DRM found")

        # Store the result for _on_steamless_finished to use
        # This prevents duplicate achievement generation starts
        self._steamless_success = success

    def _on_steamless_finished(self):
        """Handle Steamless thread finished"""
        # The thread has finished (run() returned)
        # Defer cleanup to next event loop tick to ensure thread is fully done
        if self.steamless_task:
            logger.debug("Steamless thread finished, scheduling cleanup")
            QTimer.singleShot(0, self._clear_steamless_task)

        # Only continue to achievements if Steamless actually ran
        # (prevents double-starting achievements)
        if self._steamless_success is not None:
            self._steamless_success = None  # Reset

            # Continue to achievement generation if enabled
            achievements_enabled = self.settings.value("generate_achievements", False, type=bool)
            if achievements_enabled and not self.is_cancelling:
                logger.info("Starting achievement generation after Steamless completion")
                self._start_achievement_generation()
            else:
                self._continue_after_download()

    def _clear_steamless_task(self):
        """Clear steamless task reference on next event loop tick"""
        logger.debug("Clearing steamless task reference")
        self.steamless_task = None

    def _handle_steamless_task_error(self, error_info):
        """Handle Steamless task runner errors"""
        _, error_value, _ = error_info
        logger.info(f"Steamless error: {error_value}")
        logger.error(f"Steamless processing failed: {error_value}", exc_info=error_info)

        # The thread has already finished (run() returned)
        # Defer cleanup to next event loop tick
        if self.steamless_task:
            logger.debug("Steamless thread error, scheduling cleanup")
            QTimer.singleShot(0, self._clear_steamless_task)

        # Note: steamless_task_runner and steamless_worker are not used for SteamlessTask
        # SteamlessTask is a QThread, not managed by TaskRunner

        # Continue to achievement generation even if Steamless failed
        achievements_enabled = self.settings.value("generate_achievements", False, type=bool)
        if achievements_enabled and not self.is_cancelling:
            self._start_achievement_generation()
        else:
            self._continue_after_download()

    def _start_achievement_generation(self):
        """Start achievement generation task"""
        app_id = self.game_data.get("appid")
        if not app_id:
            logger.warning("No AppID found, skipping achievement generation")
            self._continue_after_download()
            return

        logger.info("\n" + "=" * 40)
        logger.info("Starting Steam Achievement Generation...")
        logger.info("Auto-detecting account from SLScheevo...")

        self.achievement_task = GenerateAchievementsTask()
        self.achievement_task.progress.connect(logger.info)
        # Do NOT connect progress_percentage to progress bar - achievement generation
        # happens after download completion and should not interfere with the 100% progress
        # self.achievement_task.progress_percentage.connect(self.progress_bar.setValue)

        self.achievement_task_runner = TaskRunner()
        self.achievement_worker = self.achievement_task_runner.run(self.achievement_task.run, app_id)
        self.achievement_task_runner.cleanup_complete.connect(self._on_achievement_task_cleanup)

        self.achievement_worker.finished.connect(self._on_achievement_generation_complete)
        self.achievement_worker.error.connect(self._handle_achievement_error)

    def _on_achievement_generation_complete(self, result):
        """Handle achievement generation completion"""
        # Defensive check in case result is None
        if result is None:
            success = False
            message = "Unknown error: result is None"
        else:
            success = result.get("success", False)
            message = result.get("message", "Unknown status")

        logger.info("\n" + "=" * 40)
        if success:
            logger.info(f"Achievement generation completed: {message}")
        else:
            logger.info(f"Achievement generation failed: {message}")

        # Cleanup will happen via TaskRunner's cleanup_complete signal
        # Do NOT set to None here - wait for proper cleanup
        logger.debug(
            "Achievement generation complete, waiting for TaskRunner cleanup..."
        )
        self._continue_after_download()

    def _handle_achievement_error(self, error_info):
        """Handle achievement generation errors"""
        _, error_value, _ = error_info
        logger.info(f"Achievement generation error: {error_value}")
        logger.error(f"Achievement generation failed: {error_value}", exc_info=error_info)

        # Cleanup will happen via TaskRunner's cleanup_complete signal
        # Do NOT set to None here - wait for proper cleanup
        logger.debug("Achievement generation error, waiting for TaskRunner cleanup...")
        self._continue_after_download()

    def _on_achievement_task_cleanup(self):
        """Handle achievement task cleanup completion"""
        logger.debug("AchievementTask's worker has officially completed cleanup.")
        self.achievement_task_runner = None
        self.achievement_task = None
        self.achievement_worker = None
        self.main_window.job_queue._check_if_safe_to_start_next_job()

    def _continue_after_download(self):
        """Continue with the normal download completion flow"""
        if self.slssteam_mode_was_active:
            if sys.platform == "win32":
                logger.info("Windows Wrapper Mode active. Creating GreenLuma AppList files...")
                steam_path = steam_helpers.find_steam_install()
                if steam_path:
                    self._create_greenluma_applist_files(steam_path)
                else:
                    logger.error("Could not find Steam path. Skipping GreenLuma file creation.")

            self.main_window.job_queue.slssteam_prompt_pending = True

        self.main_window.job_queue.jobs_completed_count += 1

        # Auto-scan the game library after download completes
        if not self.is_cancelling:
            logger.info("Auto-scanning game library for updated games...")
            self.main_window.game_manager.scan_steam_libraries()

        self.job_finished()

    def _create_greenluma_applist_files(self, steam_path):
        """Create GreenLuma AppList files"""
        try:
            app_list_dir = os.path.join(steam_path, "AppList")

            if not os.path.exists(app_list_dir):
                os.makedirs(app_list_dir)
                logger.info(f"Created AppList directory at: {app_list_dir}")

            game_appid = self.game_data.get("appid")
            if not game_appid:
                logger.error("No AppID found, cannot create main AppList file.")
                return

            if not self._app_id_exists_in_applist(app_list_dir, game_appid):
                next_num = self._find_next_applist_number(app_list_dir)
                filepath = os.path.join(app_list_dir, f"{next_num}.txt")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(game_appid)
                logger.info(f"Created GreenLuma file: {filepath} for AppID: {game_appid}")
            else:
                logger.info(f"AppID {game_appid} already exists in AppList folder. Skipping file creation.")

            if "selected_dlcs" in self.game_data:
                for dlc_id in self.game_data["selected_dlcs"]:
                    if not self._app_id_exists_in_applist(app_list_dir, dlc_id):
                        next_num = self._find_next_applist_number(app_list_dir)
                        filepath = os.path.join(app_list_dir, f"{next_num}.txt")
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(dlc_id)
                        logger.info(f"Created GreenLuma file: {filepath} for DLC: {dlc_id}")
                    else:
                        logger.info(f"DLC AppID {dlc_id} already exists in AppList folder. Skipping file creation.")

        except Exception as e:
            logger.error(f"Failed to create GreenLuma AppList files: {e}", exc_info=True)

    @staticmethod
    def _find_next_applist_number(app_list_dir):
        """Find the next available AppList number"""
        if not os.path.exists(app_list_dir):
            os.makedirs(app_list_dir)
            return 1

        max_num = 0
        try:
            for filename in os.listdir(app_list_dir):
                match = re.match(r"^(\d+)\.txt$", filename)
                if match:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
        except Exception as e:
            logger.error(f"Error scanning AppList directory: {e}")

        return max_num + 1

    @staticmethod
    def _app_id_exists_in_applist(app_list_dir, app_id_to_check):
        """Check if AppID already exists in AppList"""
        if not os.path.exists(app_list_dir):
            return False

        try:
            for filename in os.listdir(app_list_dir):
                if filename.lower().endswith(".txt"):
                    filepath = os.path.join(app_list_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content == app_id_to_check:
                                logger.debug(f"Found existing AppID {app_id_to_check} in file: {filename}")
                                return True
                    except Exception as e:
                        logger.error(f"Error reading AppList file {filepath}: {e}")
        except Exception as e:
            logger.error(f"Error scanning AppList directory {app_list_dir}: {e}")

        return False

    def _handle_task_error(self, error_info):
        """Handle general task errors"""
        if self.is_cancelling:
            logger.info("Task error signal received, but job was cancelled. Suppressing error message.")
            return

        if not self.is_processing:
            logger.warning(f"Task error received, but no job is processing. Ignoring. Error: {error_info}")
            return

        _, error_value, _ = error_info
        QMessageBox.critical(self.main_window, "Error", f"An error occurred: {error_value}")
        if not self.is_cancelling:
            self.job_finished()

    def job_finished(self):
        """Clean up after job completion"""
        if not self.is_processing:
            logger.warning("_job_finished called, but no job is processing. Ignoring.")
            return

        logger.info(f"Job '{os.path.basename(self.current_job or 'Unknown')}' finished. Cycling to next job.")

        self.main_window.ui_state._show_main_gif()

        self.main_window.progress_bar.setVisible(False)
        self.main_window.speed_label.setVisible(False)
        self.game_data = None
        self.current_dest_path = None
        self.slssteam_mode_was_active = False

        self.is_processing = False
        self.current_job = None

        self.is_download_paused = False
        self.main_window.ui_state.pause_button.setVisible(False)
        self.main_window.ui_state.cancel_button.setVisible(False)
        self.download_task = None
        self.download_runner = None
        self.is_cancelling = False
        # Achievement and steamless clean up via their own signals/threads - don't clear here

        logger.info("\n" + "=" * 40 + "\n")

        if self.speed_monitor_task:
            logger.debug("Job finished, telling speed monitor to stop.")
            self.is_awaiting_speed_monitor_stop = True
            self._stop_speed_monitor()
        else:
            self.is_awaiting_speed_monitor_stop = False
            logger.debug("Job finished, no speed monitor running.")

        if self.zip_task_runner is None:
            self.is_awaiting_zip_task_stop = False

        self.main_window.job_queue._check_if_safe_to_start_next_job()

    def toggle_pause(self):
        """Toggle download pause/resume"""
        if not self.download_task:
            return

        self.is_download_paused = not self.is_download_paused

        try:
            self.download_task.toggle_pause(self.is_download_paused)
            if self.is_download_paused:
                self.main_window.ui_state.pause_button.setText("Resume")
                self.main_window.drop_text_label.setText(f"Paused: {os.path.basename(self.current_job)}")
                self._stop_speed_monitor()
            else:
                self.main_window.ui_state.pause_button.setText("Pause")
                self.main_window.drop_text_label.setText(f"Downloading: {os.path.basename(self.current_job)}")
                self._start_speed_monitor()
        except Exception as e:
            logger.error(f"Failed to toggle pause: {e}")
            QMessageBox.warning(self.main_window, "Error", f"Could not pause/resume download: {e}")

    def cancel_current_job(self):
        """Cancel the current job"""
        if not self.download_task or not self.current_job:
            logger.warning("Cancel button clicked, but no download task or job is active.")
            return

        reply = QMessageBox.question(
            self.main_window,
            "Cancel Job",
            f"Are you sure you want to cancel the download for '{os.path.basename(self.current_job)}'?\n\nThis will delete all downloaded files for this job.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        logger.info(f"--- Cancelling job: {os.path.basename(self.current_job)} ---")
        self.is_cancelling = True
        self.download_task.stop()
        self._kill_download_process()

        if self.achievement_task:
            logger.info("Stopping achievement generation task...")
            self.achievement_task.stop()
            # Don't set to None immediately - wait for TaskRunner cleanup
            # self.achievement_task = None
            # self.achievement_task_runner = None
            # self.achievement_worker = None

        if self.steamless_task:
            logger.info("Stopping Steamless task...")
            self.steamless_task.stop()
            # SteamlessTask will be cleaned up via the finished/error signals
            # Wait for it to finish before clearing the reference

    def _kill_download_process(self):
        """Kill the download process"""
        if self.download_task and self.download_task.process:
            logger.info("Terminating active download process...")
            try:
                p = psutil.Process(self.download_task.process.pid)
                for child in p.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                p.kill()
                logger.info("Download process terminated.")
            except psutil.NoSuchProcess:
                logger.warning(f"Process {self.download_task.process.pid} already exited.")
            except Exception as e:
                logger.error(f"Failed to kill process: {e}")

            self.download_task.process = None
            self.download_task.process_pid = None

    def _cleanup_cancelled_job_files(self):
        """Clean up files from cancelled job"""
        if not self.game_data or not self.current_dest_path:
            logger.error("Cancel cleanup failed: missing game_data or current_dest_path.")
            return

        try:
            safe_game_name_fallback = (
                re.sub(r"[^\w\s-]", "", self.game_data.get("game_name", ""))
                .strip()
                .replace(" ", "_")
            )
            install_folder_name = self.game_data.get("installdir", safe_game_name_fallback)
            if not install_folder_name:
                install_folder_name = f"App_{self.game_data['appid']}"

            steamapps_dir = os.path.join(self.current_dest_path, "steamapps")
            common_dir = os.path.join(steamapps_dir, "common")
            game_dir = os.path.join(common_dir, install_folder_name)
            acf_path = os.path.join(
                steamapps_dir, f"appmanifest_{self.game_data['appid']}.acf"
            )

            if os.path.exists(game_dir):
                shutil.rmtree(game_dir)
                logger.info(f"Removed cancelled job directory: {game_dir}")
            else:
                logger.info(f"Download directory not found, nothing to clean: {game_dir}")

            if os.path.exists(acf_path):
                os.remove(acf_path)
                logger.info(f"Removed cancelled job manifest: {acf_path}")

            temp_manifest_dir = os.path.join(
                tempfile.gettempdir(), "mistwalker_manifests"
            )
            if os.path.exists(temp_manifest_dir):
                try:
                    shutil.rmtree(temp_manifest_dir)
                    logger.info(f"Removed temporary manifest directory: {temp_manifest_dir}")
                    logger.info(f"Removed temp manifest dir on cancel: {temp_manifest_dir}")
                except Exception as e:
                    logger.error(f"Failed to remove temp manifest dir on cancel: {e}")

            if not self.slssteam_mode_was_active:
                logger.info(
                    "Normal mode: Attempting to clean up empty parent directories..."
                )
                try:
                    if os.path.exists(common_dir):
                        os.rmdir(common_dir)
                        logger.info(f"Removed empty common dir: {common_dir}")

                    if os.path.exists(steamapps_dir):
                        os.rmdir(steamapps_dir)
                        logger.info(f"Removed empty steamapps dir: {steamapps_dir}")

                except OSError as e:
                    logger.warning(f"Could not remove parent directory (likely not empty): {e}")
                except Exception as e:
                    logger.error(f"Error during parent directory cleanup: {e}", exc_info=True)
            else:
                logger.info("Wrapper mode: Skipping parent directory cleanup.")

        except Exception as e:
            logger.error(f"Failed during cancel cleanup: {e}", exc_info=True)

    def download_slssteam(self):
        """Download and install the latest SLSsteam from GitHub releases"""
        logger.info("Starting SLSsteam download and installation")

        # Check if already running
        if self.slssteam_download_task is not None and self.slssteam_download_runner is not None:
            QMessageBox.information(
                self.main_window,
                "Already Running",
                "SLSsteam download is already in progress. Please wait for it to complete.",
            )
            return

        self.slssteam_download_task = DownloadSLSsteamTask()
        self.slssteam_download_task.progress.connect(self._handle_slssteam_progress)
        self.slssteam_download_task.progress_percentage.connect(
            self._handle_slssteam_progress_percentage
        )
        self.slssteam_download_task.completed.connect(
            self._on_slssteam_download_complete
        )
        self.slssteam_download_task.error.connect(self._handle_slssteam_download_error)

        self.slssteam_download_runner = TaskRunner()
        worker = self.slssteam_download_runner.run(self.slssteam_download_task.run)
        worker.error.connect(self._handle_task_error)

    def _handle_slssteam_progress(self, message):
        """Handle SLSsteam download progress messages"""
        logger.info(f"SLSsteam: {message}")

    def _handle_slssteam_progress_percentage(self, percentage):
        """Handle SLSsteam download progress percentage"""
        logger.debug(f"SLSsteam progress: {percentage}%")

    def _on_slssteam_download_complete(self, message):
        """Handle SLSsteam download completion"""
        logger.info(f"SLSsteam download completed: {message}")
        QMessageBox.information(self.main_window, "SLSsteam Installation Complete", message)
        self.slssteam_download_task = None
        self.slssteam_download_runner = None

    def _handle_slssteam_download_error(self):
        """Handle SLSsteam download errors"""
        logger.error("SLSsteam download failed")
        QMessageBox.critical(
            self.main_window,
            "Error",
            "Failed to download and install SLSsteam. Please check your internet connection and try again.",
        )
        self.slssteam_download_task = None
        self.slssteam_download_runner = None

    def cleanup(self):
        """Clean up all tasks during shutdown"""
        self._stop_speed_monitor()

        if self.download_task and self.download_task.process:
            self.download_task.stop()
            self._kill_download_process()

        if self.achievement_task:
            self.achievement_task.stop()
            # Don't set to None immediately - wait for TaskRunner cleanup
            # self.achievement_task = None
            # self.achievement_task_runner = None
            # self.achievement_worker = None

        if self.steamless_task:
            self.steamless_task.stop()
            # SteamlessTask will be cleaned up via the finished/error signals
            # Wait for it to finish before the window closes

        if self.slssteam_download_task:
            self.slssteam_download_task.stop()
            self.slssteam_download_runner = None
            self.slssteam_download_task = None
