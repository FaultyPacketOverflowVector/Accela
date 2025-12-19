#!/usr/bin/env python3
"""
Steam AppData Database Builder
Fetches all Steam apps and builds a SQLite database of AppID -> App Details
(Name, Header Path, Install Dir, Depot Info).

- Uses steam.client (persistent clients) in worker threads (one client per worker)
- Single DB writer thread
- Reuses existing DB entries (skips already-fetched appids)
- Graceful CTRL+C handling (clean shutdown)
- Compresses depot JSON data with Zstandard to save space
- Stores the relative header path (e.g. '1004640/hash/header.jpg') in 'header_path'.
"""

from pathlib import Path
import argparse
import logging
import sqlite3
import json
import time
import threading
import queue
import signal
from typing import List, Dict, Set, Optional
import requests

# steam.client import (requires: pip install steam[client] gevent)
try:
    from steam.client import SteamClient
except ImportError:
    # We allow running without steam.client if only Web API is needed, 
    # but the script structure currently relies on it for the worker class structure.
    raise SystemExit("Missing dependency: pip install 'steam[client]' 'gevent'")

# zstandard import (requires: pip install zstandard)
try:
    import zstandard as zstd
except ImportError:
    raise SystemExit("Missing dependency: pip install 'zstandard'")

logger = logging.getLogger("steam_hdr_builder")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(ch)

def init_db(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    # Schema Updated: 
    # - depots_json is BLOB (Zstd compressed)
    # - header_path stores the relative path including appid (e.g. '570/header.jpg' or '1004640/hash/header.jpg')
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS apps (
            appid INTEGER PRIMARY KEY,
            name TEXT,
            header_path TEXT,
            installdir TEXT,
            depots_json BLOB,
            last_updated INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def load_existing_appids(db_path: Path) -> Set[int]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    try:
        cur.execute("SELECT appid FROM apps")
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return set()
    conn.close()
    return {row[0] for row in rows}

class DBWriter(threading.Thread):
    def __init__(self, db_path: Path, result_queue: "queue.Queue[Dict[int, Dict]]", stop_event: threading.Event):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.result_queue = result_queue
        self.stop_event = stop_event
        # Initialize Zstd compressor once
        self.cctx = zstd.ZstdCompressor(level=3) 

    def run(self):
        # Set a long timeout for the DB connection
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        cur = conn.cursor()
        logger.info("DB writer started")
        while not (self.stop_event.is_set() and self.result_queue.empty()):
            try:
                batch = self.result_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._write_batch(cur, batch)
                conn.commit()
            except Exception as e:
                logger.exception("Error writing batch to DB: %s", e)
            finally:
                self.result_queue.task_done()
        conn.close()
        logger.info("DB writer stopped and DB closed")

    def _write_batch(self, cur: sqlite3.Cursor, results: Dict[str, dict]):
        now = int(time.time())
        for appid_str, data in results.items():
            try:
                appid = int(appid_str)
                common = data.get("common", {}) or {}
                config = data.get("config", {}) or {}
                
                # Depot filtering logic
                depots_data = data.get("depots", {})
                filtered_depots = {}
                for depot_id, depot_info in depots_data.items():
                    if not isinstance(depot_info, dict):
                        continue
                    
                    size_str = None
                    if "max_size" in depot_info:
                        size_str = depot_info.get("max_size")
                    else:
                         size_str = depot_info.get("manifests", {}).get("public", {}).get("size")
                    
                    if size_str:
                         depot_config = depot_info.get("config", {})
                         filtered_depots[depot_id] = {
                            "name": depot_info.get("name"),
                            "oslist": depot_config.get("oslist"),
                            "language": depot_config.get("language"),
                            "steamdeck": depot_config.get("steamdeck") == "1",
                            "size": size_str,
                        }

                # Extract buildid logic added here
                branches = depots_data.get("branches")
                if branches and isinstance(branches, dict):
                    public_branch = branches.get("public")
                    if public_branch and isinstance(public_branch, dict):
                        buildid = public_branch.get("buildid")
                        if buildid:
                            # Add to the filtered_depots blob structure
                            filtered_depots["branches"] = {"public": {"buildid": buildid}}
                
                name = common.get("name") or f"App {appid}"
                installdir = config.get("installdir")
                
                # Compress depots
                depots_json_str = json.dumps(filtered_depots, ensure_ascii=False)
                depots_compressed = self.cctx.compress(depots_json_str.encode('utf-8'))
                
                # Optimization: Store relative path (e.g. "1004640/hash/header.jpg")
                header_raw = _extract_header_fragment(common.get("header_image"))
                header_path = _normalize_header_path(appid, header_raw)
                
                cur.execute(
                    """
                    INSERT OR REPLACE INTO apps
                    (appid, name, header_path, installdir, depots_json, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (appid, name, header_path, installdir, depots_compressed, now),
                )
            except Exception:
                logger.exception("Failed to process appid %s", appid_str)

def _extract_header_fragment(header_entry) -> Optional[str]:
    if not header_entry:
        return None
    if isinstance(header_entry, str):
        return header_entry
    if isinstance(header_entry, dict):
        if isinstance(header_entry.get("english"), str):
            return header_entry["english"]
        for value in header_entry.values():
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                inner = _extract_header_fragment(value)
                if inner:
                    return inner
        return None
    return None

def _normalize_header_path(appid: int, fragment: Optional[str]) -> Optional[str]:
    """
    Normalizes the header info to be the relative path from the 'apps' directory.
    
    Input scenarios:
    1. Full URL with hash: 
       "https://.../apps/1004640/2d8e.../header.jpg?t=123"
       -> Returns: "1004640/2d8e.../header.jpg"
       
    2. Simple filename (Steam Client default):
       "header.jpg"
       -> Returns: "12345/header.jpg" (Prepends appid)
    """
    if not fragment or not isinstance(fragment, str):
        return None
    
    fragment = fragment.strip()
    
    # Remove query parameters (like ?t=1762490936) before processing
    if "?" in fragment:
        fragment = fragment.split("?", 1)[0]
    
    # 1. Handle Full URLs -> Strip everything before the appid path
    # URL format: https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/{hash}/header.jpg
    if "http" in fragment and "/apps/" in fragment:
        # Split at "/apps/" and take the second part.
        # This preserves {appid}/{hash}/header.jpg
        return fragment.split("/apps/", 1)[1]
    
    # 2. Handle simple filenames (e.g. from steam.client without Web API fallback)
    # If it doesn't start with the appid, we assume it's a naked filename.
    if not fragment.startswith(f"{appid}/"):
        fragment = fragment.lstrip("/")
        return f"{appid}/{fragment}"
        
    return fragment

def _construct_header_url(header_path: Optional[str]) -> Optional[str]:
    """
    HELPER FUNCTION: Use this logic when READING from the DB.
    Reconstructs full URL by prepending the fixed CDN base.
    """
    if not header_path or not isinstance(header_path, str):
        return None
    
    # If it's already a full URL, return as is
    if header_path.startswith(("http://", "https://")):
        return header_path
        
    # Base: https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/
    # Stored path: {appid}/{optional_hash}/header.jpg
    return f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{header_path}"

class SteamWorker(threading.Thread):
    def __init__(self, worker_id: int, work_queue: "queue.Queue[List[int]]", result_queue: "queue.Queue[Dict[str, dict]]", stop_event: threading.Event, counter_ref: dict, api_key: Optional[str] = None, connect_timeout: int = 30):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.work_queue = work_queue
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.api_key = api_key
        self.connect_timeout = connect_timeout
        self.client: Optional[SteamClient] = None
        self.counter_ref = counter_ref

    def run(self):
        # Try to initialize steam client
        try:
            self.client = SteamClient()
            self.client.anonymous_login()
        except Exception as e:
            logger.warning("[W%d] SteamClient login failed (will use WebAPI fallback): %s", self.worker_id, e)
            self.client = None

        while not self.stop_event.is_set():
            try:
                batch = self.work_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if batch is None:
                self.work_queue.task_done()
                break

            logger.debug("[W%d] fetching batch of %d apps", self.worker_id, len(batch))
            
            successful_apps = {}
            failed_appids = []

            # 1. Try steam.client first
            if self.client and self.client.logged_on:
                try:
                    product_info = self.client.get_product_info(apps=batch, timeout=30) or {}
                    apps_map = product_info.get("apps") or product_info.get("response", {}).get("apps") or {}
                    
                    for appid_str, data in apps_map.items():
                        if data.get("name") != "[no-info]":
                            successful_apps[appid_str] = data
                        else:
                            failed_appids.append(int(appid_str))
                    
                    fetched_ids = set(int(x) for x in successful_apps.keys())
                    for batch_id in batch:
                        if batch_id not in fetched_ids and batch_id not in failed_appids:
                            failed_appids.append(batch_id)

                except Exception as e:
                    logger.warning("[W%d] get_product_info failed: %s", self.worker_id, e)
                    failed_appids = batch
            else:
                failed_appids = batch

            # 2. Process successful apps
            if successful_apps:
                self.result_queue.put(successful_apps)
                with threading.Lock():
                    self.counter_ref["count"] += len(successful_apps)

            # 3. Fallback to Web API
            if failed_appids:
                if self.client: 
                    logger.debug("[W%d] Fallback to Web API for %d apps", self.worker_id, len(failed_appids))
                
                fallback_results = {}
                for appid in failed_appids:
                    if self.stop_event.is_set(): break
                    
                    fallback = _fetch_store_api_details(appid)
                    if fallback:
                        fallback_results[str(appid)] = fallback
                        time.sleep(1.5) 
                    else:
                        time.sleep(0.5)

                if fallback_results:
                    self.result_queue.put(fallback_results)
                    with threading.Lock():
                        self.counter_ref["count"] += len(fallback_results)
            
            self.work_queue.task_done()

        try:
            if self.client:
                self.client.logout()
                self.client.disconnect()
        except Exception:
            pass
        logger.info("[W%d] stopped", self.worker_id)

def _fetch_store_api_details(appid: int) -> Optional[Dict]:
    """
    Fetch detailed info via the Steam Store API.
    """
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": appid}
    try:
        r = requests.get(url, params=params, timeout=10)
        if not r.ok:
            return None
            
        data = r.json()
        wrapper = data.get(str(appid))
        if not wrapper or not wrapper.get("success"):
            return None
            
        app_data = wrapper.get("data", {})
        
        result = {
            "common": {
                "name": app_data.get("name"),
                "header_image": app_data.get("header_image")
            },
            "config": {
                "installdir": app_data.get("install_dir")
            },
            "depots": app_data.get("depots", {})
        }
        return result
    except Exception:
        return None

def get_all_app_ids_via_store_service(api_key: Optional[str]) -> Set[int]:
    """
    Fetch all Steam AppIDs using IStoreService/GetAppList/v1.
    """
    if not api_key:
        logger.warning("No API key provided. IStoreService may fail or return limited results.")
    
    logger.info("Fetching master app list via IStoreService/GetAppList/v1 (Paginated)...")
    
    url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
    app_ids = set()
    last_appid = 0
    more_items = True
    batch_size = 50000 
    
    while more_items:
        params = {
            "include_games": "true",
            "include_dlc": "true",
            "include_software": "true",
            "include_videos": "false",
            "include_hardware": "false",
            "max_results": batch_size,
            "last_appid": last_appid
        }
        if api_key:
            params["key"] = api_key

        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            response_body = data.get("response", {})
            apps = response_body.get("apps", [])
            
            if not apps:
                more_items = False
                break
                
            count = 0
            for app in apps:
                aid = app.get("appid")
                if aid:
                    app_ids.add(int(aid))
                    last_appid = max(last_appid, int(aid))
                    count += 1
            
            logger.info(f"Fetched {count} apps (Last AppID: {last_appid}). Total so far: {len(app_ids)}")
            
            if count < batch_size:
                more_items = False
                
            time.sleep(1)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error("API Key required or invalid for IStoreService.")
                break
            logger.error(f"HTTP Error during app list fetch: {e}")
            break
        except Exception as e:
            logger.exception(f"Error fetching app list: {e}")
            break

    return app_ids

def chunk_list(lst: List[int], size: int) -> List[List[int]]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]

def format_duration(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

class ProgressReporter(threading.Thread):
    def __init__(self, total: int, counter, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.total = total
        self.counter = counter
        self.stop_event = stop_event
        self.start_time = time.time()

    def run(self):
        while not self.stop_event.is_set():
            done = self.counter["count"]
            elapsed = time.time() - self.start_time
            pct = (done / self.total) * 100 if self.total else 0
            rate = done / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: {done:,} / {self.total:,} ({pct:.2f}%) | Rate: {rate:.1f} apps/s | Elapsed: {format_duration(elapsed)}")
            time.sleep(5)

def main(output_dir: Path, workers: int, batch_size: int, api_key: Optional[str] = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "steam_headers.db"

    init_db(db_path)
    existing_appids = load_existing_appids(db_path)
    logger.info("Existing DB entries: %d", len(existing_appids))

    all_appids = get_all_app_ids_via_store_service(api_key)
    
    if not all_appids:
        logger.error("No app ids found. Please check your API Key or internet connection.")
        return

    to_fetch = sorted(list(all_appids - existing_appids))
    counter = {"count": 0}
    logger.info("Total master apps: %d, to fetch: %d", len(all_appids), len(to_fetch))
    
    if not to_fetch:
        logger.info("Nothing to fetch — DB is up-to-date.")
        return

    work_q: "queue.Queue[List[int]]" = queue.Queue()
    result_q: "queue.Queue[Dict[str, dict]]" = queue.Queue()
    stop_event = threading.Event()

    batches = chunk_list(to_fetch, batch_size)
    for b in batches:
        work_q.put(b)
    
    for _ in range(workers):
        work_q.put(None)

    db_writer = DBWriter(db_path=db_path, result_queue=result_q, stop_event=stop_event)
    db_writer.start()

    workers_list: List[SteamWorker] = []
    for i in range(workers):
        w = SteamWorker(worker_id=i + 1, work_queue=work_q, result_queue=result_q, stop_event=stop_event, counter_ref=counter, api_key=api_key)
        w.start()
        workers_list.append(w)

    progress_thread = ProgressReporter(total=len(to_fetch), counter=counter, stop_event=stop_event)
    progress_thread.start()
    
    def _signal_handler(sig, frame):
        logger.warning("Caught signal %s — shutting down gracefully...", sig)
        stop_event.set()
        while not work_q.empty():
            try:
                work_q.get_nowait()
                work_q.task_done()
            except queue.Empty:
                break
        for w in workers_list:
            if w.is_alive():
                work_q.put(None)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        # Wait until all tasks have been processed or stop event set
        while not stop_event.is_set():
            # Poll queue status instead of blocking with join(timeout)
            if work_q.unfinished_tasks == 0 and result_q.unfinished_tasks == 0:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt detected in main loop - initiating shutdown")
        _signal_handler("SIGINT", None)
    finally:
        stop_event.set()
        for w in workers_list:
            if w.is_alive():
                work_q.put(None)
        logger.info("Waiting for workers to finish...")
        for w in workers_list:
            w.join(timeout=10)
        logger.info("Waiting for DB writer to finish...")
        db_writer.join(timeout=10)
        logger.info("Shutdown complete.")
        progress_thread.join(timeout=1)
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast Steam Header DB Builder")
    parser.add_argument("--output-dir", "-o", type=str, default="./data", help="Output directory for DB")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Number of worker threads")
    parser.add_argument("--batch-size", "-b", type=int, default=50, help="Number of apps per batch")
    # Default key from oureveryday
    parser.add_argument("--api-key", type=str, default="1DD0450A99F573693CD031EBB160907D", help="Steam Web API key (REQUIRED for reliable app list generation)")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    main(output_dir=outdir, workers=args.workers, batch_size=args.batch_size, api_key=args.api_key)