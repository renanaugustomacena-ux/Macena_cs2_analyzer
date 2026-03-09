from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests
from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile
# F5-22: API keys are loaded from env vars / keyring in config.py — not hard-coded.
# Verify STEAM_API_KEY and FACEIT_API_KEY are set via environment or secrets manager, never in source.
from Programma_CS2_RENAN.core.config import get_credential, get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.profile_service")  # F5-33: structured logging


class ProfileService:
    def __init__(self):
        self.steam_key = get_credential("STEAM_API_KEY")
        self.faceit_key = get_credential("FACEIT_API_KEY")

    def fetch_steam_stats(self, steam_id: str) -> Dict[str, Any]:
        """Fetches stats with connection safety and timeouts."""
        if not self.steam_key or not steam_id:
            return {"error": "Steam API key or ID missing"}
        return _execute_steam_fetch(self.steam_key, steam_id)

    def fetch_faceit_stats(self, nickname: str) -> Dict[str, Any]:
        """Fetches FaceIT Elo and level."""
        if not self.faceit_key:
            return {"error": "FaceIT API key missing"}
        return _execute_faceit_fetch(self.faceit_key, nickname)

    def sync_all_external_data(self, steam_id: str, faceit_name: str):
        """Orchestrates full profile update and saves to DB."""
        steam_data = self.fetch_steam_stats(steam_id)
        faceit_data = self.fetch_faceit_stats(faceit_name)

        # AC-28-01: Don't persist an empty profile when both fetches fail
        steam_ok = "error" not in steam_data
        faceit_ok = "error" not in faceit_data
        if not steam_ok and not faceit_ok:
            logger.warning("Both Steam and FaceIT fetches failed — skipping profile save")
            return {"status": "error", "steam": steam_data, "faceit": faceit_data}

        profile = PlayerProfile(
            player_name=get_setting("CS2_PLAYER_NAME", ""),
        )

        # P-03: Populate profile fields from successful fetches instead of
        # persisting an empty shell. PlayerProfile has bio/role fields.
        bio_parts = []
        if steam_ok:
            nickname = steam_data.get("nickname")
            if nickname:
                bio_parts.append(f"Steam: {nickname}")
            hours = steam_data.get("playtime_forever")
            if hours:
                bio_parts.append(f"{hours:.0f}h CS2")
        if faceit_ok:
            elo = faceit_data.get("elo")
            level = faceit_data.get("level")
            if elo:
                bio_parts.append(f"FaceIT Elo: {elo}")
            if level:
                bio_parts.append(f"Level {level}")
        if bio_parts:
            profile.bio = " | ".join(bio_parts)

        _persist_profile_update(profile)
        return {"status": "success", "steam": steam_data, "faceit": faceit_data}


def _execute_steam_fetch(key: str, steam_id: str) -> Dict[str, Any]:
    # P-01: Bounded retry with exponential backoff for transient Steam API failures.
    _MAX_RETRIES = 3
    import time

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
                params={"key": key, "steamids": steam_id},
                timeout=10,
            ).json()
            return _parse_steam_response(resp, key, steam_id)
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(min(2 ** attempt, 10))
            continue
        except Exception as e:
            return {"error": f"Steam Fetch Failed: {str(e)}"}
    return {"error": f"Steam Fetch Failed after {_MAX_RETRIES} retries: {last_error}"}


def _parse_steam_response(resp: Dict[str, Any], key: str, steam_id: str) -> Dict[str, Any]:
    players = resp.get("response", {}).get("players")
    if not players:
        return {"error": "Player not found"}
    p = players[0]
    # P-02: Validate player entry is a dict (Steam API contract)
    if not isinstance(p, dict):
        return {"error": "Invalid player data from Steam API"}
    cs2_hours = _fetch_cs2_hours(key, steam_id)
    return {
        "nickname": p.get("personaname"),
        "avatar": p.get("avatarfull"),
        "playtime_forever": cs2_hours,
    }


def _fetch_cs2_hours(key: str, steam_id: str) -> float:
    r = requests.get(
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/",
        params={"key": key, "steamid": steam_id, "format": "json"},
        timeout=10,
    ).json()
    games = r.get("response", {}).get("games", [])
    cs2 = next((g for g in games if g["appid"] == 730), None)
    return cs2.get("playtime_forever", 0) / 60 if cs2 else 0


def _execute_faceit_fetch(key: str, nickname: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}"}
    # AC-28-02: URL-encode nickname to prevent query string corruption
    url = f"https://open.faceit.com/data/v4/players?nickname={quote(nickname)}&game=cs2"
    try:
        r = requests.get(url, headers=headers, timeout=10).json()
        stats = r.get("games", {}).get("cs2", {})
        return {
            "elo": stats.get("faceit_elo", 0),
            "level": stats.get("skill_level", 0),
            "faceit_id": r.get("player_id"),
        }
    except Exception as e:
        return {"error": str(e)}


def _persist_profile_update(profile):
    db = get_db_manager()
    # F5-21: get_session() context manager auto-commits on clean exit and
    # rolls back on exception — explicit session.commit() is not required here.
    with db.get_session() as session:
        stmt = select(PlayerProfile).where(PlayerProfile.player_name == get_setting("CS2_PLAYER_NAME", ""))
        existing = session.exec(stmt).first()
        _update_or_add_profile(session, existing, profile)


def _update_or_add_profile(session, existing, profile):
    if not existing:
        session.add(profile)
        return
    _apply_profile_fields(existing, profile)
    session.add(existing)


def _apply_profile_fields(existing, profile):
    for key, val in profile.model_dump(exclude_unset=True).items():
        if key != "id":
            setattr(existing, key, val)
