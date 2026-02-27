import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager
from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.ingestion.downloader")

# --- Configuration ---
# DOWNLOAD_DIR is now resolved dynamically via StorageManager
HEADLESS = True
NAVIGATION_TIMEOUT = 60000
DOWNLOAD_TIMEOUT = 120000


# --- Browser Management ---
class BrowserManager:
    def __enter__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
        )
        self.context.set_default_timeout(NAVIGATION_TIMEOUT)
        self.page = self.context.new_page()
        return self.page


def _extract_date(page) -> Optional[str]:
    # F6-12: Date extraction not yet implemented. Returns None until HLTV date
    # parsing is added (parse page.locator(".date") or similar HLTV selector).
    # Downstream consumers must handle None gracefully.
    return None


# --- Extractor ---
def extract_match_metadata(page):
    page.wait_for_selector(".team1 .teamName", timeout=30000)
    team1 = page.locator(".team1 .teamName").inner_text().strip()
    team2 = page.locator(".team2 .teamName").inner_text().strip()
    event = page.locator(".event a").inner_text().strip()
    date_val = _extract_date(page)
    return {"teams": {"team1": team1, "team2": team2}, "event": event, "date": date_val}


def extract_maps_and_demos(page):
    page.wait_for_selector("a[href*='/download/demo']", timeout=30000)
    demo_links = page.eval_on_selector_all(
        "a[href*='/download/demo']", "els => els.map(e => e.href)"
    )
    map_names = page.eval_on_selector_all(
        ".mapholder .mapname", "els => els.map(e => e.innerText.strip())"
    )
    maps = []
    for i, demo in enumerate(demo_links):
        m_name = map_names[i] if i < len(map_names) else f"Map_{i+1}"
        maps.append({"map": m_name, "demo_url": demo})
    return maps


# --- Downloader ---
def download_demo(page, demo_url, filename):
    storage = StorageManager()
    download_dir = storage.get_ingest_dir(is_pro=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    return _execute_demo_download(page, demo_url, download_dir, filename)


def _execute_demo_download(page, url, directory, name):
    with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as download_info:
        page.goto(url)
    download = download_info.value
    target = os.path.join(directory, name)
    download.save_as(target)
    return target


def download_single_match(match_url, match_id):
    with BrowserManager() as page:
        page.goto(match_url, wait_until="domcontentloaded")
        meta = extract_match_metadata(page)
        maps = extract_maps_and_demos(page)
        return _process_match_maps(page, match_id, meta, maps)


def _process_match_maps(page, match_id, meta, maps):
    storage = StorageManager()
    download_dir = storage.get_ingest_dir(is_pro=True)
    for i, m in enumerate(maps, start=1):
        m["demo_file"] = download_demo(page, m["demo_url"], f"{match_id}_map{i}.dem")
    result = {"match_id": match_id, **meta, "maps": maps}
    _save_match_json(download_dir, match_id, result)
    return result


def _save_match_json(directory, match_id, data):
    with open(directory / f"{match_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Example usage
if __name__ == "__main__":
    app_logger.info("Starting HLTV Downloader test...")
    example_match_url = "https://www.hltv.org/matches/2368940/mouz-vs-g2-iem-cologne-2023-play-in"
    example_match_id = "iem_cologne_2023_mouz_g2"

    try:
        download_result = download_single_match(example_match_url, example_match_id)
        app_logger.info("Download successful: %s", download_result["match_id"])
    except Exception as e:
        app_logger.error("Download failed: %s", e)
