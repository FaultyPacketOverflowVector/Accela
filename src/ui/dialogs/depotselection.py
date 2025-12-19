import logging
import os
import platform
import re
import sys
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from utils.image_fetcher import ImageFetcher

logger = logging.getLogger(__name__)

class DepotSelectionDialog(QDialog):
    def __init__(self, app_id, game_name, depots, header_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Depots to Download")
        self.depots = depots
        self.game_name = game_name
        self.header_url = header_url
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)

        self.anchor_row = -1

        self.header_label = QLabel("Loading header image...")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setMinimumHeight(150)
        layout.addWidget(self.header_label)
        self._fetch_header_image(app_id)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        def get_sort_key(depot_item):
            _depot_id, depot_data = depot_item

            os_val = depot_data.get("oslist")
            if os_val is None:
                os_str = "zzzz"
            else:
                os_str = os_val.lower()

            os_priority = 4

            if os_str == "windows":
                os_priority = 1
            elif os_str == "linux":
                os_priority = 2
            elif "all" in os_str:
                os_priority = 3
            elif os_str == "macosx" or os_str == "macos":
                os_priority = 5

            desc_str = depot_data.get("desc", "").lower()
            lang_val = depot_data.get("language")

            lang_priority = 3
            lang_sort_key = lang_val.lower() if lang_val else "zzzz"

            is_no_language = (
                lang_val is None
                and "english" not in desc_str
                and "japanese" not in desc_str
            )

            if "english" in desc_str:
                lang_priority = 1
                lang_sort_key = lang_val.lower() if lang_val else "english"
            elif is_no_language:
                lang_priority = 1
                lang_sort_key = "english"
            elif "japanese" in desc_str:
                lang_priority = 2
                lang_sort_key = "japanese"

            final_key = (os_priority, lang_priority, lang_sort_key)
            logger.debug(
                f"Depot {_depot_id}: OS='{os_val}', Lang='{lang_val}', Desc='{depot_data.get('desc', '')}'"
            )
            logger.debug(
                f"    -> Key: {final_key} (OS_Prio: {os_priority}, Lang_Prio: {lang_priority}, Lang_Key: '{lang_sort_key}')"
            )

            return final_key

        logger.debug("--- Starting Depot Sort ---")
        sorted_depots = sorted(self.depots.items(), key=get_sort_key)
        logger.debug("--- Depot Sort Finished ---")

        is_first_depot = True

        for depot_id, depot_data in sorted_depots:
            original_desc = depot_data["desc"]

            original_desc = re.sub(
                r"\s*-\s*Depot\s*" + re.escape(depot_id),
                "",
                original_desc,
                flags=re.IGNORECASE,
            )

            tags = ""
            base_desc = original_desc.strip()
            tags_match = re.match(r"^((?:\[.*?\]\s*)*)(.*)", original_desc)
            if tags_match:
                tags = tags_match.group(1).strip()
                base_desc = tags_match.group(2).strip()

            is_generic_fallback = bool(
                re.fullmatch(r"Depot \d+", base_desc, re.IGNORECASE)
            )

            if is_first_depot:
                if is_generic_fallback:
                    final_desc = f"{tags} {self.game_name}".strip()
                else:
                    final_desc = original_desc

                is_first_depot = False
            else:
                if is_generic_fallback:
                    final_desc = tags
                else:
                    final_desc = original_desc

            if depot_data.get("size"):
                try:
                    size_gb = int(depot_data["size"]) / (1024**3)
                    final_desc += f" <{size_gb:.2f} GB>"
                except (ValueError, TypeError):
                    pass

            item_text = f"{depot_id} - {final_desc}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, depot_id)
            item.setCheckState(Qt.CheckState.Unchecked)

            # Removes ItemIsUserCheckable flag to disable internal checkbox handling, handled manually in self.on_depot_item_clicked
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.list_widget.addItem(item)

        # Makes list widget update stylesheets for the items
        QApplication.processEvents()

        layout.addWidget(self.list_widget)

        self.list_widget.itemClicked.connect(self.on_depot_item_clicked)

        button_layout = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(
            lambda: self._toggle_all_checkboxes(check=True)
        )
        button_layout.addWidget(select_all_button)

        deselect_all_button = QPushButton("Deselect All")
        deselect_all_button.clicked.connect(
            lambda: self._toggle_all_checkboxes(check=False)
        )
        button_layout.addWidget(deselect_all_button)
        layout.addLayout(button_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_depot_item_clicked(self, item):
        modifiers = QApplication.keyboardModifiers()
        current_row = self.list_widget.row(item)

        current_state = item.checkState()
        new_state = (
            Qt.CheckState.Unchecked
            if current_state == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if self.anchor_row == -1:
                item.setCheckState(new_state)
                self.anchor_row = current_row
            else:
                try:
                    anchor_item = self.list_widget.item(self.anchor_row)
                    target_state = anchor_item.checkState()
                except Exception as e:
                    logger.warning(f"Could not find anchor item for shift-click: {e}")
                    target_state = new_state

                start_row = min(self.anchor_row, current_row)
                end_row = max(self.anchor_row, current_row)

                self.list_widget.blockSignals(True)
                for i in range(start_row, end_row + 1):
                    self.list_widget.item(i).setCheckState(target_state)
                self.list_widget.blockSignals(False)

        else:
            item.setCheckState(new_state)
            self.anchor_row = current_row

    def _toggle_all_checkboxes(self, check=True):
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)
        self.list_widget.blockSignals(False)

        self.anchor_row = -1

    def _fetch_header_image(self, app_id):
        url = ImageFetcher.get_header_image_url(app_id)

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
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            self.header_label.setPixmap(
                pixmap.scaledToWidth(460, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.header_label.setText("Header image not available.")

    def get_selected_depots(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def closeEvent(self, event):
        """Ensure image fetch thread is cleaned up when dialog closes"""
        if hasattr(self, 'thread') and self.thread is not None:
            try:
                # Check if thread is still valid and running
                if not self.thread.isFinished():
                    self.thread.quit()
                    self.thread.wait()
            except RuntimeError:
                # Thread has already been deleted by Qt
                pass
        super().closeEvent(event)

