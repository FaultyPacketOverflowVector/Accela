from PyQt6.QtCore import QObject, pyqtSignal
import logging
import time
import requests
from functools import wraps
from managers.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

def time_function(func):
    """Decorator to time function execution"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000
        logger.debug(f"{func.__name__} executed in {execution_time:.2f}ms")
        return result
    return wrapper

def sendRequest(url):
    """Fast URL validation using HEAD requests"""
    try:
        response = requests.head(url, timeout=1.5, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        if response.status_code == 200:
            return True
        return False
    except Exception as e:
        logger.debug(f"URL check failed for {url}: {e}")
        return False

class ImageFetcher(QObject):
    finished = pyqtSignal(bytes)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            start_time = time.time()
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(self.url, headers=headers, timeout=3)
            response.raise_for_status()
            data = response.content
            end_time = time.time()
            download_time = (end_time - start_time) * 1000
            logger.debug(f"Downloaded {len(data)} bytes from {self.url} in {download_time:.2f}ms")
            self.finished.emit(data)
        except Exception as e:
            logger.debug(f"Failed to fetch image from {self.url}: {e}")
            self.finished.emit(b"")

    @staticmethod
    @time_function
    def _get_best_image_url(app_id: int, url_list: list) -> str:
        """URL checking with HEAD requests"""
        # ONLY FOR NOW
        return url_list[0]

        logger.debug(f"Starting URL validation for app {app_id} with {len(url_list)} URLs")

        # If there's only one URL, just return it immediately
        if len(url_list) == 1:
            logger.debug(f"Only one URL available, returning: {url_list[0]}")
            return url_list[0]

        start_time = time.time()

        for i, url in enumerate(url_list):
            # If this is the last URL, just return it without checking
            if i == len(url_list) - 1:
                total_time = (time.time() - start_time) * 1000
                logger.debug(f"Last URL, returning without check: {url} (total time: {total_time:.2f}ms)")
                return url

            if sendRequest(url):
                total_time = (time.time() - start_time) * 1000
                logger.info(f"Selected valid image URL: {url} (found in {total_time:.2f}ms)")
                return url

    @staticmethod
    @time_function
    def get_header_image_url(app_id: int) -> str:
        # 1. Try DB for the specific hash URL (FAST)
        try:
            db_url = DatabaseManager().get_header_url(app_id)
            if db_url:
                return db_url
        except Exception:
            pass

        # 2. Fallback to generic URL construction (Does not update DB, just provides a working link)
        urls = [
            f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
            f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_header.jpg",
            f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_hero.jpg",
        ]

        if app_id == "3949040":
            return "https://cdn.akamai.steamstatic.com/steam/apps/3949040/library_hero.jpg"

        logger.debug(f"Header image URLs for app {app_id}: {[url.split('/')[-1] for url in urls]}")
        return ImageFetcher._get_best_image_url(app_id, urls)

    @staticmethod
    @time_function
    def get_capsule_image_url(app_id: int) -> str:
        urls = [
            f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/capsule_184x69.jpg",
            f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_capsule.jpg",
        ]

        if app_id == "3949040":
            return "https://cdn.akamai.steamstatic.com/steam/apps/3949040/library_capsule.jpg"

        logger.debug(f"Capsule image URLs for app {app_id}: {[url.split('/')[-1] for url in urls]}")
        return ImageFetcher._get_best_image_url(app_id, urls)