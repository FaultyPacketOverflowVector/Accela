import logging
import re
from PyQt6.QtCore import Qt, QSize, QThread
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from core import morrenus_api
from utils.task_runner import TaskRunner
from utils.image_fetcher import ImageFetcher

logger = logging.getLogger(__name__)

class FetchManifestDialog(QDialog):
    """
    A dialog for searching and downloading manifests from the Morrenus API.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Fetch Manifest from Morrenus API")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.task_runner = TaskRunner()
        self._active_image_fetchers = {}  # Keep track of active fetchers to prevent GC

        layout = QVBoxLayout(self)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for a game and press Enter...")
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        # Set a larger icon size for the header images (Aspect Ratio approx 2.15)
        # Steam Headers are 460x215. Scaled down to half size: 230x108
        self.results_list.setIconSize(QSize(230, 108))  
        self.results_list.setSpacing(5)
        layout.addWidget(self.results_list)

        self.status_label = QLabel("Search for a game to begin.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.search_input.returnPressed.connect(self.on_search)
        self.results_list.itemDoubleClicked.connect(self.on_item_double_clicked)

        logger.debug("FetchManifestDialog initialized.")

    def on_search(self):
        query = self.search_input.text().strip()
        if not query or len(query) < 2:
            self.status_label.setText("Please enter a search query (min 2 chars).")
            return

        logger.info(f"Starting Morrenus API search for: '{query}'")
        self.results_list.clear()
        # Clear any old fetchers
        self._active_image_fetchers.clear()

        self.status_label.setText("Searching...")
        self.search_input.setEnabled(False)
        self.results_list.setEnabled(False)

        worker = self.task_runner.run(morrenus_api.search_games, query)
        worker.finished.connect(self.on_search_finished)
        worker.error.connect(self.on_task_error)

    def on_search_finished(self, results):
        self.search_input.setEnabled(True)
        self.results_list.setEnabled(True)

        if results.get("error"):
            error_msg = results.get("error")
            logger.error(f"API search failed: {error_msg}")
            self.status_label.setText(f"Error: {error_msg}")
            QMessageBox.critical(self, "Search Error", error_msg)
            return

        game_results = results.get("results")
        if game_results:
            logger.info(f"Found {len(game_results)} results.")

            blacklist_keywords = [
                "soundtrack",
                "ost",
                "original soundtrack",
                "artbook",
                "graphic novel",
                "demo",
                "server",
                "dedicated server",
                "tool",
                "sdk",
                "3d print model",
            ]

            filtered_count = 0
            for game in game_results:
                name_lower = game.get("game_name", "").lower()
                is_blacklisted = False
                for keyword in blacklist_keywords:
                    if re.search(rf"\b{re.escape(keyword)}\b", name_lower):
                        is_blacklisted = True
                        break

                if not is_blacklisted:
                    app_id = str(game["game_id"])
                    item_text = f"{game['game_name']} (AppID: {app_id})"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, app_id)
                    self.results_list.addItem(item)

                    # Initiate async image fetch for this item
                    self._fetch_item_image(item, app_id)
                else:
                    filtered_count += 1

            self.status_label.setText(
                f"Found {len(game_results)} results ({filtered_count} filtered). Double-click to download."
            )
        else:
            logger.info("No results found.")
            self.status_label.setText("No results found.")

    def _fetch_item_image(self, item, app_id):
        url = ImageFetcher.get_header_image_url(app_id)
        
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
        # Clean up reference
        if app_id in self._active_image_fetchers:
            del self._active_image_fetchers[app_id]

        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
        # If it failed, it just won't have an icon, which is fine as a fallback.

    def on_item_double_clicked(self, item):
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if not app_id:
            return

        logger.info(f"User selected AppID {app_id} for download.")
        self.status_label.setText(f"Downloading manifest for AppID {app_id}...")
        self.search_input.setEnabled(False)
        self.results_list.setEnabled(False)

        worker = self.task_runner.run(morrenus_api.download_manifest, app_id)
        worker.finished.connect(self.on_download_finished)
        worker.error.connect(self.on_task_error)

    def on_download_finished(self, result):
        temp_zip_path, error_message = result

        if error_message:
            logger.error(f"Manifest download failed: {error_message}")
            QMessageBox.critical(self, "Download Failed", error_message)
            self.search_input.setEnabled(True)
            self.results_list.setEnabled(True)
            self.status_label.setText("Download failed. Ready to search.")
            return

        if temp_zip_path:
            logger.info(f"Manifest downloaded successfully to {temp_zip_path}")
            self.status_label.setText("Download complete! Adding to queue...")
            if self.parent_window:
                self.parent_window.job_queue.add_job(temp_zip_path)
            self.accept()

    def on_task_error(self, error_info):
        _, error_value, _ = error_info
        logger.error(f"A worker task failed: {error_value}", exc_info=error_info)
        QMessageBox.critical(
            self, "Error", f"An unexpected error occurred: {error_value}"
        )
        self.search_input.setEnabled(True)
        self.results_list.setEnabled(True)
        self.status_label.setText("An error occurred. Ready to search.")

    def closeEvent(self, event):
        # Ensure all threads are cleaned up when dialog closes
        for thread, fetcher in self._active_image_fetchers.values():
            try:
                thread.quit()
                thread.wait()
            except RuntimeError:
                # Thread may have already been deleted by Qt
                logger.debug("Image fetcher thread was already deleted, skipping cleanup.")
                pass
        self._active_image_fetchers.clear()

        # Clean up task_runner thread if running
        if self.task_runner and self.task_runner.thread is not None:
            try:
                self.task_runner.thread.quit()
                self.task_runner.thread.wait()
            except RuntimeError:
                # Thread may have already been deleted by Qt
                logger.debug("TaskRunner thread was already deleted, skipping cleanup.")
                pass

        super().closeEvent(event)