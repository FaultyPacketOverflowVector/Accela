import logging
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QApplication,
)

logger = logging.getLogger(__name__)

class SteamLibraryDialog(QDialog):
    def __init__(self, library_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Steam Library")
        self.selected_path = None
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        logger.debug(f"Opening SteamLibraryDialog with {len(library_paths)} libraries.")

        self.list_widget = QListWidget()
        # Sort the library paths alphabetically
        sorted_paths = sorted(library_paths)
        for path in sorted_paths:
            self.list_widget.addItem(QListWidgetItem(path))

        # Makes list widget update stylesheets for the items
        QApplication.processEvents()

        layout.addWidget(self.list_widget)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
