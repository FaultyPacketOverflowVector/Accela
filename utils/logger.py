import logging
import os
import platform
import sys
import shutil
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from utils.helpers import get_base_path

class QtLogHandler(QObject, logging.Handler):
    new_record = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        self.setFormatter(formatter)

    def emit(self, record):
        msg = self.format(record)
        self.new_record.emit(msg)


qt_log_handler = QtLogHandler()


def get_log_path(app_name="ACCELA"):
    """
    Return the full path to the log file for the current platform.
    If 'Logs' exists, rename it to 'logs'.
    """
    base_path = get_base_path()
    log_dir = base_path / "logs"
    old_log_dir = base_path / "Logs"

    # Rename Logs → logs (case normalization)
    if old_log_dir.exists() and not log_dir.exists():
        old_log_dir.rename(log_dir)
    elif old_log_dir.exists() and log_dir.exists():
        # Both exist: merge old into new then remove old
        for item in old_log_dir.iterdir():
            target = log_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            else:
                item.rename(target)
        old_log_dir.rmdir()

    # Ensure logs exists
    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir / f"{app_name.lower()}.log"


def _get_linux_log_path(app_name):
    """Get Linux log path following XDG Base Directory specification"""
    xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
        "~/.local/share"
    )
    app_dir = Path(xdg_data_home) / app_name / "logs"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / f"{app_name.lower()}.log"


def _get_windows_log_path(app_name):
    """Get Windows log path following Windows conventions"""
    #appdata_local = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
    #    "~\\AppData\\Local"
    #)
    #app_dir = Path(appdata_local) / app_name / "Logs"
    app_dir = Path(os.path.dirname(os.path.abspath(sys.argv[0]))) / app_name / "Logs"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / f"{app_name.lower()}.log"


def _get_macos_log_path(app_name):
    """Get macOS log path following macOS conventions"""
    home = Path.home()
    app_dir = home / "Library" / "Logs" / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / f"{app_name.lower()}.log"


def _get_fallback_log_path(app_name):
    """Fallback log path for unknown platforms"""
    app_dir = Path.home() / ".logs" / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / f"{app_name.lower()}.log"


def setup_logging():
    """Setup logging with platform-appropriate paths"""

    log_path = get_log_path()
    system = platform.system()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    handlers = []

    # File handler
    try:
        file_handler = logging.FileHandler(
            log_path,
            mode="a",
            encoding="utf-8",
            delay=True,  # Delay file opening until first log
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except (PermissionError, OSError) as e:
        print(f"Warning: Could not create log file at {log_path}: {e}", file=sys.stderr)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # Qt handler
    qt_log_handler.setLevel(logging.INFO)
    qt_log_handler.setFormatter(formatter)
    handlers.append(qt_log_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)

    logger = logging.getLogger(__name__)

    # Log configuration details
    logger.info("Logging configuration:")
    logger.info("  Platform: %s", system)
    logger.info("  Python: %s", sys.version)
    logger.info("  Log file: %s", log_path)
    logger.info("  File level: DEBUG")
    logger.info("  Console level: INFO")
    logger.info("  Qt GUI level: INFO")

    return logger


def get_log_location():
    """Utility function to get the current log file location"""
    return get_log_path()

def get_log_directory():
    """Utility function to get the log directory"""
    return get_log_path().parent

def rotate_logs(max_size_mb=10, backup_count=5):
    """
    Simple log rotation utility that works on all platforms
    """
    log_path = get_log_path()

    if not log_path.exists():
        return

    max_size = max_size_mb * 1024 * 1024  # Convert to bytes

    try:
        if log_path.stat().st_size > max_size:
            # Rotate logs
            for i in range(backup_count - 1, 0, -1):
                old_log = log_path.parent / f"{log_path.stem}.{i}{log_path.suffix}"
                new_log = log_path.parent / f"{log_path.stem}.{i + 1}{log_path.suffix}"
                if old_log.exists():
                    old_log.rename(new_log)

            # Move current log to .1
            backup_log = log_path.parent / f"{log_path.stem}.1{log_path.suffix}"
            log_path.rename(backup_log)

            logger = logging.getLogger(__name__)
            logger.info(
                "Log file rotated (size: %.2f MB)",
                log_path.stat().st_size / (1024 * 1024),
            )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Failed to rotate logs: %s", e)


def cleanup_old_logs(max_age_days=30):
    """
    Clean up log files older than specified days
    """
    log_dir = get_log_directory()
    if not log_dir.exists():
        return

    import time

    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60

    for log_file in log_dir.glob("*.log.*"):
        try:
            if (current_time - log_file.stat().st_mtime) > max_age_seconds:
                log_file.unlink()
                logger = logging.getLogger(__name__)
                logger.debug("Removed old log file: %s", log_file.name)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error("Failed to remove old log file %s: %s", log_file.name, e)


def open_log_directory():
    """Open the log directory in the system file manager"""
    log_dir = get_log_directory()

    try:
        system = platform.system().lower()
        if system == "windows":
            os.startfile(log_dir)
        elif system == "darwin":  # macOS
            os.system(f'open "{log_dir}"')
        else:  # Linux and other Unix-like
            os.system(f'xdg-open "{log_dir}"')
        return True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Failed to open log directory: %s", e)
        return False
