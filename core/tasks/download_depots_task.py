import logging
import subprocess
import sys
import os
import re
from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)

class StreamReader(QObject):
    """Reads output from a stream in a separate thread and emits it."""
    new_line = pyqtSignal(str)

    def __init__(self, stream):
        super().__init__()
        self.stream = stream
        self._is_running = True

    def run(self):
        """Reads lines from the stream until it's closed or stopped."""
        for line in iter(self.stream.readline, ''):
            if not self._is_running:
                break
            self.new_line.emit(line)
        self.stream.close()

    def stop(self):
        """Signals the reader to stop."""
        self._is_running = False

class DownloadDepotsTask(QObject):
    """
    A dedicated class for the download task. This is necessary because the task
    needs to emit progress signals during its long-running execution.
    """
    progress = pyqtSignal(str)
    progress_percentage = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.percentage_regex = re.compile(r"(\d{1,3}\.\d{2})%")
        self.last_percentage = -1

    def run(self, game_data, selected_depots, dest_path):
        """
        TASK: Prepares and executes the DepotDownloaderMod commands to download
        files directly into the final destination directory.
        """
        logger.info(f"Download task starting for {len(selected_depots)} depots.")
        
        commands, skipped_depots = self._prepare_downloads(game_data, selected_depots, dest_path)
        if not commands:
            self.progress.emit("No valid download commands to execute. Task finished.")
            return

        total_depots = len(commands)
        
        for i, command in enumerate(commands):
            depot_id = command[4]
            self.progress.emit(f"--- Starting download for depot {depot_id} ({i+1}/{total_depots}) ---")
            self.last_percentage = -1
            
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                           text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                
                reader_thread = QThread()
                stream_reader = StreamReader(process.stdout)
                stream_reader.moveToThread(reader_thread)

                stream_reader.new_line.connect(self._handle_downloader_output)
                reader_thread.started.connect(stream_reader.run)
                
                reader_thread.start()
                process.wait()
                
                stream_reader.stop()
                reader_thread.quit()
                reader_thread.wait()

                if process.returncode != 0:
                    self.progress.emit(f"Warning: DepotDownloaderMod exited with code {process.returncode} for depot {depot_id}.")

            except FileNotFoundError:
                self.progress.emit("ERROR: ./DepotDownloaderMod not found. Make sure it's in the application's directory.")
                logger.critical("./DepotDownloaderMod not found.")
                raise
            except Exception as e:
                self.progress.emit(f"An unexpected error occurred during download: {e}")
                logger.error(f"Download subprocess failed: {e}", exc_info=True)
                raise
        
        if skipped_depots:
            self.progress.emit(f"Skipped {len(skipped_depots)} depots due to missing manifests: {', '.join(skipped_depots)}")
        
        self.progress.emit("--- Cleaning up temporary files ---")
        for filename in ['keys.vdf', 'manifest']:
            path = os.path.join(os.getcwd(), filename)
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    self.progress.emit(f"Removed '{filename}'.")
                except OSError as e:
                    self.progress.emit(f"Error removing '{filename}': {e}")


    def _handle_downloader_output(self, line):
        """Processes a line of output from the downloader."""
        line = line.strip()
        self.progress.emit(line)
        match = self.percentage_regex.search(line)
        if match:
            percentage = float(match.group(1))
            int_percentage = int(percentage)
            
            if int_percentage != self.last_percentage:
                self.progress_percentage.emit(int_percentage)
                self.last_percentage = int_percentage

    def _prepare_downloads(self, game_data, selected_depots, dest_path):
        """Prepares keys.vdf and command list."""
        keys_path = os.path.join(os.getcwd(), "keys.vdf")
        self.progress.emit(f"Generating depot keys file at {keys_path}")
        with open(keys_path, "w") as f:
            for depot_id in selected_depots:
                if depot_id in game_data['depots']:
                    f.write(f"{depot_id};{game_data['depots'][depot_id]['key']}\n")
        
        safe_game_name_fallback = re.sub(r'[^\w\s-]', '', game_data.get('game_name', '')).strip().replace(' ', '_')
        install_folder_name = game_data.get('installdir', safe_game_name_fallback)
        if not install_folder_name:
            install_folder_name = f"App_{game_data['appid']}"

        download_dir = os.path.join(dest_path, 'steamapps', 'common', install_folder_name)
        os.makedirs(download_dir, exist_ok=True)
        self.progress.emit(f"Download destination set to: {download_dir}")

        commands = []
        skipped_depots = []
        for depot_id in selected_depots:
            manifest_id = game_data['manifests'].get(depot_id)
            if not manifest_id:
                self.progress.emit(f"Warning: No manifest ID for depot {depot_id}. Skipping.")
                skipped_depots.append(str(depot_id))
                continue
            
            commands.append([
                "./DepotDownloaderMod", "-app", game_data['appid'], "-depot", str(depot_id),
                "-manifest", manifest_id,
                "-manifestfile", os.path.join('manifest', f"{depot_id}_{manifest_id}.manifest"),
                "-depotkeys", keys_path, "-max-downloads", "25",
                "-dir", download_dir, "-validate"
            ])

        return commands, skipped_depots

