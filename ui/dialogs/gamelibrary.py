import logging
import os
import platform
import time

from PyQt6.QtCore import QSize, Qt, QThread, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import morrenus_api
from utils.image_fetcher import ImageFetcher

logger = logging.getLogger(__name__)


class GameItemWidget(QWidget):
    """Custom widget for displaying a game item in the library"""

    def __init__(self, game_data, size_str, accent_color):
        super().__init__()
        self.game_data = game_data
        self.accent_color = accent_color

        layout = QVBoxLayout(self)

        # Game name (top)
        name_label = QLabel(game_data.get("game_name", "Unknown"))
        name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(name_label)

        # Size (middle)
        size_label = QLabel(f"Size: {size_str}")
        layout.addWidget(size_label)

        # Update status (bottom, always visible with four states)
        update_status = game_data.get("update_status", "cannot_determine")
        status_label = QLabel()

        if update_status == "update_available":
            status_label.setText("Update Available")
            status_label.setStyleSheet(f"color: {self.accent_color};")
        elif update_status == "up_to_date":
            status_label.setText("Up to Date")
            status_label.setStyleSheet(f"color: {self.accent_color};")
        elif update_status == "checking":
            status_label.setText("Checking for updates...")
            status_label.setStyleSheet(f"color: {self.accent_color};")
        elif update_status == "cannot_determine":
            status_label.setText(
                "Cannot Check Version"
            )
            status_label.setStyleSheet(f"color: {self.accent_color};")

        layout.addWidget(status_label)

    def sizeHint(self):
        """Return size hint that matches the icon height"""
        return QSize(230, 108)


class GameLibraryDialog(QDialog):
    """Dialog to display and manage the game library"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.game_manager = main_window.game_manager
        self.settings = main_window.settings
        self.accent_color = self.settings.value("accent_color", "#C06C84")
        self._active_image_fetchers = {}  # Keep track of active threads to prevent GC

        self.setWindowTitle("Game Library")
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)

        layout = QVBoxLayout(self)

        # Scan button
        self.scan_button = QPushButton("Scan Steam Libraries")
        self.scan_button.clicked.connect(self._scan_for_games)
        layout.addWidget(self.scan_button)

        # Status label
        self.status_label = QLabel("Ready to scan")
        layout.addWidget(self.status_label)

        # Games list
        self.games_list = QListWidget()
        self.games_list.setIconSize(QSize(230, 108))
        self.games_list.setSpacing(5)
        layout.addWidget(self.games_list)

        # Bottom info
        self.info_label = QLabel("Found 0 games installed by ACCELA")
        layout.addWidget(self.info_label)

        self._connect_signals()

        # Game library is now scanned at app startup
        # Just refresh the existing list (which should already be populated)
        self._refresh_game_list()

    def _connect_signals(self):
        """Connect signals"""
        self.game_manager.scan_complete.connect(self._on_scan_complete)
        self.game_manager.library_updated.connect(self._refresh_game_list)
        self.game_manager.game_update_status_changed.connect(self._on_game_update_status_changed)
        self.games_list.itemSelectionChanged.connect(self._on_item_selected)
        self._dialog_open = False  # Track if dialog is already open
        self._refreshing = False  # Track if list is being refreshed
        self._closing = False  # Track if dialog is being closed
        self._scanning = False  # Track if scan is in progress
        self._checking_updates = False  # Track if update checking is in progress

    def _scan_for_games(self):
        """Scan Steam libraries for ACCELA-installed games"""
        # Prevent multiple simultaneous scans
        if self._scanning:
            logger.warning("Scan already in progress, ignoring request")
            return

        self._scanning = True
        self.scan_button.setEnabled(False)
        self.status_label.setText("Scanning Steam libraries...")
        self._refreshing = True  # Set refreshing flag during scan
        self.games_list.clear()

        games_found = self.game_manager.scan_steam_libraries()

        if games_found == 0:
            self.status_label.setText("No ACCELA-installed games found")

        # _refreshing and _scanning will be cleared in _on_scan_complete

    def _on_scan_complete(self, count):
        """Handle scan completion"""
        self.scan_button.setEnabled(True)

        if count > 0:
            self.status_label.setText(f"Scan complete: Found {count} game(s). Checking updates...")
            self._checking_updates = True
            # Start a timer to check if update checking is done
            QTimer.singleShot(100, self._check_if_updates_complete)
        else:
            self.status_label.setText(f"Scan complete: Found {count} game(s)")
            self._scanning = False

        # Note: _refreshing flag is cleared in _refresh_game_list

    def _check_if_updates_complete(self):
        """Check if all games have been checked for updates"""
        if not self._checking_updates:
            return

        # Count how many games still show "checking" or have no appid
        checking_count = 0
        total_games = 0

        for i in range(self.games_list.count()):
            item = self.games_list.item(i)
            if item:
                game_data = item.data(Qt.ItemDataRole.UserRole)
                if game_data:
                    total_games += 1
                    status = game_data.get("update_status")
                    if status == "checking":
                        checking_count += 1

        # If no games show "checking", update checking is complete
        if total_games > 0 and checking_count == 0:
            self.status_label.setText(f"Scan complete: Found {total_games} game(s). All updates checked.")
            self._checking_updates = False
            self._scanning = False
        else:
            # Check again later
            QTimer.singleShot(500, self._check_if_updates_complete)

    def _on_game_update_status_changed(self, appid, update_status):
        """Handle individual game update status change - update just that item"""
        # Find the item with this appid and update it
        for i in range(self.games_list.count()):
            item = self.games_list.item(i)
            if item:
                game_data = item.data(Qt.ItemDataRole.UserRole)
                if game_data and game_data.get("appid") == appid:
                    # Update the game's status
                    game_data["update_status"] = update_status

                    # Recreate the widget with the new status
                    # Instead of clearing and re-adding all items, just update this one
                    size_str = self._format_size(game_data.get("size_on_disk", 0))
                    game_widget = GameItemWidget(game_data, size_str, self.accent_color)

                    # Set the updated widget
                    self.games_list.setItemWidget(item, game_widget)

                    # Keep the data updated
                    item.setData(Qt.ItemDataRole.UserRole, game_data)

                    logger.debug(f"Updated UI for game {appid}: {update_status}")
                    break

    def _format_size(self, size_bytes):
        """Format size in bytes to human-readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math

        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

    def _fetch_item_image(self, item, app_id):
        """Asynchronously fetch header image for a game item"""
        logger.debug(f"Starting image fetch for game {app_id}")
        url = ImageFetcher.get_header_image_url(app_id)

        # Create a simple ImageFetcher instance for this specific URL
        thread = QThread(self)
        fetcher = ImageFetcher(url)
        fetcher.moveToThread(thread)

        # Store references to prevent garbage collection
        self._active_image_fetchers[app_id] = (thread, fetcher)

        # Use a lambda to capture the current item for the callback
        fetcher.finished.connect(
            lambda data, i=item, aid=app_id: self._on_item_image_fetched(data, i, aid)
        )

        fetcher.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        fetcher.finished.connect(fetcher.deleteLater)

        thread.started.connect(fetcher.run)
        thread.start()

    def _on_item_image_fetched(self, image_data, item, app_id):
        """Handle fetched image data"""
        # Don't process if dialog is closing
        if self._closing:
            return

        # Clean up reference immediately
        if app_id in self._active_image_fetchers:
            del self._active_image_fetchers[app_id]

        # If we got valid image data, set it
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            if not pixmap.isNull():
                try:
                    # Resize to smaller dimensions (half size)
                    resized_pixmap = pixmap.scaled(
                        230,
                        108,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    item.setIcon(QIcon(resized_pixmap))
                    logger.debug(f"Successfully set icon for game {app_id}")
                except RuntimeError as e:
                    # Item was deleted, ignore
                    logger.debug(
                        f"Item for game {app_id} was deleted, skipping icon set"
                    )
                except Exception as e:
                    logger.warning(f"Error setting icon for game {app_id}: {e}")
        else:
            logger.debug(f"No image data received for game {app_id}")

    def _refresh_game_list(self):
        """Refresh the games list display"""
        # Don't refresh if dialog is closing
        if self._closing:
            return

        # Set refreshing flag to prevent dialogs from opening during refresh
        self._refreshing = True

        # Request all fetcher threads to quit (don't wait - let them finish in background)
        # They'll clean up via callbacks, and the _closing flag prevents issues
        for app_id in list(self._active_image_fetchers.keys()):
            thread, fetcher = self._active_image_fetchers[app_id]
            thread.quit()
        self._active_image_fetchers.clear()

        # Now clear the list safely
        self.games_list.clear()

        games = self.game_manager.get_all_games()

        # Calculate total size
        total_size = 0

        logger.debug(f"Refreshing game list with {len(games)} games")

        for game in games:
            size_bytes = game.get("size_on_disk", 0)
            total_size += size_bytes

            # Format size for display
            size_str = self._format_size(size_bytes)

            # Create custom widget for game item
            game_widget = GameItemWidget(game, size_str, self.accent_color)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, game)
            item.setSizeHint(QSize(230, 108))
            self.games_list.addItem(item)
            self.games_list.setItemWidget(item, game_widget)

            # Fetch and set header image
            app_id = game.get("appid", "0")
            logger.debug(f"Game: {game.get('game_name', 'Unknown')}, AppID: {app_id}")
            if app_id and app_id != "0":
                self._fetch_item_image(item, app_id)
            else:
                logger.debug("Skipping image fetch for game without valid AppID")

        count = len(games)
        total_size_str = self._format_size(total_size)
        self.info_label.setText(
            f"Found {count} game(s) installed by ACCELA - Total Size: {total_size_str}"
        )

        # Clear refreshing flag after refresh is complete
        self._refreshing = False

    def _on_item_selected(self):
        """Handle game selection with debouncing to prevent multiple dialogs"""
        # If a dialog is already open or list is refreshing, don't open another one
        if self._dialog_open or self._refreshing:
            return

        current_item = self.games_list.currentItem()
        if not current_item:
            return

        game_data = current_item.data(Qt.ItemDataRole.UserRole)
        if not game_data:
            return

        # Use QTimer.singleShot to debounce rapid selection changes
        # and prevent multiple dialogs from opening
        QTimer.singleShot(100, lambda: self._show_game_details_dialog(game_data))
        self._dialog_open = True

        # Reset the flag after a short delay to allow the dialog to open
        QTimer.singleShot(500, lambda: self._set_dialog_open(False))

    def _set_dialog_open(self, state):
        """Set the dialog open state"""
        self._dialog_open = state

    def _show_game_details_dialog(self, game_data):
        """Show game details in a custom dialog with uninstall button"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Game Details")
        dialog.setMinimumWidth(500)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Game name
        name_label = QLabel(f"<h2>{game_data.get('game_name', 'Unknown')}</h2>")
        name_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(name_label)

        # Game details
        details_layout = QFormLayout()

        appid = game_data.get("appid", "N/A")
        size_str = self._format_size(game_data.get("size_on_disk", 0))
        install_path = game_data.get("install_path", "N/A")
        library_path = game_data.get("library_path", "N/A")

        details_layout.addRow("AppID:", QLabel(appid))
        details_layout.addRow("Size:", QLabel(size_str))
        details_layout.addRow(
            "Library:",
            QLabel(os.path.basename(library_path) if library_path != "N/A" else "N/A"),
        )
        details_layout.addRow("Installation Path:", QLabel(install_path))

        layout.addLayout(details_layout)

        # Advanced options (Linux only)
        self.remove_compatdata_checkbox = None
        self.remove_saves_checkbox = None

        if platform.system() == "Linux":
            # Check if appid is valid
            appid_is_valid = appid and appid not in ("0", "N/A", "unknown")

            options_group = QLabel("Additional Removal Options (Linux only)")
            options_group.setStyleSheet(f"""
                QLabel {{
                    font-weight: bold;
                    color: {self.accent_color};
                    margin-top: 10px;
                }}
            """)
            layout.addWidget(options_group)

            self.remove_compatdata_checkbox = QCheckBox(
                "Remove Proton/Wine compatibility data (compatdata)"
            )
            if appid_is_valid:
                self.remove_compatdata_checkbox.setToolTip(
                    "Removes the Proton/Wine prefix which contains game configuration and may contain saves"
                )
            else:
                self.remove_compatdata_checkbox.setEnabled(False)
                self.remove_compatdata_checkbox.setToolTip(
                    "Disabled: AppID is unknown or invalid (cannot determine compatdata location)"
                )
            layout.addWidget(self.remove_compatdata_checkbox)

            self.remove_saves_checkbox = QCheckBox("Remove Steam Cloud saves")
            if appid_is_valid:
                self.remove_saves_checkbox.setToolTip(
                    "Removes saved games stored in Steam's cloud sync folder"
                )
            else:
                self.remove_saves_checkbox.setEnabled(False)
                self.remove_saves_checkbox.setToolTip(
                    "Disabled: AppID is unknown or invalid (cannot determine save location)"
                )
            layout.addWidget(self.remove_saves_checkbox)

        # Buttons
        button_box = QDialogButtonBox()

        # Check if API key is configured
        api_key = self.settings.value("morrenus_api_key", "", type=str)
        if api_key:
            # API key is set, show update button based on status
            update_status = game_data.get("update_status", "cannot_determine")

            if update_status == "update_available":
                # Show "Download Update" button
                fetch_button = button_box.addButton(
                    "Download Update", QDialogButtonBox.ButtonRole.ApplyRole
                )
                fetch_button.clicked.connect(
                    lambda: self._fetch_game_manifest(game_data, dialog)
                )
            elif update_status in ("cannot_determine", "up_to_date"):
                # Show "Validate Files" button
                fetch_button = button_box.addButton(
                    "Validate Files", QDialogButtonBox.ButtonRole.ApplyRole
                )
                fetch_button.clicked.connect(
                    lambda: self._fetch_game_manifest(game_data, dialog)
                )

        uninstall_button = button_box.addButton(
            "Uninstall Game", QDialogButtonBox.ButtonRole.ApplyRole
        )
        uninstall_button.clicked.connect(
            lambda: self._uninstall_game(game_data, dialog)
        )

        close_button = button_box.addButton(
            "Close", QDialogButtonBox.ButtonRole.RejectRole
        )
        close_button.clicked.connect(dialog.accept)

        layout.addWidget(button_box)

        dialog.exec()

    def _fetch_game_manifest(self, game_data, dialog):
        """Fetch manifest from Morrenus API and add to job queue"""
        app_id = game_data.get("appid", "0")

        # Validate AppID
        if not app_id or app_id == "0":
            QMessageBox.warning(
                self,
                "Invalid AppID",
                f"Cannot fetch manifest: AppID is invalid or missing for '{game_data.get('game_name', 'Unknown')}'.",
            )
            return

        game_name = game_data.get("game_name", "Unknown")

        # Confirm fetch operation
        reply = QMessageBox.question(
            self,
            "Confirm Fetch & Reinstall",
            f"This operation will use your Morrenus API quota.\n\n"
            f"This will fetch and validate the latest manifest for '{game_name}' (AppID: {app_id}) from the Morrenus API.\n\n"
            f"The manifest will be downloaded, validated, and added to the download queue to reinstall/update the game.\n\n"
            f"Note: This will not remove your current installation. The game will be verified and any missing/corrupted files will be re-downloaded.\n\n"
            f"Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Show progress dialog
        progress = QProgressDialog(
            f"Fetching manifest for {game_name}...", "Cancel", 0, 0, self
        )
        progress.setWindowTitle("Fetching Manifest")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowFlags(
            progress.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        progress.show()

        try:
            # Call Morrenus API to download manifest
            filepath, error_msg = morrenus_api.download_manifest(app_id)

            if filepath:
                # Success!
                progress.close()

                # Add the manifest to the job queue
                self.main_window.job_queue.add_job(filepath)

                # Close dialogs silently
                dialog.accept()
                self.accept()  # Close the GameLibraryDialog
            else:
                # Error
                progress.close()
                QMessageBox.critical(
                    self,
                    "Fetch Failed",
                    f"Failed to fetch manifest for '{game_name}' (AppID: {app_id}):\n\n{error_msg}",
                )

        except Exception as e:
            # Exception occurred
            progress.close()
            logger.exception(f"Error fetching manifest for AppID {app_id}: {e}")
            QMessageBox.critical(
                self, "Error", f"An error occurred while fetching manifest:\n\n{str(e)}"
            )

    def _uninstall_game(self, game_data, dialog):
        """Uninstall the game by removing folder and ACF file"""
        # Check additional removal options (Linux only)
        remove_compatdata = False
        remove_saves = False

        if platform.system() == "Linux":
            remove_compatdata = (
                self.remove_compatdata_checkbox.isChecked()
                if self.remove_compatdata_checkbox
                else False
            )
            remove_saves = (
                self.remove_saves_checkbox.isChecked()
                if self.remove_saves_checkbox
                else False
            )

        # Get confirmation message from GameManager
        confirm_msg = self.game_manager.get_uninstall_confirmation_message(game_data)

        # Confirm uninstall
        reply = QMessageBox.question(
            self,
            "Confirm Uninstall",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Perform uninstall using GameManager
        success, error_msg = self.game_manager.uninstall_game(
            game_data, remove_compatdata=remove_compatdata, remove_saves=remove_saves
        )

        if success:
            game_name = game_data.get("game_name", "Unknown")
            QMessageBox.information(
                self,
                "Uninstall Complete",
                f"'{game_name}' has been successfully uninstalled.",
            )
            dialog.accept()
            # No need to explicitly refresh - the signal will handle it
        else:
            game_name = game_data.get("game_name", "Unknown")
            QMessageBox.critical(
                self,
                "Uninstall Failed",
                f"Failed to uninstall '{game_name}':\n\n{error_msg}",
            )

    def closeEvent(self, event):
        """Ensure all image fetch threads are cleaned up when dialog closes"""
        # Set closing flag to prevent any callbacks from executing
        self._closing = True

        # Disconnect all signals to prevent accumulation on next open
        try:
            self.game_manager.scan_complete.disconnect(self._on_scan_complete)
            self.game_manager.library_updated.disconnect(self._refresh_game_list)
            self.game_manager.game_update_status_changed.disconnect(self._on_game_update_status_changed)
            self.games_list.itemSelectionChanged.disconnect(self._on_item_selected)
        except TypeError:
            # Signals may already be disconnected, ignore
            pass

        # Stop checking for update completion
        self._checking_updates = False

        # Clean up image fetcher threads properly
        threads = list(self._active_image_fetchers.values())

        # First, request all threads to quit (non-blocking)
        for thread, fetcher in threads:
            thread.quit()

        # Then wait for all threads to finish with a reasonable total timeout
        start_time = time.time()
        max_wait_time = 2.0  # Maximum 2 seconds total for all threads

        for thread, fetcher in threads:
            elapsed = time.time() - start_time
            remaining = max(0, int((max_wait_time - elapsed) * 1000))

            if remaining > 0:
                if not thread.wait(remaining):
                    logger.warning(f"Thread did not finish in time")

            # Don't wait any longer if we've exceeded max time
            if time.time() - start_time >= max_wait_time:
                break

        self._active_image_fetchers.clear()

        super().closeEvent(event)
