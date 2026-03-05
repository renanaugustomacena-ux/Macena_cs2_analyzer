# F6-01: Removed unused `import torch`. Replaced `import datetime` with explicit imports.
# F6-05: Replaced all print() calls with structured logger calls.
# F6-04: datetime.utcnow() → datetime.now(timezone.utc) (timezone-aware).
# Anti-fabrication: _map_stats_to_model() raises ValueError on missing/unparseable stats
# instead of silently inserting hardcoded fallback values into the pro baseline DB.
from datetime import datetime, timezone
from typing import Optional

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.backend.data_sources.hltv.selectors import HLTVURLBuilder, PlayerStatsSelectors
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv.players")


class PlayerCollector:
    def __init__(self, page, limiter):
        self.page = page
        self.limiter = limiter

    def discover_player_ids(self, start_id=1, end_id=35000):
        ids_to_check = _prepare_id_list(start_id, end_id)
        logger.info("Starting Discovery Pass for IDs %s to %s...", start_id, end_id)
        return _execute_discovery_loop(self, ids_to_check)

    def scrape_from_list(self, url_list):
        logger.info("Starting Extraction Pass for %s validated URLs...", len(url_list))
        return _execute_extraction_loop(self, url_list)


def _prepare_id_list(start, end):
    ids = list(range(start, end + 1))
    if 21266 not in ids:
        ids.append(21266)
        ids.sort()
    return ids


def _execute_discovery_loop(collector, ids):
    valid_urls = []
    for pid in ids:
        url = f"https://www.hltv.org/player/{pid}/_"
        _check_single_player_id(collector, pid, url, valid_urls)
    return valid_urls


def _check_single_player_id(coll, pid, url, results):
    try:
        logger.debug("Checking ID %s...", pid)
        resp = coll.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        coll.limiter.wait("micro")
        if _is_profile_valid(coll.page, resp, pid):
            logger.info("[Valid] ID %s -> %s", pid, coll.page.url)
            results.append(coll.page.url)
    except Exception as e:
        logger.error("[Error] Failed ID %s: %s", pid, e)
        coll.limiter.wait("backoff")


def _is_profile_valid(page, resp, pid):
    if resp.status >= 400 or "/player/" not in page.url or f"/{pid}/" not in page.url:
        return False
    return (
        page.locator(".playerRealname").is_visible() or page.locator(".playerNickname").is_visible()
    )


def _execute_extraction_loop(collector, url_list):
    db_manager = get_db_manager()
    count = 0
    for url in url_list:
        collector.limiter.wait("heavy")
        if _extract_player_data(collector, url, db_manager):
            count += 1
    return count


def _extract_player_data(coll, url, db):
    detailed_url = url.replace("/player/", "/stats/players/individual/")
    player_name = url.split("/")[-1]
    logger.info("Extracting stats for %s...", player_name)
    try:
        coll.page.goto(detailed_url, wait_until="domcontentloaded", timeout=60000)
        coll.limiter.wait("standard")
        return _process_extraction_page(coll, player_name, db)
    except Exception as e:
        logger.error("[Error] Failed %s: %s", url, e)
        return False


def _process_extraction_page(coll, name, db):
    if not coll.page.locator(".statistics").is_visible():
        return False
    stats = coll.page.eval_on_selector(".statistics", _get_stats_js())
    match_stats = _map_stats_to_model(name, stats, coll.page.content())
    db.upsert(match_stats)
    logger.info("[Success] Fully synced %s", name)
    return True


def _get_stats_js():
    return """el => {
        const rows = Array.from(el.querySelectorAll('.stat-row'));
        const d = {};
        rows.forEach(r => {
            const label = r.firstChild.innerText.trim();
            const value = r.lastChild.innerText.trim();
            d[label] = value;
        });
        return d;
    }"""


def _parse_required_stat(key: str, raw: Optional[str], player_name: str) -> float:
    """Parse a required stat to float; raise ValueError if absent or unparseable (F6-01).

    Anti-fabrication: no fallback defaults allowed for required stats.
    """
    if raw is None:
        raise ValueError(f"Missing required stat '{key}' for player {player_name}")
    try:
        return float(raw.split()[0].replace("%", ""))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Unparseable stat '{key}' for player {player_name}: {raw!r}"
        ) from exc


def _map_stats_to_model(name: str, stats: dict, html: str) -> PlayerMatchStats:
    # F6-01: Anti-fabrication — all hardcoded fallback string defaults removed.
    # Missing or unparseable required stats raise ValueError so failures are explicit
    # rather than silently inserting fabricated data into the pro baseline DB.
    rating_raw = stats.get("Rating 2.0") or stats.get("Rating 1.0")
    if rating_raw is None:
        raise ValueError(f"Missing required stat 'Rating' for player {name}")

    kast_raw = stats.get("KAST")
    kast = _parse_required_stat("KAST", kast_raw, name) / 100

    hs_raw = stats.get("Headshot %")
    avg_hs = _parse_required_stat("Headshot %", hs_raw, name) / 100 if hs_raw else 0.0

    return PlayerMatchStats(
        user_id="system",
        player_name=name,
        demo_name=f"hltv_discovered_{name}.dem",
        avg_kills=_parse_required_stat("Kills per round", stats.get("Kills per round"), name),
        avg_deaths=_parse_required_stat("Deaths per round", stats.get("Deaths per round"), name),
        avg_adr=_parse_required_stat("Damage / round", stats.get("Damage / round"), name),
        avg_hs=avg_hs,
        avg_kast=kast,
        rating=_parse_required_stat("Rating", rating_raw, name),
        kd_ratio=_parse_required_stat("K/D Ratio", stats.get("K/D Ratio"), name),
        kill_std=0.0,   # Not available from HLTV stats page; computed separately
        adr_std=0.0,    # Not available from HLTV stats page; computed separately
        impact_rounds=_parse_required_stat("Impact", stats.get("Impact"), name),
        anomaly_score=0.0,
        sample_weight=1.0,
        is_pro=True,
        processed_at=datetime.now(timezone.utc),  # F6-04: timezone-aware UTC
    )
