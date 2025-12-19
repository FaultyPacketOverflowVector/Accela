import os
import sys
import logging
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from core import steam_helpers

logger = logging.getLogger(__name__)


class JobQueueManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.job_queue = []
        self.jobs_completed_count = 0
        self.slssteam_prompt_pending = False
        self.is_showing_completion_dialog = False

    def add_job(self, file_path):
        """Add a job to the queue"""
        if not os.path.exists(file_path):
            logger.error(f"Failed to add job: file {file_path} does not exist.")
            QMessageBox.critical(
                self.main_window, "Error", f"Could not add job: File not found at {file_path}"
            )
            return

        self.job_queue.append(file_path)
        logger.info(f"Added new job to queue: {os.path.basename(file_path)}")

        self._update_ui_state()

        if not self.main_window.task_manager.is_processing:
            logger.info("Not processing, starting new job from queue.")
            self.main_window.log_output.clear()
            self._start_next_job()
        else:
            logger.info("App is busy, job added to queue.")

    def move_item_up(self):
        """Move selected queue item up"""
        current_row = self.main_window.ui_state.queue_list_widget.currentRow()
        if current_row > 0:
            item = self.job_queue.pop(current_row)
            self.job_queue.insert(current_row - 1, item)
            self._update_queue_display()
            self.main_window.ui_state.queue_list_widget.setCurrentRow(current_row - 1)

    def move_item_down(self):
        """Move selected queue item down"""
        current_row = self.main_window.ui_state.queue_list_widget.currentRow()
        if current_row != -1 and current_row < len(self.job_queue) - 1:
            item = self.job_queue.pop(current_row)
            self.job_queue.insert(current_row + 1, item)
            self._update_queue_display()
            self.main_window.ui_state.queue_list_widget.setCurrentRow(current_row + 1)

    def remove_item(self):
        """Remove selected queue item"""
        current_row = self.main_window.ui_state.queue_list_widget.currentRow()
        if current_row == -1:
            logger.debug("Remove item clicked, but no item is selected.")
            return

        try:
            removed_job = self.job_queue.pop(current_row)
            logger.info(f"Removed job from queue: {os.path.basename(removed_job)}")
            self._update_queue_display()

            if current_row < self.main_window.ui_state.queue_list_widget.count():
                self.main_window.ui_state.queue_list_widget.setCurrentRow(current_row)
            elif self.main_window.ui_state.queue_list_widget.count() > 0:
                self.main_window.ui_state.queue_list_widget.setCurrentRow(current_row - 1)

        except Exception as e:
            logger.error(f"Error removing queue item: {e}", exc_info=True)

    def _start_next_job(self):
        """Start the next job in queue"""
        self._update_ui_state()

        if not self.job_queue:
            self._handle_queue_completion()
            return

        next_job = self.job_queue[0]
        self.main_window.task_manager.start_zip_processing(next_job)
        self.job_queue.pop(0)
        self._update_ui_state()

    def _handle_queue_completion(self):
        """Handle when queue is empty"""
        if self.is_showing_completion_dialog:
            return

        self.is_showing_completion_dialog = True
        try:
            was_pending = self.slssteam_prompt_pending
            self.slssteam_prompt_pending = False

            if was_pending:
                self._prompt_for_steam_restart()
            elif self.jobs_completed_count > 0:
                QMessageBox.information(
                    self.main_window,
                    "Queue Finished",
                    f"All {self.jobs_completed_count} job(s) have finished successfully!",
                )

            self.jobs_completed_count = 0
        finally:
            self.is_showing_completion_dialog = False

    def _update_ui_state(self):
        """Update UI based on queue state"""
        has_jobs = len(self.job_queue) > 0
        is_processing = self.main_window.task_manager.is_processing

        self.main_window.ui_state.update_queue_visibility(is_processing, has_jobs)
        self._update_queue_display()

    def _update_queue_display(self):
        """Update the queue list widget"""
        self.main_window.ui_state.queue_list_widget.clear()
        self.main_window.ui_state.queue_list_widget.addItems(
            [os.path.basename(job) for job in self.job_queue]
        )

    def _check_if_safe_to_start_next_job(self):
        """Check if it's safe to start the next job"""
        if (not self.main_window.task_manager.is_processing and
            not self.main_window.task_manager.is_awaiting_zip_task_stop and
            not self.main_window.task_manager.is_awaiting_speed_monitor_stop and
            not self.main_window.task_manager.achievement_task_runner):  # Also wait for achievement cleanup

            logger.debug("All thread cleanup flags are clear. Safe to start next job.")
            self._start_next_job()
        else:
            logger.debug(
                f"Not starting next job yet. State: "
                f"is_processing={self.main_window.task_manager.is_processing}, "
                f"awaiting_zip={self.main_window.task_manager.is_awaiting_zip_task_stop}, "
                f"awaiting_speed={self.main_window.task_manager.is_awaiting_speed_monitor_stop}, "
                f"achievement_runner={self.main_window.task_manager.achievement_task_runner is not None}"
            )

    def _prompt_for_steam_restart(self):
        """Prompt user to restart Steam with complete restart logic"""
        reply = QMessageBox.question(
            self.main_window,
            "SLSsteam Integration",
            "SLSsteam files have been created. Would you like to restart Steam now to apply the changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("User agreed to restart Steam.")

            if sys.platform == "linux":
                if not steam_helpers.kill_steam_process():
                    logger.info(
                        "Steam process not found, attempting to launch directly."
                    )

                # Check common SLSsteam.so locations first
                common_paths = [
                    "/usr/lib32/libSLSsteam.so",  # System-wide installation
                    os.path.expanduser("~/.local/share/SLSsteam/SLSsteam.so"),  # User installation
                ]

                found_path = None
                for path in common_paths:
                    if os.path.exists(path):
                        found_path = path
                        logger.info(f"Found SLSsteam.so at: {path}")
                        break

                if found_path:
                    # Use the found path to start Steam
                    if steam_helpers.start_steam_with_path(found_path):
                        logger.info(f"Started Steam with SLSsteam.so from: {found_path}")
                    else:
                        logger.warning(f"Failed to start Steam with SLSsteam.so from: {found_path}")
                        QMessageBox.warning(
                            self.main_window,
                            "Execution Failed",
                            f"Could not start Steam with SLSsteam.so from {found_path}",
                        )
                else:
                    # No SLSsteam.so found in common locations, prompt user
                    logger.warning(
                        "SLSsteam.so not found in common locations. Please locate it manually."
                    )
                    filePath, _ = QFileDialog.getOpenFileName(
                        self.main_window,
                        "Select SLSsteam.so",
                        os.path.expanduser("~"),
                        "SLSsteam.so (SLSsteam.so libSLSsteam.so)",
                    )
                    if filePath:
                        if not steam_helpers.start_steam_with_path(filePath):
                            QMessageBox.warning(
                                self.main_window,
                                "Execution Failed",
                                "Could not start Steam with the selected file.",
                            )
                        else:
                            logger.info(f"Started Steam with SLSsteam.so from: {filePath}")
                    else:
                        logger.info("User cancelled file selection.")

            else:
                # Windows platform
                steam_path = steam_helpers.find_steam_install()
                if steam_path:
                    logger.info("Closing Steam...")
                    if not steam_helpers.kill_steam_process():
                        logger.info(
                            "Steam process was not running or could not be killed."
                        )

                    logger.info(
                        "Windows Wrapper Mode: Attempting to launch DLLInjector.exe..."
                    )
                    if not steam_helpers.run_dll_injector(steam_path):
                        QMessageBox.warning(
                            self.main_window,
                            "Injector Failed",
                            f"Could not launch DLLInjector.exe from {steam_path}. Make sure it exists.",
                        )
                else:
                    QMessageBox.warning(
                        self.main_window,
                        "Error",
                        "Could not find Steam installation path. Cannot run DLLInjector.exe.",
                    )

    def clear(self):
        """Clear the job queue"""
        self.job_queue.clear()
