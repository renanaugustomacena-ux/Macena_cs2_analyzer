import os
import random
import re
import sys
import time
from typing import Any, Dict, Optional

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.ingestion.hltv.flaresolverr_client import FlareSolverrClient
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv_manual_fetcher")


class HLTVStatFetcher:
    """
    Robust fetcher for HLTV.org statistical data.

    Uses FlareSolverr (Docker) to bypass Cloudflare protection.
    All HTTP requests go through the local FlareSolverr REST API
    which resolves JS challenges automatically.
    """

    def __init__(self):
        if not _HAS_BS4:
            raise ImportError(
                "beautifulsoup4 is required for HLTV stat fetching. "
                "Install it with: pip install beautifulsoup4"
            )
        self._solver = FlareSolverrClient(timeout=60)

    def fetch_top_players(self) -> list[str]:
        """Scrapes the Top 50 players page to get profile URLs."""
        url = "https://www.hltv.org/stats/players?rankingFilter=Top50"
        logger.info("Auto-discovering Top 50 players from: %s", url)
        try:
            time.sleep(random.uniform(2, 4))
            html = self._solver.get(url)
            if not html:
                logger.error("FlareSolverr failed for Top 50 page")
                return []

            soup = BeautifulSoup(html, "html.parser")
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
        except Exception:
            logger.exception("Error discovering top players")
            return []

    def fetch_player_stats(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Orchestrator: Fetches Main Stats + Deep Dives (Clutches, Multikills, Career).
        """
        logger.info("Deep-Crawling stats for: %s", url)
        try:
            # 1. Main Stats Page (Overview + Firepower/Entrying/Utility)
            # URL format: .../stats/players/{id}/{name}
            time.sleep(random.uniform(3, 7))
            html = self._solver.get(url)
            if not html:
                logger.error("FlareSolverr failed for %s", url)
                return None

            soup = BeautifulSoup(html, "html.parser")
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
            logger.exception("Error in Deep Crawl")
            return None

    def _fetch_sub_stats(self, url: str, parser_func) -> Dict[str, Any]:
        """Generic helper for sub-page fetching."""
        try:
            time.sleep(random.uniform(2, 5))  # Polite delay
            html = self._solver.get(url)
            if html:
                return parser_func(BeautifulSoup(html, "html.parser"))
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
        """Parses the Clutches table.

        STUB: HLTV clutch page layout requires HTML inspection to implement.
        Returns empty dict rather than fabricated data.
        """
        clutches = {}
        # Try to parse clutch stats table if it exists
        rows = soup.select(".stats-table tr")
        for row in rows:
            cols = row.select("td")
            text = row.text.lower()
            if "1 on 1" in text and len(cols) >= 2:
                clutches["1on1_wins"] = self._safe_float(cols[-2].text)
                clutches["1on1_losses"] = self._safe_float(cols[-1].text)
            elif "1 on 2" in text and len(cols) >= 2:
                clutches["1on2_wins"] = self._safe_float(cols[-2].text)
            elif "1 on 3" in text and len(cols) >= 2:
                clutches["1on3_wins"] = self._safe_float(cols[-2].text)

        return clutches

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

        # Extract player nickname from page title or known selectors.
        # HLTV title format: "RealFirst 'nickname' RealLast Counter-Strike Statistics"
        player_name = None
        name_tag = soup.select_one(".player-nickname") or soup.select_one("h1.summaryNickname")
        if name_tag:
            player_name = name_tag.text.strip()
        if not player_name:
            title_tag = soup.find("title")
            if title_tag:
                import re as _re
                m = _re.search(r"'([^']+)'", title_tag.text)
                if m:
                    player_name = m.group(1)
        mapped["player_name"] = player_name or "Unknown_Pro"

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
