import logging
import os
import requests
from pathlib import Path
from utils.settings import get_settings
from utils.helpers import get_base_path

logger = logging.getLogger(__name__)

BASE_URL = "https://manifest.morrenus.xyz/api/v1"


def _get_headers():
    """
    Retrieves the Morrenus API key from settings and constructs auth headers.
    """
    settings = get_settings()
    api_key = settings.value("morrenus_api_key", "", type=str)
    if not api_key:
        logger.warning("Morrenus API key is not set in settings.")
        return None
    return {"Authorization": f"Bearer {api_key}"}


def search_games(query):
    """
    Searches for games on the Morrenus API.
    """
    headers = _get_headers()
    if headers is None:
        return {"error": "API Key is not set. Please set it in Settings."}

    params = {"q": query, "limit": 50}
    url = f"{BASE_URL}/search"
    logger.info(f"Searching Morrenus API: {url} with query: {query}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"API search HTTP error: {e} - {e.response.text}")
        try:
            # Try to parse the error detail from the API response
            error_detail = e.response.json().get("detail", e.response.text)
            return {"error": f"API Error ({e.response.status_code}): {error_detail}"}
        except requests.exceptions.JSONDecodeError:
            return {"error": f"API Error ({e.response.status_code}): {e.response.text}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"API search failed: {e}")
        return {"error": f"Request Failed: {e}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during search: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {e}"}


def download_manifest(app_id):
    """
    Downloads a manifest zip for a given app_id to a persistent folder.
    Returns (filepath, None) on success, or (None, error_message) on failure.
    """
    headers = _get_headers()
    if headers is None:
        return (None, "API Key is not set. Please set it in Settings.")

    url = f"{BASE_URL}/manifest/{app_id}"
    # Save to persistent folder
    manifests_dir = Path(get_base_path()) / "morrenus_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    save_path = manifests_dir / f"accela_fetch_{app_id}.zip"
    logger.info(f"Attempting to download manifest for AppID {app_id} to {save_path}")

    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        logger.info(f"Manifest for {app_id} downloaded successfully to {save_path}")
        return (str(save_path), None)
    except requests.exceptions.HTTPError as e:
        logger.error(f"API download HTTP error: {e} - {e.response.text}")
        if os.path.exists(save_path):
            os.remove(save_path) # Clean up partial file
        try:
            error_detail = e.response.json().get("detail", e.response.text)
            return (None, f"API Error ({e.response.status_code}): {error_detail}")
        except requests.exceptions.JSONDecodeError:
            return (None, f"API Error ({e.response.status_code}): {e.response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"API download failed: {e}")
        if os.path.exists(save_path):
            os.remove(save_path)
        return (None, f"Download Failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during download: {e}", exc_info=True)
        if os.path.exists(save_path):
            os.remove(save_path)
        return (None, f"An unexpected error occurred: {e}")
