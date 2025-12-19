import logging
import time
import os
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class DownloadMonitorTask(QObject):

    progress_percentage = pyqtSignal(int)
    
    def __init__(self, download_path, total_size, initial_size, interval=1):
        super().__init__()
        self.download_path = download_path
        self.total_size_to_download = total_size
        self.initial_disk_size = initial_size
        self.interval = interval
        self._is_running = True
        logger.debug(f"Monitor Task Init: Path={download_path}, TotalSize={total_size}, InitialSize={initial_size}")

    def run(self):
        logger.info(f"Disk monitor task starting for: {self.download_path}")
        if self.total_size_to_download <= 0:
            logger.warning("Total remaining download size is <= 0. Files may already exist. Reporting 100%.")
            self.progress_percentage.emit(100)
        
        last_emitted_percentage = -1

        while self._is_running:
            time.sleep(self.interval)
            if not self._is_running:
                break
            
            try:
                current_size = self._get_folder_size(self.download_path)
                
                downloaded_bytes = current_size - self.initial_disk_size
                downloaded_bytes = max(0, downloaded_bytes)
                
                percentage = 0
                if self.total_size_to_download > 0:
                    percentage = int((downloaded_bytes / self.total_size_to_download) * 100)
                elif current_size >= self.initial_disk_size:
                    percentage = 100
                
                percentage = max(0, min(100, percentage)) 
                
                if percentage != last_emitted_percentage:
                    self.progress_percentage.emit(percentage)
                    last_emitted_percentage = percentage
                
            except Exception as e:
                logger.warning(f"Error during disk monitor loop: {e}")
                self.stop()

        logger.info("Disk monitor task finished.")

    @staticmethod
    def _get_folder_size(path):
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp) and not os.path.islink(fp):
                        try:
                            total_size += os.path.getsize(fp)
                        except OSError as e:
                            logger.debug(f"Could not get size of file {fp}: {e}")
        except FileNotFoundError:
            logger.debug(f"Download path {path} not created yet. Current size is 0.")
            return 0
        except Exception as e:
            logger.warning(f"Error walking directory {path}: {e}")
        return total_size

    def stop(self):
        self._is_running = False