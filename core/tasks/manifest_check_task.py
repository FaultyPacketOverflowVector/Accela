import logging
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from utils.helpers import get_base_path

logger = logging.getLogger(__name__)

try:
    from core.steam_api import batched_get_product_info
except ImportError:
    # For testing purposes
    batched_get_product_info = None



class ManifestCheckTask(QObject):
    """
    Asynchronous task to check game updates by comparing .depot files
    with current Steam API manifest data without updating the database.
    """

    # Signals
    game_update_checked = pyqtSignal(str, str)  # (appid, update_status)
    progress = pyqtSignal(int, int)  # (current, total)
    batch_progress = pyqtSignal(int, int)  # (current_batch, total_batches)
    completed = pyqtSignal()
    error = pyqtSignal(tuple)  # (Exception, message, traceback)

    def __init__(self, games_list):
        """
        Args:
            games_list: List of game dictionaries to check
        """
        super().__init__()
        self.games_list = games_list
        self._is_running = False

    def run(self):
        """Run the update checks asynchronously using batched API calls"""
        logger.info(f"Starting async update check for {len(self.games_list)} games")
        self._is_running = True

        try:
            total_games = len(self.games_list)
            checked_games = 0

            # Collect all valid appids
            valid_games = []
            for game in self.games_list:
                # Check if task was stopped
                if not self._is_running:
                    logger.debug("Update check task was stopped, exiting")
                    return

                appid = game.get("appid")

                # Skip invalid appids
                if not appid or appid in ("0", "N/A", "unknown"):
                    logger.debug(f"Skipping update check for invalid appid: {appid}")
                    checked_games += 1
                    self.progress.emit(checked_games, total_games)
                    continue

                valid_games.append(game)

            if not valid_games:
                logger.warning("No valid games to check")
                return

            logger.info(f"Valid games to check: {len(valid_games)}")

            # Use batched API call for all valid games
            appid_list = [game["appid"] for game in valid_games]
            batch_size = 20  # Hardcoded as per requirements
            rate_limit_delay = 0.3  # Hardcoded as per requirements

            # Calculate number of batches for progress reporting
            num_batches = (len(appid_list) + batch_size - 1) // batch_size
            logger.info(f"Will process {len(appid_list)} appids in {num_batches} batches")

            # Fetch all data in batched calls
            batched_results = batched_get_product_info(appid_list, batch_size=batch_size, rate_limit_delay=rate_limit_delay)

            # Process each game with the batched results
            for game in valid_games:
                # Check if task was stopped
                if not self._is_running:
                    break

                appid = game.get("appid")
                game_name = game.get("game_name", "Unknown")

                try:
                    # Use batched results to determine update status
                    update_status = self._check_game_update_with_batched_data(game, batched_results)
                    # Emit signal with results
                    self.game_update_checked.emit(appid, update_status)

                except Exception as e:
                    logger.error(f"Error checking update for game {appid}: {e}")
                    self.error.emit((type(e), str(e), traceback.format_exc()))
                    self.game_update_checked.emit(appid, "cannot_determine")

                checked_games += 1
                self.progress.emit(checked_games, total_games)

            logger.info("Async update check complete")

        finally:
            self.completed.emit()

    def _check_game_update_with_batched_data(self, game_data, batched_results):
        """
        Check if a game has an update available using pre-fetched batched data.

        This method uses the results from a batched API call to determine if a game
        has an update, comparing the saved manifest ID with the current public manifest ID.

        Args:
            game_data: Dictionary containing game information
            batched_results: Dict mapping appid -> product_info from batched_get_product_info()

        Returns:
            str: Status constant ('update_available', 'up_to_date', 'cannot_determine')
        """
        appid = game_data.get("appid")

        # Skip if no valid appid
        if not appid or appid in ("0", "N/A", "unknown"):
            return "cannot_determine"

        # Read saved manifest ID from depot file
        depots_dir = Path(get_base_path()) / "depots"
        depot_file = depots_dir / f"{appid}.depot"

        if not depot_file.exists():
            # No saved manifest file, cannot determine version
            logger.debug(f"Depot file not found for app {appid}: {depot_file}")
            return "cannot_determine"

        # Read the saved manifest ID
        try:
            with open(depot_file, "r") as f:
                content = f.read().strip()
                if ":" not in content:
                    logger.warning(f"Invalid depot file format for {appid}")
                    return "cannot_determine"

                saved_main_depot_id, saved_manifest_id = content.split(":", 1)
                saved_main_depot_id = saved_main_depot_id.strip()
                saved_manifest_id = saved_manifest_id.strip()
        except Exception as e:
            logger.error(f"Error reading depot file {depot_file}: {e}")
            return "cannot_determine"

        # Get current manifest from batched results
        try:
            # Look for the appid in batched results
            if appid not in batched_results:
                logger.debug(f"App {appid} not found in batched results")
                return "cannot_determine"

            steam_client_data = batched_results[appid]

            # Look for the manifest ID in the response
            if steam_client_data and steam_client_data.get("depots"):
                depots = steam_client_data.get("depots", {})

                # Find the matching depot
                if saved_main_depot_id in depots:
                    depot_info = depots[saved_main_depot_id]
                    current_manifest_id = depot_info.get("manifest_id")

                    if current_manifest_id:
                        # Compare manifest IDs
                        if saved_manifest_id != current_manifest_id:
                            logger.info(
                                f"Update available for app {appid}: saved={saved_manifest_id}, current={current_manifest_id}"
                            )
                            return "update_available"
                        else:
                            return "up_to_date"
                    else:
                        return "cannot_determine"
                else:
                    return "cannot_determine"
            else:
                return "cannot_determine"

        except Exception as e:
            logger.error(f"Error checking for updates for app {appid}: {e}")
            return "cannot_determine"

    def stop(self):
        """Stop the task"""
        logger.debug("Stopping manifest check task")
        self._is_running = False
