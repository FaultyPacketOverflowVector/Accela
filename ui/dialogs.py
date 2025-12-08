import logging
import urllib.request
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QListWidget, 
    QListWidgetItem, QPushButton, QInputDialog, QMessageBox, QLabel
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap
from utils.settings import get_settings

logger = logging.getLogger(__name__)

class ImageFetcher(QObject):
    finished = pyqtSignal(bytes)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            with urllib.request.urlopen(self.url) as response:
                data = response.read()
                self.finished.emit(data)
        except Exception as e:
            logger.warning(f"Failed to fetch header image from {self.url}: {e}")
            self.finished.emit(b'')

class SettingsDialog(QDialog):
    """
    A dialog for configuring application settings, like SLSsteam mode.
    Settings are persisted using QSettings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = get_settings()
        self.layout = QVBoxLayout(self)
        
        logger.debug("Opening SettingsDialog.")

        self.sls_mode_checkbox = QCheckBox("SLSsteam Wrapper Mode")
        is_sls_mode = self.settings.value("slssteam_mode", False, type=bool)
        self.sls_mode_checkbox.setChecked(is_sls_mode)
        self.sls_mode_checkbox.setToolTip("Enables special file handling for SLSsteam compatibility.")
        self.layout.addWidget(self.sls_mode_checkbox)
        logger.debug(f"Initial SLSsteam mode setting is: {is_sls_mode}")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def accept(self):
        is_sls_mode = self.sls_mode_checkbox.isChecked()
        self.settings.setValue("slssteam_mode", is_sls_mode)
        logger.info(f"SLSsteam mode setting changed to: {is_sls_mode}")
        super().accept()

class DepotSelectionDialog(QDialog):
    """
    A dialog that allows the user to select which depots to download from a list.
    """
    def __init__(self, app_id, depots, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Depots to Download")
        self.depots = depots
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)

        self.header_label = QLabel("Loading header image...")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setMinimumHeight(150)
        layout.addWidget(self.header_label)
        self._fetch_header_image(app_id)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        for depot_id, depot_data in self.depots.items():
            item_text = f"{depot_id} - {depot_data['desc']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, depot_id)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fetch_header_image(self, app_id):
        """Fetches the game's header image from Steam's CDN in a background thread."""
        url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
        
        self.thread = QThread()
        self.fetcher = ImageFetcher(url)
        self.fetcher.moveToThread(self.thread)
        
        self.thread.started.connect(self.fetcher.run)
        self.fetcher.finished.connect(self.on_image_fetched)
        
        self.fetcher.finished.connect(self.thread.quit)
        self.fetcher.finished.connect(self.fetcher.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def on_image_fetched(self, image_data):
        """Slot to handle the fetched image data."""
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            self.header_label.setPixmap(pixmap.scaledToWidth(460, Qt.TransformationMode.SmoothTransformation))
        else:
            self.header_label.setText("Header image not available.")

    def get_selected_depots(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

class DlcSelectionDialog(QDialog):
    """
    A dialog that allows the user to select which DLC AppIDs to add for the
    SLSsteam wrapper.
    """
    def __init__(self, dlcs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select DLC for SLSsteam Wrapper")
        self.dlcs = dlcs
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        
        for dlc_id, dlc_desc in self.dlcs.items():
            item_text = f"{dlc_id} - {dlc_desc}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, dlc_id)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_dlcs(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

class SteamLibraryDialog(QDialog):
    """
    A dialog to let the user choose from a list of found Steam library folders.
    """
    def __init__(self, library_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Steam Library")
        self.selected_path = None
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        logger.debug(f"Opening SteamLibraryDialog with {len(library_paths)} libraries.")

        self.list_widget = QListWidget()
        for path in library_paths:
            self.list_widget.addItem(QListWidgetItem(path))
        layout.addWidget(self.list_widget)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            self.selected_path = current_item.text()
            logger.info(f"User selected Steam library: {self.selected_path}")
            super().accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a library folder.")

    def get_selected_path(self):
        return self.selected_path
