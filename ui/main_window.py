import logging
import os
import random
import sys
import re
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QProgressBar,
    QTextEdit, QFrame, QFileDialog, QMessageBox,
    QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMovie

from ui.custom_title_bar import CustomTitleBar
from ui.dialogs import SettingsDialog, DepotSelectionDialog, SteamLibraryDialog, DlcSelectionDialog
from utils.task_runner import TaskRunner
from core.tasks.process_zip_task import ProcessZipTask
from core.tasks.download_depots_task import DownloadDepotsTask
from core.tasks.monitor_speed_task import SpeedMonitorTask
from core import steam_helpers
from utils.logger import qt_log_handler
from utils.settings import get_settings

logger = logging.getLogger(__name__)

class ScaledLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumSize(1, 1)
        self._movie = None

    def setMovie(self, movie):
        if self._movie:
            self._movie.frameChanged.disconnect(self.on_frame_changed)
        self._movie = movie
        if self._movie:
            self._movie.frameChanged.connect(self.on_frame_changed)

    def on_frame_changed(self, frame_number):
        if self.size().width() > 0 and self.size().height() > 0 and self._movie:
            pixmap = self._movie.currentPixmap()
            scaled_pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        if self._movie:
            self.on_frame_changed(0)
        super().resizeEvent(event)

class ScaledFontLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumSize(1, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        font = self.font()
        new_size = max(8, min(72, int(self.height() * 0.4)))
        font.setPointSize(new_size)
        self.setFont(font)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Depot Downloader GUI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setGeometry(100, 100, 800, 600)
        self.settings = get_settings()
        self.game_data = None
        self.speed_monitor_task = None
        self.main_movie = QMovie("main.gif")
        self.download_gifs = [f"downloading{i}.gif" for i in range(1, 12)]
        self.current_movie = None
        self.depot_dialog = None
        self.current_dest_path = None
        self.slssteam_mode_was_active = False
        self._setup_ui()

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        main_content_frame = QFrame()
        main_content_frame.setStyleSheet("background-color: #000000;")
        self.layout.addWidget(main_content_frame)
        
        main_layout = QVBoxLayout(main_content_frame)
        main_layout.setContentsMargins(0,0,0,0)
        
        drop_zone_container = QWidget()
        drop_zone_layout = QVBoxLayout(drop_zone_container)
        drop_zone_layout.setContentsMargins(0,0,0,0)
        drop_zone_layout.setSpacing(0)

        self.drop_label = ScaledLabel()
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if self.main_movie.isValid():
            self.drop_label.setMovie(self.main_movie)
            self.main_movie.start()
            self.current_movie = self.main_movie
        else:
            self.drop_label.setText("Drag and Drop ZIP File Here")

        drop_zone_layout.addWidget(self.drop_label, 10)

        self.drop_text_label = ScaledFontLabel("Drag and Drop Zip here")
        self.drop_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_text_label.setStyleSheet("background-color: transparent;")
        drop_zone_layout.addWidget(self.drop_text_label, 1)

        main_layout.addWidget(drop_zone_container, 3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { max-height: 10px; border: 1px solid #C06C84; border-radius: 5px; text-align: center; color: #1E1E1E; }
            QProgressBar::chunk { background-color: #C06C84; border-radius: 5px; }
        """)
        main_layout.addWidget(self.progress_bar)

        self.speed_label = QLabel("")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.speed_label.setVisible(False)
        main_layout.addWidget(self.speed_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("background-color: #000000;")
        main_layout.addWidget(self.log_output, 1)
        qt_log_handler.new_record.connect(self.log_output.append)

        self.title_bar = CustomTitleBar(self)
        self.layout.addWidget(self.title_bar)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setSizeGripEnabled(True)
        self.status_bar.setStyleSheet("QStatusBar { border: 0px; background: #000000; }")

        self.setAcceptDrops(True)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            url = event.mimeData().urls()[0]
            if url.isLocalFile() and url.toLocalFile().lower().endswith('.zip'):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        url = event.mimeData().urls()[0]
        zip_path = url.toLocalFile()
        self.log_output.clear()
        self._start_zip_processing(zip_path)

    def _start_zip_processing(self, zip_path):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.drop_text_label.setText("Processing ZIP file...")
        
        self.zip_task = ProcessZipTask()
        runner = TaskRunner()
        worker = runner.run(self.zip_task.run, zip_path)
        worker.finished.connect(self._on_zip_processed)
        worker.error.connect(self._handle_task_error)

    def _on_zip_processed(self, game_data):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.game_data = game_data
        
        if self.game_data and self.game_data.get('depots'):
            self._show_depot_selection_dialog()
        else:
            QMessageBox.warning(self, "No Depots Found", "Zip file processed, but no downloadable depots were found.")
            self._reset_ui_state()

    def _show_depot_selection_dialog(self):
        self.depot_dialog = DepotSelectionDialog(self.game_data['appid'], self.game_data['depots'], self)
        if self.depot_dialog.exec():
            selected_depots = self.depot_dialog.get_selected_depots()
            if not selected_depots:
                self._reset_ui_state()
                return

            dest_path = None
            slssteam_mode = self.settings.value("slssteam_mode", False, type=bool)

            if slssteam_mode:
                if self.game_data.get('dlcs'):
                    dlc_dialog = DlcSelectionDialog(self.game_data['dlcs'], self)
                    if dlc_dialog.exec():
                        self.game_data['selected_dlcs'] = dlc_dialog.get_selected_dlcs()
                
                libraries = steam_helpers.get_steam_libraries()
                if libraries:
                    dialog = SteamLibraryDialog(libraries, self)
                    if dialog.exec():
                        dest_path = dialog.get_selected_path()
                    else:
                        self._reset_ui_state()
                        return
                else:
                    dest_path = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
            else:
                dest_path = QFileDialog.getExistingDirectory(self, "Select Destination Folder")

            if dest_path:
                self._start_download(selected_depots, dest_path, slssteam_mode)
            else:
                self._reset_ui_state()
        else:
            self._reset_ui_state()

    def _start_download(self, selected_depots, dest_path, slssteam_mode):
        self.current_dest_path = dest_path
        self.slssteam_mode_was_active = slssteam_mode

        random_gif_path = random.choice(self.download_gifs)
        download_movie = QMovie(random_gif_path)
        if download_movie.isValid():
            self.current_movie = download_movie
            self.drop_label.setMovie(self.current_movie)
            self.current_movie.start()
        
        self.drop_text_label.setVisible(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.speed_label.setVisible(True)

        self.download_task = DownloadDepotsTask()
        self.download_task.progress.connect(self.log_output.append)
        self.download_task.progress_percentage.connect(self.progress_bar.setValue)

        runner = TaskRunner()
        worker = runner.run(self.download_task.run, self.game_data, selected_depots, dest_path)
        worker.completed.connect(self._on_download_complete)
        worker.error.connect(self._handle_task_error)

        self._start_speed_monitor()

    def _on_download_complete(self):
        self._stop_speed_monitor()
        self.progress_bar.setValue(100)
        
        self._create_acf_file()
        
        if self.slssteam_mode_was_active:
            self._prompt_for_steam_restart()
        else:
            QMessageBox.information(self, "Success", "All files have been downloaded successfully!")
        
        self._reset_ui_state()

    def _create_acf_file(self):
        self.log_output.append("Generating Steam .acf manifest file...")
        
        safe_game_name_fallback = re.sub(r'[^\w\s-]', '', self.game_data.get('game_name', '')).strip().replace(' ', '_')
        install_folder_name = self.game_data.get('installdir', safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{self.game_data['appid']}"
            
        acf_path = os.path.join(self.current_dest_path, 'steamapps', f"appmanifest_{self.game_data['appid']}.acf")
        
        acf_content = f'''
"AppState"
{{
    "appid"         "{self.game_data['appid']}"
    "name"          "{self.game_data['game_name']}"
    "universe"      "1"
    "installdir"    "{install_folder_name}"
    "StateFlags"    "4"
}}
'''

        try:
            with open(acf_path, 'w', encoding='utf-8') as f:
                f.write(acf_content)
            self.log_output.append(f"Created .acf file at {acf_path}")
        except IOError as e:
            self.log_output.append(f"Error creating .acf file: {e}")

    def _handle_task_error(self, error_info):
        _, error_value, _ = error_info
        QMessageBox.critical(self, "Error", f"An error occurred: {error_value}")
        self._reset_ui_state()
        self._stop_speed_monitor()

    def _reset_ui_state(self):
        if self.current_movie:
            self.current_movie.stop()
        if self.main_movie.isValid():
            self.drop_label.setMovie(self.main_movie)
            self.main_movie.start()
            self.current_movie = self.main_movie
        
        self.drop_text_label.setVisible(True)
        self.drop_text_label.setText("Drag and Drop Zip here")
        self.progress_bar.setVisible(False)
        self.speed_label.setVisible(False)
        self.game_data = None
        self.current_dest_path = None
        self.slssteam_mode_was_active = False

    def _start_speed_monitor(self):
        self.speed_monitor_task = SpeedMonitorTask()
        self.speed_monitor_task.speed_update.connect(self.speed_label.setText)
        runner = TaskRunner()
        runner.run(self.speed_monitor_task.run)

    def _stop_speed_monitor(self):
        if self.speed_monitor_task:
            self.speed_monitor_task.stop()
            self.speed_monitor_task = None

    def _prompt_for_steam_restart(self):
        reply = QMessageBox.question(self, 'SLSsteam Integration', 
                                     "SLSsteam files have been created. Would you like to restart Steam now to apply the changes?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("User agreed to restart Steam.")
            
            if sys.platform == 'linux':
                if not steam_helpers.kill_steam_process():
                    self.log_output.append("Steam process not found, attempting to launch directly.")
                
                status = steam_helpers.start_steam()

                if status == 'NEEDS_USER_PATH':
                    self.log_output.append("SLSsteam.so not found. Please locate it manually.")
                    filePath, _ = QFileDialog.getOpenFileName(self, "Select SLSsteam.so", os.path.expanduser("~"), "SLSsteam.so (SLSsteam.so)")
                    if filePath:
                        if not steam_helpers.start_steam_with_path(filePath):
                            QMessageBox.warning(self, "Execution Failed", "Could not start Steam with the selected file.")
                    else:
                        self.log_output.append("User cancelled file selection.")
                
                elif status == 'FAILED':
                    QMessageBox.warning(self, "Steam Not Found", "Could not start Steam automatically. Please start it manually.")

            else:
                steam_helpers.kill_steam_process()
                if not steam_helpers.start_steam() == 'SUCCESS':
                    QMessageBox.warning(self, "Steam Not Found", "Could not restart Steam automatically. Please start it manually.")

    def closeEvent(self, event):
        self._stop_speed_monitor()
        super().closeEvent(event)

