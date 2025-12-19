import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from utils.helpers import resource_path

try:
    import psutil
except ImportError:
    logging.critical(
        "Failed to import 'psutil'. Pausing/resuming downloads will not work."
    )
    psutil = None

logger = logging.getLogger(__name__)


class StreamReader(QObject):
    new_line = pyqtSignal(str)

    def __init__(self, stream, task_instance):
        super().__init__()
        self.stream = stream
        self._is_running = True
        self.task_instance = task_instance

    def run(self):
        try:
            for line in iter(self.stream.readline, ""):
                if not self._is_running:
                    break
                if not self.task_instance._is_running:
                    break
                self.new_line.emit(line)
        except ValueError:
            logger.debug(
                "StreamReader ValueError: Stream was likely closed forcefully."
            )
        except Exception as e:
            if self.task_instance._is_running:
                logger.error(f"StreamReader error: {e}", exc_info=True)
        finally:
            try:
                self.stream.close()
            except Exception:
                pass

    def stop(self):
        self._is_running = False


class DownloadDepotsTask(QObject):
    progress = pyqtSignal(str)
    progress_percentage = pyqtSignal(int)
    completed = pyqtSignal()
    error = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._is_running = True
        self.percentage_regex = re.compile(r"(\d{1,3}\.\d{2})%")
        self.last_percentage = -1
        self.process = None
        self.process_pid = None

        self.total_download_size_for_this_job = 0
        self.completed_so_far_for_this_job = 0
        self.current_depot_size = 0

    def run(self, game_data, selected_depots, dest_path):
        global command
        logger.info(f"Download task starting for {len(selected_depots)} depots.")

        commands, skipped_depots, depot_sizes = self._prepare_downloads(
            game_data, selected_depots, dest_path
        )
        if not commands:
            self.progress.emit("No valid download commands to execute. Task finished.")
            self.completed.emit()
            return

        total_depots = len(commands)

        self.total_download_size_for_this_job = sum(depot_sizes)
        self.completed_so_far_for_this_job = 0
        logger.info(
            f"Task tracking total download size: {self.total_download_size_for_this_job} bytes"
        )

        try:
            for i, command in enumerate(commands):
                if not self._is_running:
                    logger.info("Download task stopping before next depot.")
                    break

                depot_id = command[4]
                self.current_depot_size = depot_sizes[i]
                self.progress.emit(
                    f"--- Starting download for depot {depot_id} ({i + 1}/{total_depots}) [Size: {self.current_depot_size} bytes] ---"
                )
                self.last_percentage = -1

                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                )

                self.process_pid = self.process.pid

                reader_thread = QThread()
                stream_reader = StreamReader(self.process.stdout, self)
                stream_reader.moveToThread(reader_thread)

                stream_reader.new_line.connect(self._handle_downloader_output)
                reader_thread.started.connect(stream_reader.run)

                reader_thread.start()
                self.process.wait()

                stream_reader.stop()
                reader_thread.quit()
                reader_thread.wait()

                if not self._is_running:
                    logger.info("Download task stopping because stop() was called.")
                    self.completed.emit()
                    return

                return_code = self.process.returncode
                self.process = None
                self.process_pid = None

                if return_code != 0:
                    self.progress.emit(
                        f"Warning: DepotDownloaderMod exited with code {return_code} for depot {depot_id}."
                    )
                    logger.warning(
                        f"DepotDownloaderMod exited with code {return_code} for depot {depot_id}."
                    )
                else:
                    self.completed_so_far_for_this_job += self.current_depot_size

            if skipped_depots:
                self.progress.emit(
                    f"Skipped {len(skipped_depots)} depots due to missing manifests: {', '.join(skipped_depots)}"
                )

            if not self._is_running:
                logger.info("Download task stopped before cleanup.")
                self.completed.emit()
                return

            self.progress.emit("--- Cleaning up temporary files ---")
            temp_dir = tempfile.gettempdir()
            items_to_clean = {
                "mistwalker_keys.vdf": os.path.join(temp_dir, "mistwalker_keys.vdf"),
            }

            for name, path in items_to_clean.items():
                if os.path.exists(path):
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                            self.progress.emit(f"Removed temp directory '{name}'.")
                        else:
                            os.remove(path)
                            self.progress.emit(f"Removed temp file '{name}'.")
                    except OSError as e:
                        self.progress.emit(f"Error removing temp item '{name}': {e}")

            # Ensure PlayNotOwnedGames is enabled in SLSsteam config
            self._ensure_play_not_owned_games_enabled()

            self.completed.emit()

        except FileNotFoundError:
            exe_name = "DepotDownloaderMod"
            if "command" in locals() and command:
                exe_name = command[0]
            self.progress.emit(
                f"ERROR: '{exe_name}' not found. Make sure it's in the application's directory."
            )
            logger.critical(f"'{exe_name}' not found.")
            self.error.emit()
            raise
        except Exception as e:
            self.progress.emit(f"An unexpected error occurred during download: {e}")
            logger.error(f"Download subprocess failed: {e}", exc_info=True)
            self.process = None
            self.process_pid = None
            self.error.emit()
            raise

    def _handle_downloader_output(self, line):
        if not self._is_running:
            return
        line = line.strip()
        self.progress.emit(line)
        match = self.percentage_regex.search(line)
        if match:
            percentage = float(match.group(1))

            if self.total_download_size_for_this_job > 0:
                progress_of_current_depot = (
                    percentage / 100.0
                ) * self.current_depot_size

                total_progress_bytes = (
                    self.completed_so_far_for_this_job + progress_of_current_depot
                )

                total_percentage = int(
                    (total_progress_bytes / self.total_download_size_for_this_job) * 100
                )

                total_percentage = max(0, min(100, total_percentage))

                if total_percentage != self.last_percentage:
                    self.progress_percentage.emit(total_percentage)
                    self.last_percentage = total_percentage
            else:
                int_percentage = int(percentage)
                if int_percentage != self.last_percentage:
                    self.progress_percentage.emit(int_percentage)
                    self.last_percentage = int_percentage

    def _prepare_downloads(self, game_data, selected_depots, dest_path):
        temp_dir = tempfile.gettempdir()
        keys_path = os.path.join(temp_dir, "mistwalker_keys.vdf")
        manifest_dir = os.path.join(temp_dir, "mistwalker_manifests")

        self.progress.emit(f"Generating depot keys file at {keys_path}")
        with open(keys_path, "w") as f:
            for depot_id in selected_depots:
                if depot_id in game_data["depots"]:
                    f.write(f"{depot_id};{game_data['depots'][depot_id]['key']}\n")

        safe_game_name_fallback = (
            re.sub(r"[^\w\s-]", "", game_data.get("game_name", ""))
            .strip()
            .replace(" ", "_")
        )
        install_folder_name = game_data.get("installdir", safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{game_data['appid']}"

        download_dir = os.path.join(
            dest_path, "steamapps", "common", install_folder_name
        )
        os.makedirs(download_dir, exist_ok=True)
        self.progress.emit(f"Download destination set to: {download_dir}")

        if sys.platform == "win32":
            exe_name = resource_path("deps/DepotDownloaderMod.exe")
        else:
            exe_name = resource_path("deps/DepotDownloaderMod")
            # Only try chmod if we are allowed to write the file's metadata
            if os.access(exe_name, os.W_OK):
                st = os.stat(exe_name)
                new_mode = st.st_mode | stat.S_IEXEC
                try:
                    os.chmod(exe_name, new_mode)
                except PermissionError:
                    pass  # silently ignore if fs blocks us (read-only, no perms)

        commands = []
        skipped_depots = []
        depot_sizes = []

        # Validate that manifests exist in game_data
        if not game_data.get("manifests"):
            self.progress.emit(
                "ERROR: No manifest files found in the zip. The zip file may be incomplete or corrupted."
            )
            logger.error(
                "No 'manifests' key found in game_data. Cannot proceed with download."
            )
            raise Exception(
                "No manifest files were detected in the zip. Please ensure you're using a zip from a trusted source."
            )

        for depot_id in selected_depots:
            manifest_id = game_data.get("manifests", {}).get(depot_id)
            if not manifest_id:
                self.progress.emit(
                    f"Warning: No manifest ID for depot {depot_id}. Skipping."
                )
                skipped_depots.append(str(depot_id))
                continue

            try:
                size_str = game_data["depots"][depot_id].get("size")
                if size_str:
                    depot_sizes.append(int(size_str))
                else:
                    depot_sizes.append(0)
                    self.progress.emit(
                        f"Warning: No size data for depot {depot_id}. Total progress may be inaccurate."
                    )
            except (ValueError, TypeError):
                depot_sizes.append(0)
                self.progress.emit(
                    f"Warning: Invalid size data for depot {depot_id}. Total progress may be inaccurate."
                )

            manifest_file_path = os.path.join(
                manifest_dir, f"{depot_id}_{manifest_id}.manifest"
            )

            commands.append(
                [
                    exe_name,
                    "-app",
                    game_data["appid"],
                    "-depot",
                    str(depot_id),
                    "-manifest",
                    manifest_id,
                    "-manifestfile",
                    manifest_file_path,
                    "-depotkeys",
                    keys_path,
                    "-max-downloads",
                    "25",
                    "-dir",
                    download_dir,
                    "-validate",
                ]
            )

        return commands, skipped_depots, depot_sizes

    def stop(self):
        logger.debug("Stop signal received by download task.")
        self._is_running = False

    def toggle_pause(self, pause):
        global status
        if not psutil:
            logger.error("psutil not found. Cannot pause or resume.")
            raise Exception("psutil library is not loaded.")

        if not self.process_pid:
            logger.warning("Attempted to pause/resume, but no process is running.")
            return

        try:
            parent = psutil.Process(self.process_pid)
            children = parent.children(recursive=True)
            processes = [parent] + children

            for proc in processes:
                try:
                    if pause:
                        proc.suspend()
                    else:
                        proc.resume()
                except psutil.NoSuchProcess:
                    logger.warning(f"Process {proc.pid} no longer exists. Skipping.")

            status = "paused" if pause else "resumed"
            logger.info(f"Download process tree {status}.")

        except psutil.NoSuchProcess:
            logger.error(
                f"Main process {self.process_pid} not found. Cannot pause/resume."
            )
            self.process_pid = None
            self.process = None
        except Exception as e:
            logger.error(f"An error occurred while trying to {status} process: {e}")
            raise

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
            # Don't emit error - this is not critical for the download
