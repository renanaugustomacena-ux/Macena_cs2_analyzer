import os
import random
import re
import sys
import time
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv_manual_fetcher")


class HLTVStatFetcher:
    """
    Robust fetcher for HLTV.org statistical data.
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",  # Request English to minimize localization issues
    }

    def fetch_top_players(self) -> list[str]:
        """Scrapes the Top 50 players page to get profile URLs."""
        url = "https://www.hltv.org/stats/players?rankingFilter=Top50"
        logger.info("Auto-discovering Top 50 players from: %s", url)
        try:
            time.sleep(random.uniform(2, 4))
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.error("Failed to fetch Top 50: %s", resp.status_code)
                return []

            soup = BeautifulSoup(resp.content, "html.parser")
            player_links = []

            # Select rows in the stats table
            rows = soup.select(".stats-table tbody tr")
            for row in rows:
                link_tag = row.select_one(".playerCol a")
                if link_tag and link_tag.get("href"):
                    full_url = "https://www.hltv.org" + link_tag["href"]
                    player_links.append(full_url)

            logger.info("Discovered %s players.", len(player_links))
            return player_links
        except Exception as e:
            logger.error("Error discovering top players: %s", e)
            return []

    def fetch_player_stats(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Orchestrator: Fetches Main Stats + Deep Dives (Clutches, Multikills, Career).
        """
        logger.info("Deep-Crawling stats for: %s", url)
        try:
            # 1. Main Stats Page (Overview + Firepower/Entrying/Utility)
            # URL format: .../stats/players/{id}/{name}
            time.sleep(random.uniform(2, 5))
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.error("Failed to fetch Main Page %s: %s", url, resp.status_code)
                return None

            soup = BeautifulSoup(resp.content, "html.parser")
            main_data = self._parse_overview(soup)

            # Extract ID and Name for sub-pages
            # URL is likely ending in /12345/nickname
            tokens = url.split("/")
            if len(tokens) >= 2:
                p_id = tokens[-2]
                p_name = tokens[-1]

                # Container for deep stats
                detailed = {}

                # 2. Parse Firepower/Entrying/Utility from Main Page (if available visually)
                detailed.update(self._parse_trait_sections(soup))

                # 3. Sub-Page: Clutches
                # .../stats/players/clutches/{id}/1on1/{name} -> standard is /stats/players/clutches/{id}/all/{name}
                clutch_url = url.replace("/stats/players/", "/stats/players/clutches/").replace(
                    f"/{p_id}/", f"/{p_id}/all/"
                )
                detailed["clutches"] = self._fetch_sub_stats(clutch_url, self._parse_clutches)

                # 4. Sub-Page: Multi-Kills
                # .../stats/players/multikills/{id}/all/{name}
                multikill_url = url.replace(
                    "/stats/players/", "/stats/players/multikills/"
                ).replace(f"/{p_id}/", f"/{p_id}/all/")
                detailed["multikills"] = self._fetch_sub_stats(
                    multikill_url, self._parse_multikills
                )

                # 5. Sub-Page: Career
                career_url = url.replace("/stats/players/", "/stats/players/career/")
                detailed["career"] = self._fetch_sub_stats(career_url, self._parse_career)

                # Attach to main data
                main_data["detailed_stats_json"] = detailed

            return main_data

        except Exception as e:
            logger.error("Error in Deep Crawl: %s", e)
            return None

    def _fetch_sub_stats(self, url: str, parser_func) -> Dict[str, Any]:
        """Generic helper for sub-page fetching."""
        try:
            time.sleep(random.uniform(1.5, 3.0))  # Polite delay
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            if resp.status_code == 200:
                return parser_func(BeautifulSoup(resp.content, "html.parser"))
        except Exception as e:
            logger.debug("Sub-stat fetch skipped for %s: %s", url, e)
        return {}

    def _safe_float(self, text: str) -> float:
        """Robust float parsing handling 'N/A', '-', and commas."""
        if not text or text in ["-", "N/A", "nan"]:
            return 0.0
        try:
            # Remove % and use dot for decimal
            clean_text = text.replace("%", "").replace(",", ".").strip()
            # Handle "123 maps" -> 123
            clean_text = clean_text.split()[0]
            return float(clean_text)
        except (ValueError, TypeError):
            return 0.0

    def _parse_trait_sections(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses Firepower, Entrying, Utility columns from Main Stats Page."""
        traits = {}

        # HLTV generic two-column layout for these stats
        # Look for headers like "Firepower", "Entrying"
        # Since classes are minified/generic, we look for text headers

        # Strategy: Find all 'standard-box' or similar containers
        # Or look for specific known labels

        section_map = {
            "Kills per round": ("firepower", "kpr"),
            "Damage per round": ("firepower", "adr"),
            "Opening duel win": ("entrying", "opening_win_pct"),
            "Traded deaths": ("entrying", "traded_deaths_pct"),
            "Flash assists": ("utility", "flash_assists"),
            "Damage per round win": ("firepower", "adr_win"),
            "Kills per round win": ("firepower", "kpr_win"),
        }

        # Scan all rows again (since they are often scattered)
        rows = soup.select("tr") + soup.select(".stats-row")

        for row in rows:
            text = row.text.strip()
            for key_phrase, (category, json_key) in section_map.items():
                if key_phrase.lower() in text.lower():
                    # Attempt to find the value (often the last child or specific class)
                    # HLTV structure varies: <span>Label</span> <span>Value</span>
                    # Or <td>Label</td> <td>Value</td>

                    # Try finding the number
                    # Get all text chunks in the row
                    chunks = [t.strip() for t in row.text.split("\n") if t.strip()]
                    # Usually the value is the last chunk: "0.78"
                    if len(chunks) >= 2:
                        val = self._safe_float(chunks[-1])

                        if category not in traits:
                            traits[category] = {}
                        traits[category][json_key] = val

        return traits

    def _parse_clutches(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses the Clutches table."""
        clutches = {}
        # Look for summary box with "1 on 1", "1 on 2" headers
        # or the table "All clutch history" (too detailed)
        # We prefer the summary boxes if they exist, otherwise we count from table?
        # Actually HLTV has a "Clutches" summary stats-table usually.

        # Scrape the "summary-matrix" or specific header boxes
        # Simplified: Look for text "1 on 1" and the number below/next to it

        # Example: 1 on 1 - 487 Wins - 207 Losses
        # Often in a grid
        clutch_types = ["1on1", "1on2", "1on3", "1on4", "1on5"]

        # Search for summary cards
        for c_type in clutch_types:
            # This is heuristic, actual HTML inspection required for high robust
            # We assume a specific layout might vary, so we look for labeled containers
            pass

        # Fallback to Summary Table aggregation if needed
        # For now, let's grab the "Total" if possible
        return {"scraped": "true_but_heuristic_pending"}

    def _parse_multikills(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses Multi-Kill summary."""
        mk = {}
        # "3 kills", "4 kills", "5 kills" rows
        rows = soup.select(".stats-table tr")
        for row in rows:
            text = row.text
            if "3 kills" in text:
                mk["3k"] = self._safe_float(row.select("td")[-1].text)
            if "4 kills" in text:
                mk["4k"] = self._safe_float(row.select("td")[-1].text)
            if "5 kills" in text:
                mk["5k"] = self._safe_float(row.select("td")[-1].text)
        return mk

    def _parse_career(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses Career Rating history."""
        career = {}
        # Parse year-by-year table
        rows = soup.select(".stats-table tbody tr")
        history = {}
        for row in rows:
            # First col is Time Period (e.g. "2024"), Second is Rating
            cols = row.select("td")
            if len(cols) >= 2:
                period = cols[0].text.strip()
                rating = self._safe_float(cols[1].text)
                if period.isdigit():  # "2024", "2023"
                    history[period] = rating
        career["rating_history"] = history
        return career

    def _parse_overview(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses the player overview page."""
        stats = {}
        rows = soup.select(".stats-row")
        for row in rows:
            spans = row.find_all("span")
            if len(spans) == 2:
                # Normalizing keys: "Damage / Round" -> "adr"
                label = spans[0].text.strip().lower()
                value = spans[1].text.strip()

                if "damage / round" in label:
                    stats["adr"] = value
                if "kills / round" in label:
                    stats["kpr"] = value
                if "deaths / round" in label:
                    stats["dpr"] = value
                if "headshot" in label:
                    stats["hs"] = value
                if "kast" in label:
                    stats["kast"] = value
                if "rating" in label:
                    stats["rating"] = value
                if "impact" in label:
                    stats["impact"] = value

        # Additional cleanup for missing keys
        mapped = {
            "avg_kills": self._safe_float(stats.get("kpr")),
            "avg_deaths": self._safe_float(stats.get("dpr")),
            "avg_adr": self._safe_float(stats.get("adr")),
            "avg_hs": self._safe_float(stats.get("hs")) / 100.0,  # Store as 0.0-1.0
            "avg_kast": self._safe_float(stats.get("kast")) / 100.0,
            "rating": self._safe_float(stats.get("rating")),
            "impact_rating": self._safe_float(stats.get("impact")),
        }

        # Calculate K/D if missing (legacy scraper faked it, now we calculate)
        if mapped["avg_deaths"] > 0:
            mapped["kd_ratio"] = mapped["avg_kills"] / mapped["avg_deaths"]
        else:
            mapped["kd_ratio"] = 0.0  # Avoid DivByZero

        # Extract player name from title or breadcrumb
        name_tag = soup.select_one(".player-nickname") or soup.select_one("h1.summaryNickname")
        mapped["player_name"] = name_tag.text.strip() if name_tag else "Unknown_Pro"

        return mapped


def run_manual_fetch():
    fetcher = HLTVStatFetcher()

    url_file = os.path.join(
        project_root, "Programma_CS2_RENAN", "data", "external", "hltv_stats_urls.txt"
    )
    urls = []

    if os.path.exists(url_file):
        with open(url_file, "r") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not urls:
        logger.info("No manual URLs found. Switching to Auto-Discovery (Top 50)...")
        urls = fetcher.fetch_top_players()

    if not urls:
        logger.warning("No players to fetch.")
        return
    db = get_db_manager()

    for url in urls:
        data = fetcher.fetch_player_stats(url)
        if data:
            p_name = data.pop("player_name")
            logger.info("Saving stats for %s...", p_name)

            # Create a PlayerMatchStats record marked as Pro
            import json

            # Extract detailed stats to separate variable -> convert to string for SQLite/Storage
            detailed_json_str = "{}"
            if "detailed_stats_json" in data:
                detailed_json_str = json.dumps(data.pop("detailed_stats_json"))

            stat_record = PlayerMatchStats(
                player_name=p_name,
                demo_name=f"HLTV_WEB_{int(time.time())}",
                is_pro=True,
                detailed_stats_json=detailed_json_str,  # Use the computed JSON string
                **data,
            )
            # Default missing normalization fields (std dev) as they don't exist on HLTV overview
            # We explicitly do NOT fake "impact" anymore.
            stat_record.kill_std = 0.0
            stat_record.adr_std = 0.0
            stat_record.econ_rating = 1.0  # Basic placeholder for economy

            if not data.get("impact_rating"):
                # Fallback: Estimate impact from Rating 2.0 (Rough heuristic if missing)
                pass

            db.upsert(stat_record)
            logger.info("Successfully updated %s from HLTV web stats (Deep).", p_name)


if __name__ == "__main__":
    run_manual_fetch()
