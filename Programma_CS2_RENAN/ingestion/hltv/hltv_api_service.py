import re
import time
from datetime import datetime, timezone

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.ingestion.hltv.browser.manager import BrowserManager
from Programma_CS2_RENAN.ingestion.hltv.cache import get_proxy
from Programma_CS2_RENAN.ingestion.hltv.rate_limit import RateLimiter
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv_service")

# Reference player for calibration — s1mple (HLTV ID 7998 maps to stats page 21266)
REFERENCE_PLAYER_ID = 21266

# Default metadata values for fields not available from HLTV scraping
KILL_STD_DEFAULT = 0.1  # Placeholder — HLTV does not expose per-round variance
ADR_STD_DEFAULT = 5.0  # Placeholder — HLTV does not expose per-round variance


# F6-10: Circuit breaker — stops the loop after MAX_FAILURES consecutive failures
# to avoid wasting hours on a blocked/unavailable service.
class _CircuitBreaker:
    """Open after MAX_FAILURES consecutive failures; resets after RESET_WINDOW_S."""

    MAX_FAILURES = 10
    RESET_WINDOW_S = 3600.0

    def __init__(self):
        self._failures = 0
        self._last_failure_ts: float = 0.0

    def record_failure(self) -> None:
        now = time.monotonic()
        if now - self._last_failure_ts > self.RESET_WINDOW_S:
            self._failures = 0
        self._failures += 1
        self._last_failure_ts = now

    def record_success(self) -> None:
        self._failures = 0

    @property
    def is_open(self) -> bool:
        return self._failures >= self.MAX_FAILURES


class HLTVApiService:
    def __init__(self, headless=True):
        self.browser_manager = BrowserManager(headless=headless)
        self.limiter = RateLimiter()
        self.proxy = get_proxy()
        self._flaresolverr = None  # Lazy-init on first Cloudflare block

    def _get_flaresolverr(self):
        """Lazy-init FlareSolverr client as Cloudflare bypass fallback."""
        if self._flaresolverr is None:
            from Programma_CS2_RENAN.ingestion.hltv.flaresolverr_client import FlareSolverrClient
            self._flaresolverr = FlareSolverrClient()
        return self._flaresolverr

    def sync_range(self, start_id, end_id):
        page = self.browser_manager.start()
        db_manager = get_db_manager()
        ids = self._get_ids_range(start_id, end_id)
        logger.info("Starting Stability Sync for IDs %s...", ids)
        synced = _sync_ids_loop(self, page, db_manager, ids)
        self.browser_manager.close()
        return synced

    def _get_ids_range(self, start, end):
        ids = list(range(start, end + 1))
        if REFERENCE_PLAYER_ID not in ids:
            ids.append(REFERENCE_PLAYER_ID)
        ids.sort()
        return ids

    def _sync_player(self, page, db_manager, pid):
        # TASK 2.8.1: Check cache first
        cached_html = self.proxy.get_player_html(pid)

        if cached_html:
            logger.info("Cache HIT for ID %s", pid)
            # Load cached HTML into page to reuse JS extraction logic
            page.set_content(cached_html, wait_until="domcontentloaded")
            return _process_player_page(self, page, db_manager, pid)

        # Cache Miss - Fetch Live
        url = f"https://www.hltv.org/stats/players/individual/{pid}/_"
        logger.info("Fetching live from HLTV for ID %s...", pid)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Save to cache
            html_content = page.content()
            self.proxy.save_player_html(pid, html_content)

            self.limiter.wait("standard")
            return _process_player_page(self, page, db_manager, pid)

        except Exception as e:
            logger.exception("Failed to fetch ID %s", pid)
            return False

    def _extract_stats(self, page):
        return page.eval_on_selector(".statistics", _get_stats_js_eval())

    def _get_nickname(self, page, pid):
        if page.locator(".player-nickname").is_visible():
            return page.locator(".player-nickname").inner_text().strip()
        return f"Player_{pid}"

    def _map_to_model(self, data, nick, pid, html):
        stats = _build_stats_dict(data, nick, pid, html)
        m = PlayerMatchStats(**stats)
        _apply_hs_ratio(m, html)
        return m


def _sync_ids_loop(svc, page, db, id_list):
    count = 0
    breaker = _CircuitBreaker()  # F6-10: circuit breaker to abort on consecutive failures
    for pid in id_list:
        if breaker.is_open:  # F6-10: abort loop when circuit is open
            logger.error(
                "Circuit breaker OPEN after %s consecutive failures — aborting sync loop",
                _CircuitBreaker.MAX_FAILURES,
            )
            break
        try:
            if svc._sync_player(page, db, pid):
                breaker.record_success()
                count += 1
            else:
                breaker.record_failure()
        except Exception as e:
            logger.exception("Fail ID %s", pid)
            breaker.record_failure()
            svc.limiter.wait("backoff")
    return count


def _is_cloudflare_block(page) -> bool:
    """Detect Cloudflare challenge or block pages robustly (F6-21)."""
    title = page.title().lower()
    try:
        content = page.content().lower()
    except Exception:
        logger.debug("Could not retrieve page content for Cloudflare check", exc_info=True)
        content = ""
    return (
        "attention required" in title
        or "just a moment" in title
        or "cf-browser-verification" in content
        or "challenge-form" in content
        or page.locator("#cf-challenge-running").count() > 0
    )


def _process_player_page(svc, page, db, pid):
    if _is_cloudflare_block(page):  # F6-21: robust Cloudflare detection
        logger.warning("Cloudflare detected for ID %s — trying FlareSolverr fallback", pid)
        if _try_flaresolverr_fallback(svc, page, db, pid):
            return True
        svc.limiter.wait("backoff")
        return False
    if not page.locator(".statistics").is_visible():
        logger.warning("No stats for ID %s", pid)
        return False
    _finalize_extraction(svc, page, db, pid)
    return True


def _try_flaresolverr_fallback(svc, page, db, pid):
    """Attempt to fetch player page via FlareSolverr when Cloudflare blocks."""
    try:
        client = svc._get_flaresolverr()
        if not client.is_available():
            logger.warning("FlareSolverr not available — skipping fallback")
            return False

        url = f"https://www.hltv.org/stats/players/individual/{pid}/_"
        html = client.get(url)
        if not html:
            return False

        # Load FlareSolverr HTML into Playwright page for JS extraction
        page.set_content(html, wait_until="domcontentloaded")

        if _is_cloudflare_block(page):
            logger.error("FlareSolverr also blocked by Cloudflare for ID %s", pid)
            return False

        if not page.locator(".statistics").is_visible():
            logger.warning("FlareSolverr: no stats visible for ID %s", pid)
            return False

        # Save to cache for future reuse
        svc.proxy.save_player_html(pid, html)
        _finalize_extraction(svc, page, db, pid)
        logger.info("FlareSolverr fallback succeeded for ID %s", pid)
        return True
    except Exception as exc:
        logger.error("FlareSolverr fallback failed for ID %s: %s", pid, exc)
        return False


def _finalize_extraction(svc, page, db, pid):
    data = svc._extract_stats(page)
    nick = svc._get_nickname(page, pid)
    m = svc._map_to_model(data, nick, pid, page.content())
    db.upsert(m)
    logger.info("Synced %s", nick)


def _get_stats_js_eval():
    return "el => { const rows = Array.from(el.querySelectorAll('.stat-row')); const d = {}; rows.forEach(r => { d[r.firstChild.innerText.trim()] = r.lastChild.innerText.trim(); }); return d; }"


def _build_stats_dict(d, nick, pid, html):
    # Validate required fields are present (no hardcoded fallbacks allowed)
    required_fields = {
        "Kills per round": d.get("Kills per round"),
        "Deaths per round": d.get("Deaths per round"),
        "Damage / round": d.get("Damage / round"),
        "KAST": d.get("KAST"),
    }

    missing = [k for k, v in required_fields.items() if v is None]
    if missing:
        logger.error("Player %s (%s) missing required fields: %s", pid, nick, missing)
        raise ValueError(f"Incomplete HLTV data for player {pid}: missing {missing}")

    # Extract rating (2.0 preferred, fallback to 1.0 if neither exists)
    rating_20 = d.get("Rating 2.0")
    rating_10 = d.get("Rating 1.0")
    if not rating_20 and not rating_10:
        logger.error("Player %s (%s) missing both Rating 2.0 and Rating 1.0", pid, nick)
        raise ValueError(f"No rating data for player {pid}")
    rating = float(rating_20 or rating_10)

    # K/D Ratio required
    kd_ratio_str = d.get("K/D Ratio")
    if not kd_ratio_str:
        logger.error("Player %s (%s) missing K/D Ratio", pid, nick)
        raise ValueError(f"No K/D ratio for player {pid}")

    # Impact (optional - defaults to 0.0 if missing)
    impact_str = d.get("Impact")
    impact = float(impact_str) if impact_str else 0.0
    if not impact_str:
        logger.warning("Player %s (%s) missing Impact stat - defaulting to 0.0", pid, nick)

    return {
        "user_id": "system",
        "player_name": nick,
        "demo_name": f"api_{pid}.dem",
        "avg_kills": float(required_fields["Kills per round"].split()[0]),
        "avg_deaths": float(required_fields["Deaths per round"].split()[0]),
        "avg_adr": float(required_fields["Damage / round"].split()[0]),
        "avg_hs": 0.0,  # Populated by _apply_hs_ratio from HTML regex
        "avg_kast": float(required_fields["KAST"].replace("%", "")) / 100,
        "rating": rating,
        "kd_ratio": float(kd_ratio_str),
        "kill_std": KILL_STD_DEFAULT,
        "adr_std": ADR_STD_DEFAULT,
        "impact_rounds": impact,
        "anomaly_score": 0.0,  # Computed later by drift detection
        "sample_weight": 1.0,  # Default weight for pro data
        "is_pro": True,
        "processed_at": datetime.now(timezone.utc),  # F6-04: timezone-aware UTC
    }


def _apply_hs_ratio(m, html):
    match = re.search(r"Headshot %.*?(\d+\.\d+)%", html)
    if match:
        m.avg_hs = float(match.group(1)) / 100
    else:
        logger.warning(
            "Failed to extract Headshot %% for %s (ID: %s) - avg_hs remains 0.0",
            m.player_name,
            m.demo_name,
        )
