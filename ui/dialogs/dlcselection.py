import logging
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

class DlcSelectionDialog(QDialog):
    def __init__(self, dlcs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select DLC for SLSsteam Wrapper")
        self.dlcs = dlcs
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)

        self.anchor_row = -1

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        for dlc_id, dlc_desc in self.dlcs.items():
            item_text = f"{dlc_id} - {dlc_desc}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, dlc_id)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        self.list_widget.itemClicked.connect(self.on_dlc_item_clicked)

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

    def on_dlc_item_clicked(self, item):
        modifiers = QApplication.keyboardModifiers()
        current_row = self.list_widget.row(item)

        click_pos_x = self.list_widget.mapFromGlobal(QCursor.pos()).x()
        item_rect = self.list_widget.visualItemRect(item)

        is_text_click = (click_pos_x - item_rect.x()) > 30

        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if self.anchor_row == -1:
                if is_text_click:
                    current_state = item.checkState()
                    new_state = (
                        Qt.CheckState.Unchecked
                        if current_state == Qt.CheckState.Checked
                        else Qt.CheckState.Checked
                    )
                    item.setCheckState(new_state)
                self.anchor_row = current_row
            else:
                try:
                    anchor_item = self.list_widget.item(self.anchor_row)
                    target_state = anchor_item.checkState()
                except Exception as e:
                    logger.warning(f"Could not find anchor item for shift-click: {e}")
                    target_state = item.checkState()

                start_row = min(self.anchor_row, current_row)
                end_row = max(self.anchor_row, current_row)

                self.list_widget.blockSignals(True)
                for i in range(start_row, end_row + 1):
                    self.list_widget.item(i).setCheckState(target_state)
                self.list_widget.blockSignals(False)

        elif is_text_click:
            current_state = item.checkState()
            new_state = (
                Qt.CheckState.Unchecked
                if current_state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            item.setCheckState(new_state)
            self.anchor_row = current_row
        else:
            self.anchor_row = current_row

    def _toggle_all_checkboxes(self, check=True):
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)
        self.list_widget.blockSignals(False)

        self.anchor_row = -1

    def get_selected_dlcs(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

