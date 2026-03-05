"""
HLTV Player Statistics Fetcher

Fetches pro player statistics from HLTV.org player pages via FlareSolverr.
Saves data into ProPlayer + ProPlayerStatCard in hltv_metadata.db.

Data scraped (text only — no file downloads):
    - Main stats: Rating 2.0, KPR, DPR, ADR, KAST, HS%, Impact
    - Trait sections: Firepower, Entrying, Utility
    - Sub-pages: Clutches, Multikills, Career history
"""

import json
import random
import re
import time
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from Programma_CS2_RENAN.backend.data_sources.hltv.flaresolverr_client import FlareSolverrClient
from Programma_CS2_RENAN.backend.storage.database import get_hltv_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import ProPlayer, ProPlayerStatCard
from Programma_CS2_RENAN.observability.logger_setup import get_logger
from sqlmodel import select

logger = get_logger("cs2analyzer.hltv_stat_fetcher")


class HLTVStatFetcher:
    """
    Fetches player statistics from HLTV.org.

    Uses FlareSolverr (Docker) to bypass Cloudflare protection.
    All HTTP requests go through the local FlareSolverr REST API
    which resolves JS challenges automatically.

    Saves to ProPlayer + ProPlayerStatCard in hltv_metadata.db.
    """

    def __init__(self):
        if not _HAS_BS4:
            raise ImportError(
                "beautifulsoup4 is required for HLTV stat fetching. "
                "Install it with: pip install beautifulsoup4"
            )
        self._solver = FlareSolverrClient(timeout=60)
        self._hltv_db = get_hltv_db_manager()

    def fetch_top_players(self) -> List[str]:
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

    def fetch_and_save_player(self, url: str) -> bool:
        """
        Fetch player stats from HLTV and save to hltv_metadata.db.

        Args:
            url: HLTV player stats URL (e.g. https://www.hltv.org/stats/players/2023/fallen)

        Returns:
            True if successfully fetched and saved, False otherwise.
        """
        data = self._fetch_player_stats(url)
        if not data:
            return False

        player_name = data.pop("player_name", "Unknown_Pro")
        hltv_id = data.pop("hltv_id", None)

        if hltv_id is None:
            logger.error("Could not extract HLTV ID from URL: %s", url)
            return False

        return self._save_to_db(hltv_id, player_name, data)

    def _fetch_player_stats(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetches Main Stats + Deep Dives (Clutches, Multikills, Career).
        """
        logger.info("Deep-Crawling stats for: %s", url)
        try:
            time.sleep(random.uniform(3, 7))
            html = self._solver.get(url)
            if not html:
                logger.error("FlareSolverr failed for %s", url)
                return None

            soup = BeautifulSoup(html, "html.parser")
            main_data = self._parse_overview(soup)

            # Extract ID and Name from URL: .../stats/players/{id}/{name}
            tokens = url.rstrip("/").split("/")
            if len(tokens) >= 2:
                p_id = tokens[-2]
                p_name = tokens[-1]

                # Try to parse HLTV ID
                try:
                    main_data["hltv_id"] = int(p_id)
                except ValueError:
                    logger.warning("Non-numeric player ID in URL: %s", p_id)
                    return None

                detailed = {}
                detailed.update(self._parse_trait_sections(soup))

                # Sub-pages
                clutch_url = url.replace(
                    "/stats/players/", "/stats/players/clutches/"
                ).replace(f"/{p_id}/", f"/{p_id}/all/")
                detailed["clutches"] = self._fetch_sub_stats(clutch_url, self._parse_clutches)

                multikill_url = url.replace(
                    "/stats/players/", "/stats/players/multikills/"
                ).replace(f"/{p_id}/", f"/{p_id}/all/")
                detailed["multikills"] = self._fetch_sub_stats(
                    multikill_url, self._parse_multikills
                )

                career_url = url.replace("/stats/players/", "/stats/players/career/")
                detailed["career"] = self._fetch_sub_stats(career_url, self._parse_career)

                main_data["detailed_stats_json"] = detailed

            return main_data

        except Exception:
            logger.exception("Error in Deep Crawl for %s", url)
            return None

    def _save_to_db(self, hltv_id: int, nickname: str, data: Dict[str, Any]) -> bool:
        """Save fetched data to ProPlayer + ProPlayerStatCard in hltv_metadata.db."""
        try:
            with self._hltv_db.get_session() as session:
                # Upsert ProPlayer
                player = session.exec(
                    select(ProPlayer).where(ProPlayer.hltv_id == hltv_id)
                ).first()

                if not player:
                    player = ProPlayer(hltv_id=hltv_id, nickname=nickname)
                    session.add(player)
                    session.commit()
                    session.refresh(player)
                    logger.info("Created ProPlayer: %s (ID: %s)", nickname, hltv_id)
                else:
                    player.nickname = nickname
                    session.add(player)
                    session.commit()

                # Upsert ProPlayerStatCard
                card = session.exec(
                    select(ProPlayerStatCard).where(
                        ProPlayerStatCard.player_id == hltv_id
                    )
                ).first()

                detailed_json_str = "{}"
                if "detailed_stats_json" in data:
                    detailed_json_str = json.dumps(data.pop("detailed_stats_json"))

                card_data = {
                    "player_id": hltv_id,
                    "rating_2_0": data.get("rating", 0.0),
                    "kpr": data.get("kpr", 0.0),
                    "dpr": data.get("dpr", 0.0),
                    "adr": data.get("adr", 0.0),
                    "kast": data.get("kast_pct", 0.0),
                    "impact": data.get("impact_rating", 0.0),
                    "headshot_pct": data.get("hs_pct", 0.0),
                    "maps_played": data.get("maps_played", 0),
                    "opening_kill_ratio": data.get("opening_kill_ratio", 0.0),
                    "opening_duel_win_pct": data.get("opening_duel_win_pct", 0.0),
                    "detailed_stats_json": detailed_json_str,
                    "time_span": "all_time",
                }

                if card:
                    for key, value in card_data.items():
                        setattr(card, key, value)
                    session.add(card)
                else:
                    card = ProPlayerStatCard(**card_data)
                    session.add(card)

                session.commit()
                logger.info("Saved stat card for %s (ID: %s)", nickname, hltv_id)
                return True

        except Exception:
            logger.exception("Failed to save stats for %s (ID: %s)", nickname, hltv_id)
            return False

    def _fetch_sub_stats(self, url: str, parser_func) -> Dict[str, Any]:
        """Generic helper for sub-page fetching."""
        try:
            time.sleep(random.uniform(2, 5))
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
            clean_text = text.replace("%", "").replace(",", ".").strip()
            clean_text = clean_text.split()[0]
            return float(clean_text)
        except (ValueError, TypeError):
            return 0.0

    def _parse_overview(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses the player overview page."""
        stats = {}
        rows = soup.select(".stats-row")
        for row in rows:
            spans = row.find_all("span")
            if len(spans) == 2:
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
                if "maps played" in label:
                    stats["maps_played"] = value

        mapped = {
            "kpr": self._safe_float(stats.get("kpr")),
            "dpr": self._safe_float(stats.get("dpr")),
            "adr": self._safe_float(stats.get("adr")),
            "hs_pct": self._safe_float(stats.get("hs")),
            "kast_pct": self._safe_float(stats.get("kast")),
            "rating": self._safe_float(stats.get("rating")),
            "impact_rating": self._safe_float(stats.get("impact")),
            "maps_played": int(self._safe_float(stats.get("maps_played"))),
        }

        # K/D ratio
        if mapped["dpr"] > 0:
            mapped["kd_ratio"] = mapped["kpr"] / mapped["dpr"]
        else:
            mapped["kd_ratio"] = 0.0

        # Player nickname
        player_name = None
        name_tag = soup.select_one(".player-nickname") or soup.select_one("h1.summaryNickname")
        if name_tag:
            player_name = name_tag.text.strip()
        if not player_name:
            title_tag = soup.find("title")
            if title_tag:
                m = re.search(r"'([^']+)'", title_tag.text)
                if m:
                    player_name = m.group(1)
        mapped["player_name"] = player_name or "Unknown_Pro"

        return mapped

    def _parse_trait_sections(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses Firepower, Entrying, Utility columns from Main Stats Page."""
        traits = {}

        section_map = {
            "Kills per round": ("firepower", "kpr"),
            "Damage per round": ("firepower", "adr"),
            "Opening duel win": ("entrying", "opening_win_pct"),
            "Traded deaths": ("entrying", "traded_deaths_pct"),
            "Flash assists": ("utility", "flash_assists"),
            "Damage per round win": ("firepower", "adr_win"),
            "Kills per round win": ("firepower", "kpr_win"),
        }

        rows = soup.select("tr") + soup.select(".stats-row")

        for row in rows:
            text = row.text.strip()
            for key_phrase, (category, json_key) in section_map.items():
                if key_phrase.lower() in text.lower():
                    chunks = [t.strip() for t in row.text.split("\n") if t.strip()]
                    if len(chunks) >= 2:
                        val = self._safe_float(chunks[-1])
                        if category not in traits:
                            traits[category] = {}
                        traits[category][json_key] = val

        return traits

    def _parse_clutches(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parses the Clutches table."""
        clutches = {}
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
        rows = soup.select(".stats-table tbody tr")
        history = {}
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 2:
                period = cols[0].text.strip()
                rating = self._safe_float(cols[1].text)
                if period.isdigit():
                    history[period] = rating
        career["rating_history"] = history
        return career
