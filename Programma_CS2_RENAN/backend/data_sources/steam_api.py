import time

import requests

from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.steam_api")

MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]  # seconds


def _request_with_retry(url, params, timeout=5, max_total_timeout=20):
    """HTTP GET with exponential backoff retry for transient failures.

    Args:
        url: Target URL.
        params: Query parameters dict.
        timeout: Per-request socket timeout in seconds.
        max_total_timeout: DS-03 — hard ceiling (monotonic clock) for the
            entire retry loop. Prevents unbounded blocking when multiple
            retries compound with backoff delays.
    """
    deadline = time.monotonic() + max_total_timeout
    last_exc = None
    for attempt in range(MAX_RETRIES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            app_logger.warning(
                "Steam API total timeout (%ds) exceeded before attempt %d",
                max_total_timeout,
                attempt + 1,
            )
            break
        try:
            # Per-request timeout capped to remaining budget
            effective_timeout = min(timeout, remaining)
            resp = requests.get(url, params=params, timeout=effective_timeout)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            delay = BACKOFF_DELAYS[attempt] if attempt < len(BACKOFF_DELAYS) else BACKOFF_DELAYS[-1]
            # Cap sleep to remaining time budget
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            delay = min(delay, remaining)
            app_logger.warning(
                "Steam API attempt %d/%d failed: %s — retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                e,
                delay,
            )
            time.sleep(delay)
        except requests.exceptions.HTTPError:
            raise  # Don't retry on 4xx/5xx — let caller handle
    raise last_exc


def resolve_vanity_url(vanity_url, api_key):
    """
    Resolves a Steam Custom URL to a 64-bit Steam ID.
    Returns the ID as string or None.
    """
    url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
    params = {"key": api_key.strip(), "vanityurl": vanity_url.strip()}
    app_logger.debug("Resolving vanity URL '%s'", vanity_url.strip())
    try:
        resp = _request_with_retry(url, params, timeout=5)
        app_logger.debug("Resolve status code: %s", resp.status_code)
        data = resp.json()
        if data.get("response", {}).get("success") == 1:
            return data["response"]["steamid"]
        else:
            app_logger.warning("Resolve failed: %s", data)
    except Exception as e:
        app_logger.error("Resolve error: %s", e)
    return None


def fetch_steam_profile(steam_id, api_key):
    """
    Fetches basic player profile from Steam Web API.
    Handles Vanity URLs automatically.
    """
    if not steam_id or not api_key:
        raise ValueError("Missing Steam ID or API Key")

    steam_id = str(steam_id).strip()
    api_key = str(api_key).strip()

    # Auto-Resolve Vanity URL if not numeric
    if not steam_id.isdigit():
        resolved = resolve_vanity_url(steam_id, api_key)
        if not resolved:
            raise ValueError(
                f"Could not resolve Steam Custom URL: '{steam_id}'. Please use the 64-bit ID (765...)"
            )
        steam_id = resolved

    # R3-M04: Validate Steam64 ID format (17-digit numeric starting with 765)
    if not (steam_id.isdigit() and len(steam_id) == 17):
        raise ValueError(
            f"Invalid Steam64 ID: '{steam_id}'. Expected 17-digit numeric string."
        )

    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {"key": api_key, "steamids": steam_id}

    app_logger.debug("Fetching profile for ID %s", steam_id)
    try:
        resp = _request_with_retry(url, params, timeout=5)
        app_logger.debug("Profile status code: %s", resp.status_code)
        if resp.status_code == 403:
            # Try to see if there's any body info
            app_logger.warning("403 Forbidden. Response text: %s", resp.text)

        resp.raise_for_status()
        data = resp.json()
        players = data.get("response", {}).get("players", [])

        if not players:
            return None

        return players[0]
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            raise ValueError(
                "Steam API Error 403: Forbidden.\nYour API Key is invalid or restricted.\nPlease generate a new key at: steamcommunity.com/dev/apikey"
            )
        raise
    except Exception as e:
        app_logger.error("Steam API Error: %s", e)
        raise
