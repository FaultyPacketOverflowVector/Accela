import logging
import os
import re
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.steam_helpers import get_steam_libraries
from core.tasks.manifest_check_task import ManifestCheckTask
from utils.helpers import get_base_path
from utils.task_runner import TaskRunner

logger = logging.getLogger(__name__)

# Update status constants
UPDATE_STATUS = {
    "UPDATE_AVAILABLE": "update_available",
    "UP_TO_DATE": "up_to_date",
    "CANNOT_DETERMINE": "cannot_determine",
    "CHECKING": "checking",  # While async update check is running
}


class GameManager(QObject):
    """
    Manager for handling game library operations.
    Manages game metadata, library view, and game-related operations.
    """

    # Signals
    game_updated = pyqtSignal(str)
    library_updated = pyqtSignal()
    game_selected = pyqtSignal(str)
    scan_complete = pyqtSignal(int)  # Emits number of games found
    game_update_status_changed = pyqtSignal(str, str)  # (appid, update_status)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.settings = main_window.settings

        # Game library data
        self.games = []
        self.selected_game = None
        self.filtered_games = []

        # Manifest check task management
        self.manifest_check_task = None
        self.manifest_check_runner = None
        self._games_to_check = []

        logger.info("GameManager initialized")

    def add_game(self, game_data):
        """Add a game to the library"""
        # TODO: Implement game addition logic
        logger.info(f"Adding game to library: {game_data.get('game_name', 'Unknown')}")
        self.games.append(game_data)
        self._apply_filters()
        self.library_updated.emit()

    def remove_game(self, game_id):
        """Remove a game from the library"""
        # TODO: Implement game removal logic
        logger.info(f"Removing game from library: {game_id}")
        self.games = [g for g in self.games if g.get("appid") != game_id]
        self._apply_filters()
        self.library_updated.emit()

    def get_game(self, game_id):
        """Get a specific game by ID"""
        for game in self.games:
            if game.get("appid") == game_id:
                return game
        return None

    def get_all_games(self):
        """Get all games in the library"""
        return self.filtered_games if self.filtered_games else self.games

    def select_game(self, game_id):
        """Select a specific game"""
        game = self.get_game(game_id)
        if game:
            self.selected_game = game
            self.game_selected.emit(game_id)
            logger.info(
                f"Selected game: {game.get('game_name', 'Unknown')} ({game_id})"
            )
            return True
        return False

    def update_game(self, game_id, game_data):
        """Update game information"""
        # TODO: Implement game update logic
        logger.info(f"Updating game: {game_id}")
        for i, game in enumerate(self.games):
            if game.get("appid") == game_id:
                self.games[i].update(game_data)
                self.game_updated.emit(game_id)
                self._apply_filters()
                self.library_updated.emit()
                return True
        return False

    def _apply_filters(self):
        """Apply current filters to the game list"""
        # TODO: Implement filtering logic
        self.filtered_games = self.games

    def search_games(self, query):
        """Search games by name or other criteria"""
        # TODO: Implement search functionality
        if not query:
            self.filtered_games = self.games
            return

        query = query.lower()
        self.filtered_games = [
            game for game in self.games if query in game.get("game_name", "").lower()
        ]
        self.library_updated.emit()

    def clear_filters(self):
        """Clear all applied filters"""
        self.filtered_games = []
        self._apply_filters()
        self.library_updated.emit()

    def check_game_updates_async(self):
        """
        Start async update checking for all games in the library.
        Games appear with 'checking' status initially, then update individually.
        """
        # Cancel any existing task by stopping it and waiting for cleanup
        if self.manifest_check_task is not None:
            logger.info("Cancelling previous manifest check task")
            old_task = self.manifest_check_task
            old_task.stop()
            # Don't disconnect or set to None here - let the task finish and clean itself up
            # This prevents race conditions

        # Get games with valid appids
        self._games_to_check = [g for g in self.games if g.get("appid") not in ("0", "N/A", "unknown")]

        if not self._games_to_check:
            logger.info("No games with valid appids to check")
            return

        logger.info(f"Starting async update check for {len(self._games_to_check)} games")

        # Create new task
        self.manifest_check_task = ManifestCheckTask(self._games_to_check)

        # Connect signals
        self.manifest_check_task.game_update_checked.connect(self._on_game_update_checked)
        self.manifest_check_task.progress.connect(self._on_update_check_progress)
        self.manifest_check_task.completed.connect(self._on_update_check_completed)
        self.manifest_check_task.error.connect(self._on_update_check_error)

        # Start task via TaskRunner
        self.manifest_check_runner = TaskRunner()
        # Connect to cleanup_complete to clear references AFTER thread finishes
        self.manifest_check_runner.cleanup_complete.connect(self._on_manifest_check_runner_cleanup)
        self.manifest_check_runner.run(self.manifest_check_task.run)

    def _on_game_update_checked(self, appid, update_status):
        """Handle individual game update check result"""
        # Find and update the game
        for game in self.games:
            if game.get("appid") == appid:
                game["update_status"] = update_status
                logger.debug(f"Updated status for game {appid}: {update_status}")
                # Emit specific signal for individual game update (UI can choose to update just that item)
                self.game_update_status_changed.emit(appid, update_status)
                break

    def _on_update_check_progress(self, current, total):
        """Handle update check progress"""
        logger.debug(f"Update check progress: {current}/{total}")

    def _on_update_check_completed(self):
        """Handle update check completion"""
        logger.info("All game updates checked")
        # Note: We don't clear references here
        # They will be cleared by _on_manifest_check_runner_cleanup when thread finishes

    def _on_update_check_error(self, error_info):
        """Handle update check error"""
        exc_type, exc_msg, exc_traceback = error_info
        logger.error(f"Error during update check: {exc_msg}", exc_info=(exc_type, exc_msg, exc_traceback))
        # Note: We don't clear references here
        # They will be cleared by _on_manifest_check_runner_cleanup when thread finishes

    def _on_manifest_check_runner_cleanup(self):
        """Handle TaskRunner cleanup completion - called when thread finishes"""
        logger.debug("TaskRunner cleanup complete, clearing references")
        self.manifest_check_task = None
        self.manifest_check_runner = None
        self._games_to_check = []



    def scan_steam_libraries(self):
        """Scan Steam library directories for games installed by ACCELA"""
        logger.info("Starting scan of Steam libraries for ACCELA-installed games...")

        # Clear existing games before scanning
        self.games.clear()

        steam_libraries = get_steam_libraries()

        if not steam_libraries:
            logger.warning("No Steam libraries found")
            self.scan_complete.emit(0)
            return 0

        logger.info(f"Found {len(steam_libraries)} Steam library location(s)")

        games_found = 0
        scanned_libraries = 0

        for library_path in steam_libraries:
            logger.info(f"Scanning library: {library_path}")
            scanned_libraries += 1

            steamapps_path = os.path.join(library_path, "steamapps")
            if not os.path.exists(steamapps_path):
                logger.warning(f"Steamapps directory not found at: {steamapps_path}")
                continue

            common_path = os.path.join(steamapps_path, "common")
            if not os.path.exists(common_path):
                logger.warning(f"Common directory not found at: {common_path}")
                continue

            # Scan for games with .DepotDownloader folders
            try:
                for game_name in os.listdir(common_path):
                    game_path = os.path.join(common_path, game_name)
                    if not os.path.isdir(game_path):
                        continue

                    depot_downloader_path = os.path.join(game_path, ".DepotDownloader")
                    if os.path.exists(depot_downloader_path):
                        # Check if folder has actual game content (not just .DepotDownloader)
                        if self._has_game_content(game_path):
                            # Found a game installed by ACCELA
                            game_data = self._collect_game_data(
                                game_path, game_name, library_path
                            )
                            if game_data:
                                self.games.append(game_data)
                                games_found += 1
                                logger.info(f"  Found ACCELA game: {game_name}")
                        else:
                            logger.info(f"  Skipped empty game folder: {game_name}")

            except OSError as e:
                logger.error(f"Error scanning {common_path}: {e}")

        logger.info(
            f"Scan complete. Scanned {scanned_libraries} library location(s), found {games_found} ACCELA-installed game(s)"
        )
        self._apply_filters()
        self.library_updated.emit()
        self.scan_complete.emit(games_found)

        # Start async update checking for all collected games
        if games_found > 0:
            logger.info("Starting async update check for collected games")
            self.check_game_updates_async()

        return games_found

    def _has_game_content(self, game_path):
        """
        Check if the game folder has actual content beyond .DepotDownloader
        Returns True if there are files or folders other than .DepotDownloader
        """
        try:
            for item in os.listdir(game_path):
                if item == ".DepotDownloader":
                    # Skip the .DepotDownloader folder
                    continue
                # Check if it's a file or another directory
                item_path = os.path.join(game_path, item)
                if os.path.isfile(item_path) or os.path.isdir(item_path):
                    # Found something other than .DepotDownloader
                    return True
            return False
        except OSError:
            return False

    def _collect_game_data(self, game_path, game_name, library_path):
        """
        Collect game data from installation directory.
        Returns a dictionary with game information.
        """
        try:
            # Try to read appmanifest to get AppID and other metadata
            appmanifest_path = None
            appid = None

            # Look for appmanifest files in steamapps
            steamapps_path = os.path.join(library_path, "steamapps")
            if os.path.exists(steamapps_path):
                logger.debug(f"Looking for ACF match for game: '{game_name}'")
                for filename in os.listdir(steamapps_path):
                    if filename.startswith("appmanifest_") and filename.endswith(
                        ".acf"
                    ):
                        test_manifest_path = os.path.join(steamapps_path, filename)

                        # Parse ACF to check if this is the right game
                        try:
                            with open(test_manifest_path, "r", encoding="utf-8") as f:
                                content = f.read()
                                # Extract installdir using regex
                                match = re.search(r'"installdir"\s+"([^"]+)"', content)
                                if match:
                                    installdir = match.group(1)
                                    logger.debug(
                                        f"  Checking {filename}: installdir='{installdir}'"
                                    )

                                    # Check if this manifest matches the current game
                                    if installdir == game_name:
                                        appmanifest_path = test_manifest_path
                                        # Extract appid from filename
                                        appid = filename.replace(
                                            "appmanifest_", ""
                                        ).replace(".acf", "")
                                        logger.debug(f"  ✓ Match found! AppID: {appid}")
                                        logger.info(
                                            f"Successfully determined AppID for '{game_name}': {appid}"
                                        )
                                        break  # Found the right manifest, stop looking
                        except Exception as e:
                            logger.debug(f"  Error parsing {filename}: {e}")
                            pass

            # Warn if AppID could not be determined
            if not appid:
                logger.warning(
                    f"FAILED to determine AppID for '{game_name}'. Game will have AppID='0' (unknown). This may happen if the ACF file's installdir doesn't match the folder name exactly."
                )

            # Initialize game data dictionary early so we can populate it
            # Determine install directory name
            install_dir = game_name

            game_data = {
                "appid": appid or "0",
                "game_name": game_name,
                "install_dir": install_dir,
                "install_path": game_path,
                "library_path": library_path,
                "size_on_disk": 0,  # Will be calculated below
                "source": "ACCELA",
                "depot_downloader_path": os.path.join(game_path, ".DepotDownloader"),
            }

            # Get file size - try ACF first, fall back to manual calculation
            size_on_disk = 0
            acf_size_available = False

            # Check for ACF file data first
            if appmanifest_path and os.path.exists(appmanifest_path):
                try:
                    with open(appmanifest_path, "r", encoding="utf-8") as f:
                        content = f.read()

                        # Extract name using regex
                        name_match = re.search(r'"name"\s+"([^"]+)"', content)
                        if name_match:
                            game_data["game_name"] = name_match.group(1)

                        # Extract buildid using regex
                        buildid_match = re.search(r'"buildid"\s+"([^"]+)"', content)
                        if buildid_match:
                            game_data["buildid"] = buildid_match.group(1)

                        # Extract LastUpdated using regex
                        lastupdated_match = re.search(
                            r'"LastUpdated"\s+"([^"]+)"', content
                        )
                        if lastupdated_match:
                            game_data["last_updated"] = lastupdated_match.group(1)

                        # Extract SizeOnDisk using regex (only use if non-zero)
                        sizeon_disk_match = re.search(
                            r'"SizeOnDisk"\s+"([^"]+)"', content
                        )
                        if sizeon_disk_match:
                            acf_size = int(sizeon_disk_match.group(1))
                            # Only use ACF size if it's greater than 0
                            if acf_size > 0:
                                size_on_disk = acf_size
                                acf_size_available = True
                                logger.debug(
                                    f"Using ACF SizeOnDisk for {game_name}: {size_on_disk} bytes"
                                )
                except Exception as e:
                    logger.debug(f"Could not parse ACF file {appmanifest_path}: {e}")

            # Only calculate size manually if ACF doesn't have a valid SizeOnDisk
            if not acf_size_available:
                logger.debug(
                    f"ACF SizeOnDisk not available, calculating size manually for {game_name}"
                )
                try:
                    for dirpath, dirnames, filenames in os.walk(game_path):
                        for filename in filenames:
                            filepath = os.path.join(dirpath, filename)
                            if os.path.exists(filepath):
                                size_on_disk += os.path.getsize(filepath)
                except OSError:
                    pass

            # Update the size in game_data
            game_data["size_on_disk"] = size_on_disk

            # Set default update status to "checking" - will be checked asynchronously
            # Only if appid is valid
            if appid and appid not in ("0", "N/A", "unknown"):
                game_data["update_status"] = UPDATE_STATUS["CHECKING"]
            else:
                game_data["update_status"] = UPDATE_STATUS["CANNOT_DETERMINE"]

            return game_data

        except Exception as e:
            logger.error(
                f"Error collecting game data for {game_name}: {e}", exc_info=True
            )
            return None

    def clear_library(self):
        """Clear all games from the library"""
        logger.info("Clearing entire game library")
        self.games.clear()
        self.filtered_games.clear()
        self.selected_game = None
        self.library_updated.emit()

    def import_library(self, file_path):
        """Import library from a file"""
        # TODO: Implement library import
        logger.info(f"Importing library from: {file_path}")
        return False

    def get_library_stats(self):
        """Get statistics about the game library"""
        total_games = len(self.games)
        total_size = sum(game.get("size_on_disk", 0) for game in self.games)

        return {
            "total_games": total_games,
            "total_size": total_size,
            "filtered_count": len(self.filtered_games),
        }

    def cleanup(self):
        """Clean up GameManager resources"""
        logger.info("Cleaning up GameManager")

        # Stop any running manifest check task
        if self.manifest_check_task is not None:
            logger.debug("Stopping manifest check task during cleanup")
            self.manifest_check_task.stop()
            self.manifest_check_task = None

        self.games.clear()
        self.filtered_games.clear()
        self.selected_game = None
        self._games_to_check = []

    def get_uninstall_confirmation_message(self, game_data):
        """
        Build a confirmation message for uninstalling a game.
        Returns a string with the confirmation message.
        """
        game_name = game_data.get("game_name", "Unknown")
        install_path = game_data.get("install_path")
        library_path = game_data.get("library_path")
        appid = game_data.get("appid", "0")

        import os
        import platform

        from core.steam_helpers import find_steam_install, get_steam_libraries

        confirm_msg = f"Are you sure you want to uninstall '{game_name}'?\n\n"

        # Warn if appid is unknown
        if not appid or appid in ("0", "N/A", "unknown"):
            confirm_msg += "⚠️ WARNING: AppID is unknown for this game.\n"
            if platform.system() == "Linux":
                confirm_msg += "Compatdata and saves WILL NOT be removed.\n"
            elif platform.system() == "Windows":
                confirm_msg += "GreenLuma AppList files WILL NOT be removed.\n"
            confirm_msg += "\n"

        confirm_msg += "This will permanently delete:\n"
        confirm_msg += f"• Game folder: {install_path}\n"

        # Only show ACF removal if appid is valid
        if appid and appid not in ("0", "N/A", "unknown"):
            confirm_msg += f"• Steam app manifest ({appid}.acf)\n"

        # Check for additional items that would be removed
        if (
            platform.system() == "Linux"
            and appid
            and appid not in ("0", "N/A", "unknown")
        ):
            steam_libraries = get_steam_libraries()
            if steam_libraries:
                steam_dir = steam_libraries[0]
                compatdata_path = os.path.join(
                    steam_dir, "steamapps", "compatdata", appid
                )
                userdata_path = os.path.join(steam_dir, "userdata")

                # Check if compatdata exists
                if os.path.exists(compatdata_path):
                    confirm_msg += (
                        f"• Proton/Wine compatibility data: {compatdata_path}\n"
                    )

                # Check if userdata exists
                if os.path.exists(userdata_path):
                    has_saves = False
                    try:
                        for user_dir in os.listdir(userdata_path):
                            user_path = os.path.join(userdata_path, user_dir)
                            if os.path.isdir(user_path):
                                saves_path = os.path.join(user_path, appid, "remote")
                                if os.path.exists(saves_path):
                                    has_saves = True
                                    break
                    except OSError:
                        pass

                    if has_saves:
                        confirm_msg += "• Steam Cloud saves from userdata folders\n"
        elif (
            platform.system() == "Windows"
            and appid
            and appid not in ("0", "N/A", "unknown")
        ):
            # Check for GreenLuma AppList files
            steam_path = find_steam_install()
            if steam_path:
                app_list_dir = os.path.join(steam_path, "AppList")
                if os.path.exists(app_list_dir):
                    try:
                        found_appid_files = []
                        for filename in os.listdir(app_list_dir):
                            if filename.lower().endswith(".txt"):
                                filepath = os.path.join(app_list_dir, filename)
                                try:
                                    with open(filepath, "r", encoding="utf-8") as f:
                                        content = f.read().strip()
                                        if content == str(appid):
                                            found_appid_files.append(filename)
                                except Exception:
                                    pass
                        if found_appid_files:
                            confirm_msg += f"• GreenLuma AppList file(s): {', '.join(found_appid_files)}\n"
                    except Exception:
                        pass

        confirm_msg += "\nThis action cannot be undone!"
        return confirm_msg

    def uninstall_game(self, game_data, remove_compatdata=False, remove_saves=False):
        """
        Uninstall a game by removing its folder, ACF file, and optionally compatdata/saves.
        Returns (success: bool, error_message: str)
        """
        game_name = game_data.get("game_name", "Unknown")
        install_path = game_data.get("install_path")
        library_path = game_data.get("library_path")
        appid = game_data.get("appid", "0")

        import os
        import platform

        try:
            # Remove game folder
            if install_path and os.path.exists(install_path):
                import shutil

                shutil.rmtree(install_path)
                logger.info(f"Removed game folder: {install_path}")

            # Remove ACF file
            if library_path and appid != "N/A":
                acf_path = os.path.join(
                    library_path, "steamapps", f"appmanifest_{appid}.acf"
                )
                if os.path.exists(acf_path):
                    os.remove(acf_path)
                    logger.info(f"Removed ACF file: {acf_path}")

            # Remove depot file
            if appid and appid not in ("0", "N/A", "unknown"):
                try:
                    depot_file = Path(get_base_path()) / "depots" / f"{appid}.depot"
                    if depot_file.exists():
                        depot_file.unlink()
                        logger.info(f"Removed depot file: {depot_file}")
                except Exception as e:
                    logger.warning(
                        f"Failed to remove depot file for appid {appid}: {e}"
                    )

            # Remove platform-specific data
            if platform.system() == "Linux":
                self._remove_linux_game_data(appid, remove_compatdata, remove_saves)
            elif platform.system() == "Windows":
                self._remove_windows_game_data(appid)

            # Remove from game manager
            self.remove_game(appid)

            return True, None

        except Exception as e:
            error_msg = f"Error uninstalling game {game_name}: {e}"
            logger.error(error_msg)
            return False, str(e)

    def _remove_linux_game_data(self, appid, remove_compatdata, remove_saves):
        """
        Remove Linux-specific game data (compatdata and Steam Cloud saves).
        """
        import os

        from core.steam_helpers import get_steam_libraries

        # CRITICAL SAFETY CHECK: Never remove compatdata/saves for invalid appids
        if not appid or appid in ("0", "N/A", "unknown"):
            logger.warning(
                f"Skipping compatdata/saves removal for invalid appid: {appid}"
            )
            return

        # Validate appid is numeric
        if not str(appid).isdigit():
            logger.error(
                f"Invalid appid format: {appid}. Must be numeric. Skipping compatdata/saves removal."
            )
            return

        steam_libraries = get_steam_libraries()
        if not steam_libraries:
            return

        # Use the first (primary) Steam library
        steam_dir = steam_libraries[0]

        # Remove compatdata
        if remove_compatdata:
            compatdata_path = os.path.join(steam_dir, "steamapps", "compatdata", appid)
            if os.path.exists(compatdata_path):
                try:
                    import shutil

                    shutil.rmtree(compatdata_path)
                    logger.info(f"Removed compatdata: {compatdata_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to remove compatdata {compatdata_path}: {e}"
                    )

        # Remove Steam Cloud saves
        if remove_saves:
            userdata_path = os.path.join(steam_dir, "userdata")
            if os.path.exists(userdata_path):
                try:
                    # Find all user directories
                    for user_dir in os.listdir(userdata_path):
                        user_path = os.path.join(userdata_path, user_dir)
                        if os.path.isdir(user_path):
                            saves_path = os.path.join(user_path, appid, "remote")
                            if os.path.exists(saves_path):
                                import shutil

                                shutil.rmtree(saves_path)
                                logger.info(
                                    f"Removed saves for user {user_dir}: {saves_path}"
                                )
                except Exception as e:
                    logger.warning(f"Failed to remove saves: {e}")

    def _remove_windows_game_data(self, appid):
        """
        Remove Windows-specific game data (GreenLuma AppList files).
        """
        import os
        import shutil

        from core.steam_helpers import find_steam_install

        # CRITICAL SAFETY CHECK: Never remove AppList files for invalid appids
        if not appid or appid in ("0", "N/A", "unknown"):
            logger.warning(
                f"Skipping GreenLuma AppList cleanup for invalid appid: {appid}"
            )
            return

        # Validate appid is numeric
        if not str(appid).isdigit():
            logger.error(
                f"Invalid appid format: {appid}. Must be numeric. Skipping GreenLuma cleanup."
            )
            return

        # Find Steam installation path
        steam_path = find_steam_install()
        if not steam_path:
            logger.warning(
                "Could not find Steam installation path. Skipping GreenLuma AppList cleanup."
            )
            return

        # Locate AppList directory
        app_list_dir = os.path.join(steam_path, "AppList")
        if not os.path.exists(app_list_dir):
            logger.info(
                "AppList directory does not exist. No GreenLuma files to clean up."
            )
            return

        logger.info(f"Scanning GreenLuma AppList directory: {app_list_dir}")

        # Step 1: Find all .txt files that contain this appid
        files_to_delete = []
        all_files_data = []  # List of tuples (filename, filepath, appid_content)

        try:
            for filename in os.listdir(app_list_dir):
                if filename.lower().endswith(".txt"):
                    filepath = os.path.join(app_list_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            # Store all files for later renumbering
                            all_files_data.append((filename, filepath, content))

                            # Check if this file contains our appid
                            if content == str(appid):
                                files_to_delete.append((filename, filepath))
                                logger.info(
                                    f"Found GreenLuma file to delete: {filename} (contains AppID {appid})"
                                )
                    except Exception as e:
                        logger.warning(f"Error reading AppList file {filepath}: {e}")
        except Exception as e:
            logger.error(f"Error scanning AppList directory {app_list_dir}: {e}")
            return

        # Step 2: Delete files containing this appid
        for filename, filepath in files_to_delete:
            try:
                os.remove(filepath)
                logger.info(f"Deleted GreenLuma file: {filepath}")
            except Exception as e:
                logger.warning(f"Failed to delete GreenLuma file {filepath}: {e}")

        # Step 3: Renumber remaining files to maintain sequential numbering
        # Build list of remaining files (those that don't contain our appid)
        remaining_files = [
            (filename, filepath, content)
            for filename, filepath, content in all_files_data
            if filepath not in [f[1] for f in files_to_delete]
        ]

        # Sort remaining files by their current number
        remaining_files.sort(
            key=lambda x: int(re.match(r"^(\d+)\.txt$", x[0]).group(1))
        )

        # Renumber all remaining files sequentially starting from 0
        for index, (old_filename, old_filepath, content) in enumerate(remaining_files):
            new_filename = f"{index}.txt"
            new_filepath = os.path.join(app_list_dir, new_filename)

            # Only rename if the filename will change
            if old_filename != new_filename:
                try:
                    os.rename(old_filepath, new_filepath)
                    logger.debug(
                        f"Renamed GreenLuma file: {old_filename} -> {new_filename}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to rename {old_filename} to {new_filename}: {e}"
                    )

        logger.info(
            f"GreenLuma AppList cleanup complete. Removed {len(files_to_delete)} file(s)."
        )
