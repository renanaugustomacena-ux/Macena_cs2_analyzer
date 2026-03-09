import hashlib
import hmac
import os
import pickle
from typing import Dict, List, Tuple

import pandas as pd
from demoparser2 import DemoParser

from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import validate_demo_file
from Programma_CS2_RENAN.core.demo_frame import (
    BombState,
    DemoFrame,
    EventType,
    GameEvent,
    NadeState,
    NadeType,
    PlayerState,
    Team,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.demo_loader")


# DS-01: Restricted unpickler — prevents arbitrary code execution from
# crafted cache files.  Only allows demo_frame dataclasses and builtins.
_ALLOWED_MODULES = {
    "Programma_CS2_RENAN.core.demo_frame": {
        "BombState", "DemoFrame", "EventType", "GameEvent",
        "NadeState", "NadeType", "PlayerState", "Team",
    },
    "builtins": {"True", "False", "None"},
}


class _SafeUnpickler(pickle.Unpickler):
    """Unpickler that rejects classes outside the demo_frame allowlist."""

    def find_class(self, module: str, name: str):
        allowed = _ALLOWED_MODULES.get(module)
        if allowed is not None and name in allowed:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"DS-01: Blocked deserialization of {module}.{name} — "
            f"not in cache allowlist"
        )


def _get_cache_hmac_key() -> bytes:
    """Derive a machine-local HMAC key for cache integrity verification."""
    import socket

    seed = f"cs2analyzer-cache-{socket.gethostname()}-{os.getuid() if hasattr(os, 'getuid') else 'win'}"
    return hashlib.sha256(seed.encode()).digest()


def _pickle_dump_signed(obj, path: str) -> None:
    """Serialize with pickle and write an HMAC signature for integrity."""
    data = pickle.dumps(obj)
    sig = hmac.new(_get_cache_hmac_key(), data, hashlib.sha256).digest()
    with open(path, "wb") as f:
        f.write(sig)  # first 32 bytes = HMAC-SHA256
        f.write(data)


def _pickle_load_verified(path: str):
    """Load pickle data only after HMAC integrity verification.

    DS-01: Uses _SafeUnpickler instead of pickle.loads() to prevent
    arbitrary code execution from crafted cache files.
    """
    with open(path, "rb") as f:
        sig = f.read(32)
        data = f.read()
    expected = hmac.new(_get_cache_hmac_key(), data, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Cache file integrity check failed — HMAC mismatch")
    import io

    return _SafeUnpickler(io.BytesIO(data)).load()


class DemoLoader:
    """
    Handles loading and parsing of CS2 .dem files using demoparser2.
    Implements caching and multi-map support.
    """

    CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
    CACHE_VERSION = "v20_money_fix"  # Increment to invalidate old caches

    @staticmethod
    def load_demo(
        path: str, force_reparse: bool = False
    ) -> Dict[str, Tuple[List[DemoFrame], List[GameEvent], Dict[str, int]]]:
        try:
            from Programma_CS2_RENAN.observability.sentry_setup import add_breadcrumb

            add_breadcrumb("ingestion", f"Demo parse started: {os.path.basename(path)}")
        except ImportError:
            pass

        if not os.path.exists(path):
            raise FileNotFoundError(f"Demo file not found: {path}")

        if not os.path.exists(DemoLoader.CACHE_DIR):
            os.makedirs(DemoLoader.CACHE_DIR)

        demo_name = os.path.basename(path)
        file_stats = os.stat(path)
        cache_name = f"{demo_name}_{file_stats.st_size}_{DemoLoader.CACHE_VERSION}.mcn"
        cache_path = os.path.join(DemoLoader.CACHE_DIR, cache_name)

        if os.path.exists(cache_path) and not force_reparse:
            app_logger.info("Loading cached simulation from %s", cache_name)
            try:
                data = _pickle_load_verified(cache_path)
                return data
            except Exception as e:
                app_logger.warning("Cache load failed, re-parsing: %s", e)

        # Pre-parse validation via DemoFormatAdapter (Proposal 12)
        validation = validate_demo_file(path)
        if not validation["valid"]:
            raise ValueError(f"Demo validation failed: {validation['error']}")
        for warning in validation.get("warnings", []):
            app_logger.warning("Demo format warning: %s", warning)

        app_logger.info("Parsing headers and base data for %s", path)
        parser = DemoParser(path)

        header = parser.parse_header()
        tick_rate = float(header.get("tick_rate", 64.0) or 64.0)
        default_map = header.get("map_name", "unknown")

        # --- 1. EXTRACT PLAYER POSITIONS (Two-Pass Baseline) ---
        app_logger.info("Pass 1 - Extracting player positions")
        fields = ["tick", "steamid", "X", "Y", "Z"]
        pos_by_tick = {}  # tick -> {steamid -> (x,y,z)}
        try:
            rows_df = parser.parse_ticks(fields)
            for row in rows_df.itertuples():
                t = int(getattr(row, "tick", 0))
                # C-08: Guard against NULL steamid/entity_id in tick data
                sid_raw = getattr(row, "steamid", None)
                if sid_raw is None:
                    continue
                sid = int(sid_raw or 0)
                if sid != 0:
                    if t not in pos_by_tick:
                        pos_by_tick[t] = {}
                    pos_by_tick[t][sid] = (
                        float(getattr(row, "X", 0.0) or 0.0),
                        float(getattr(row, "Y", 0.0) or 0.0),
                        float(getattr(row, "Z", 0.0) or 0.0),
                    )
            del rows_df
        except Exception as e:
            app_logger.error("Error in Pass 1 (player positions): %s", e)

        # --- 2. NADE EVENTS ---
        app_logger.info("Pass 2 - Linking grenades via baseline")
        nades_by_tick = {}  # tick -> List[NadeState]        # Helper to find thrower pos
        throws_df = parser.parse_events(["grenade_thrown"])
        throws = throws_df[0][1] if throws_df else pd.DataFrame()
        if not throws.empty:
            # Ensure steamid is string for consistent comparison
            throws["user_steamid"] = throws["user_steamid"].astype(str)

        def get_throw_data(det_tick, sid, tag):
            if throws.empty:
                return None, None
            sid_str = str(sid)
            # Limit search to 10 seconds before detonation to avoid mis-matching
            MAX_THROW_AGE = 10 * int(tick_rate)
            m = throws[
                (throws["tick"] < det_tick)
                & (throws["tick"] >= det_tick - MAX_THROW_AGE)
                & (throws["user_steamid"] == sid_str)
                & (throws["weapon"].str.contains(tag, case=False, na=False))
            ]
            if not m.empty:
                t_row = m.iloc[-1]
                t_tick = int(t_row["tick"])
                # Look up thrower pos in our baseline
                t_pos = pos_by_tick.get(t_tick, {}).get(sid)
                if not t_pos:
                    # Fallback: find nearest previous tick for this player
                    for offset in range(1, 15):
                        tp = pos_by_tick.get(t_tick - offset, {}).get(sid)
                        if tp:
                            t_pos = tp
                            break
                return t_tick, t_pos
            return None, None

        # Helper for common fields in all nade events (Note: lowercase x,y,z in events)
        def process_nades(event_list, n_type, dur_ticks=0, is_start_end=False):
            # WARNING: MAX_NADE_DURATION is a HEURISTIC CEILING, not ground truth
            # When end events are missing, durations are capped at this arbitrary value
            # This becomes training data, so capped durations may poison temporal models
            # TODO: Add 'duration_capped' flag to NadeState for transparency
            MAX_NADE_DURATION = 20 * int(tick_rate)  # 20 seconds fallback (heuristic)
            FADE_TICKS = 5 * int(tick_rate)  # 5 seconds for fade-out
            capped_count = 0  # Track how many grenades hit the ceiling
            try:
                res = parser.parse_events(event_list)
                if not res:
                    return

                # Group by event name and ensure they are sorted by tick
                data = {evt[0]: evt[1].sort_values("tick") for evt in res if not evt[1].empty}

                if is_start_end:
                    start_ev, end_ev = event_list
                    starts = data.get(start_ev, pd.DataFrame())
                    ends = data.get(end_ev, pd.DataFrame())

                    if not starts.empty:
                        for s_row in starts.itertuples():
                            eid = getattr(s_row, "entityid", None)
                            if eid is None:
                                continue

                            # Match end event that happens after this start event for the same entity
                            # Limit search window to 30s to avoid cross-half mis-matches
                            et = int(s_row.tick) + MAX_NADE_DURATION
                            duration_capped = True
                            if not ends.empty:
                                e_match = ends[
                                    (ends["entityid"] == eid)
                                    & (ends["tick"] > s_row.tick)
                                    & (ends["tick"] < s_row.tick + (30 * 64))
                                ]
                                if not e_match.empty:
                                    et = min(et, int(e_match.iloc[0].tick))
                                    duration_capped = False  # Found real end event

                            if duration_capped:
                                capped_count += 1

                            st = int(s_row.tick)
                            sid = int(getattr(s_row, "user_steamid", 0) or 0)
                            tag = "smoke" if n_type == NadeType.SMOKE else "molotov"
                            t_tick, t_pos = get_throw_data(st, sid, tag)

                            nade = NadeState(
                                base_id=int(eid),
                                nade_type=n_type,
                                x=float(s_row.x),
                                y=float(s_row.y),
                                z=float(s_row.z),
                                starting_tick=st,
                                ending_tick=et,
                                throw_tick=t_tick,
                                trajectory=(
                                    [t_pos, (float(s_row.x), float(s_row.y), float(s_row.z))]
                                    if t_pos
                                    else []
                                ),
                                thrower_id=sid if sid else None,
                                is_duration_estimated=duration_capped,  # DS-14
                            )
                            # Add to relevant ticks plus fade window
                            for t in range(t_tick or st, et + FADE_TICKS + 1):
                                if t not in nades_by_tick:
                                    nades_by_tick[t] = []
                                nades_by_tick[t].append(nade)
                else:
                    for ev_name in event_list:
                        df = data.get(ev_name, pd.DataFrame())
                        for row in df.itertuples():
                            # C-08: Guard against NULL entity_id in tick data
                            eid_raw = getattr(row, "entityid", None)
                            if eid_raw is None:
                                continue
                            st = int(row.tick)
                            et = st + (dur_ticks or MAX_NADE_DURATION)
                            if not dur_ticks:  # Used MAX_NADE_DURATION fallback
                                capped_count += 1
                            sid = int(getattr(row, "user_steamid", 0) or 0)
                            tag = "flash" if n_type == NadeType.FLASH else "grenade"
                            t_tick, t_pos = get_throw_data(st, sid, tag)
                            nade = NadeState(
                                base_id=int(eid_raw),
                                nade_type=n_type,
                                x=float(row.x),
                                y=float(row.y),
                                z=float(row.z),
                                starting_tick=st,
                                ending_tick=et,
                                throw_tick=t_tick,
                                trajectory=(
                                    [t_pos, (float(row.x), float(row.y), float(row.z))]
                                    if t_pos
                                    else []
                                ),
                                thrower_id=sid if sid else None,
                                is_duration_estimated=not bool(dur_ticks),  # DS-14
                            )
                            # Add to relevant ticks plus fade window
                            for t in range(t_tick or st, et + FADE_TICKS + 1):
                                if t not in nades_by_tick:
                                    nades_by_tick[t] = []
                                nades_by_tick[t].append(nade)

                # Log capped durations for transparency
                if capped_count > 0:
                    app_logger.warning(
                        "%s %s grenades had durations capped at MAX_NADE_DURATION (heuristic ceiling)",
                        capped_count,
                        n_type.name,
                    )

            except Exception as e:
                app_logger.error("Error parsing %s: %s", n_type, e)

        process_nades(
            ["smokegrenade_detonate", "smokegrenade_expired"], NadeType.SMOKE, is_start_end=True
        )
        process_nades(["inferno_startburn", "inferno_expire"], NadeType.MOLOTOV, is_start_end=True)
        process_nades(["flashbang_detonate"], NadeType.FLASH, dur_ticks=int(0.5 * tick_rate))
        process_nades(["hegrenade_detonate"], NadeType.HE, dur_ticks=int(0.5 * tick_rate))

        # --- 3. FULL EXTRACTION & MULTI-MAP SEGMENTATION ---
        app_logger.info("Pass 3 - Extracting full states & segmentation")
        fields = [
            "tick",
            "steamid",
            "name",
            "X",
            "Y",
            "Z",
            "yaw",
            "health",
            "armor_value",
            "is_alive",
            "team_name",
            "active_weapon_name",
            "flash_duration",
            "balance",
            "defuse_kit_owned",
            "kills_total",
            "deaths_total",
            "assists_total",
            "mvps",
            "is_crouching",
            "is_scoped",
            "equipment_value",
        ]

        round_starts = []
        try:
            res = parser.parse_events(["round_freeze_end"])
            if res:
                round_starts = sorted(res[0][1]["tick"].tolist())
        except Exception as e:
            app_logger.warning("Failed to parse round_freeze_end events: %s", e)

        # Detect Map Changes (via rounded start or gaps if map_name is unavailable per tick)
        # For now, we use the default map but structure it as a dict.
        # If demoparser2 allowed 'map_name' in parse_ticks, we'd use that.
        # But we can segment by 'Full Match' for the default map.

        rows_df = pd.DataFrame()
        try:
            rows_df = parser.parse_ticks(fields)
            app_logger.debug("DataFrame columns: %s", rows_df.columns.tolist())
            if not rows_df.empty:
                app_logger.debug("First row dict: %s", rows_df.iloc[0].to_dict())
        except Exception as e:
            app_logger.error("Error parsing ticks in Pass 3: %s", e)

        frames: List[DemoFrame] = []
        current_tick = -1
        current_players: List[PlayerState] = []

        # DS-06: Removed dead commented-out guard and debug-only logging.
        for row in rows_df.itertuples():
            t = int(getattr(row, "tick", 0))
            sid = int(getattr(row, "steamid", 0) or 0)
            if t != current_tick:
                if current_tick != -1:
                    r_idx = 1
                    for i, r_t in enumerate(round_starts):
                        if r_t <= current_tick:
                            r_idx = i + 1
                        else:
                            break
                    st_t = (
                        round_starts[r_idx - 1]
                        if (round_starts and r_idx <= len(round_starts))
                        else 0
                    )
                    frames.append(
                        DemoFrame(
                            tick=current_tick,
                            round_number=r_idx,
                            time_in_round=(current_tick - st_t) / tick_rate,
                            map_name=default_map,
                            players=current_players,
                            nades=nades_by_tick.get(current_tick, []),
                            bomb=None,
                        )
                    )
                current_tick = t
                current_players = []

            t_str = str(getattr(row, "team_name", "")).upper()
            team = Team.SPECTATOR
            if "CT" in t_str:
                team = Team.CT
            elif "TER" in t_str:
                team = Team.T

            # FIXED: hp should not default to 100 if 0 (dead)
            hp_val = int(getattr(row, "health", 0)) if hasattr(row, "health") else 100

            # H-03: Fetch money with fallback field names for demoparser2 compatibility
            money_val = 0
            for _money_field in ("balance", "cash", "money", "m_iAccount"):
                _raw = getattr(row, _money_field, None)
                if _raw is not None:
                    # R3-02: Use int(_raw) directly — `_raw or 0` incorrectly
                    # treated legitimate zero-money (eco round) as missing.
                    money_val = int(_raw)
                    break
            else:
                # R3-02: All money fields missing — log for data quality tracking
                app_logger.warning(
                    "No money field found for player at tick %d — defaulting to 0",
                    t,
                )

            # R3-H01: Populate inventory with the active weapon. demoparser2 does
            # not expose a full inventory list per tick, so active weapon only.
            active_weapon = str(getattr(row, "active_weapon_name", "None"))
            _inventory = [active_weapon] if active_weapon and active_weapon != "None" else []
            current_players.append(
                PlayerState(
                    player_id=sid,
                    name=str(getattr(row, "name", "Unknown")),
                    team=team,
                    x=float(getattr(row, "X", 0.0) or 0.0),
                    y=float(getattr(row, "Y", 0.0) or 0.0),
                    z=float(getattr(row, "Z", 0.0) or 0.0),
                    yaw=float(getattr(row, "yaw", 0.0) or 0.0),
                    hp=hp_val,
                    armor=int(getattr(row, "armor_value", 0) or 0),
                    is_alive=bool(getattr(row, "is_alive", False)),
                    is_flashed=float(getattr(row, "flash_duration", 0.0) or 0.0) > 0.5,
                    has_defuser=bool(getattr(row, "defuse_kit_owned", False)),
                    weapon=active_weapon,
                    is_crouching=bool(getattr(row, "is_crouching", False)),
                    is_scoped=bool(getattr(row, "is_scoped", False)),
                    equipment_value=int(getattr(row, "equipment_value", 0) or 0),
                    money=money_val,
                    kills=int(getattr(row, "kills_total", 0) or 0),
                    deaths=int(getattr(row, "deaths_total", 0) or 0),
                    assists=int(getattr(row, "assists_total", 0) or 0),
                    mvps=int(getattr(row, "mvps", 0) or 0),
                    inventory=_inventory,
                )
            )

        # --- APPEND LAST TICK ---
        if current_tick != -1:
            r_idx = 1
            for i, r_t in enumerate(round_starts):
                if r_t <= current_tick:
                    r_idx = i + 1
                else:
                    break
            st_t = round_starts[r_idx - 1] if (round_starts and r_idx <= len(round_starts)) else 0
            frames.append(
                DemoFrame(
                    tick=current_tick,
                    round_number=r_idx,
                    time_in_round=(current_tick - st_t) / tick_rate,
                    map_name=default_map,
                    players=current_players,
                    nades=nades_by_tick.get(current_tick, []),
                    bomb=None,
                )
            )

        # Resolving Kills
        app_logger.info("Resolving final game events")
        game_events = []
        try:
            res = parser.parse_events(["player_death"])
            if res:
                for row in res[0][1].itertuples():
                    t = int(row.tick)
                    # DS-09: Guard against None/NaN steamid from bot kills or warmup.
                    vic_id_raw = getattr(row, "user_steamid", None)
                    if vic_id_raw is None:
                        continue
                    try:
                        vic_id = int(vic_id_raw)
                    except (TypeError, ValueError):
                        continue
                    gx, gy = 0.0, 0.0
                    if t in pos_by_tick and vic_id in pos_by_tick[t]:
                        gx, gy, _ = pos_by_tick[t][vic_id]
                    game_events.append(
                        GameEvent(
                            tick=t,
                            event_type=EventType.KILL,
                            x=gx,
                            y=gy,
                            details=f"{getattr(row, 'attacker_name', '?')} -> {getattr(row, 'user_name', '?')}",
                        )
                    )
        except Exception as e:
            app_logger.warning("Failed to parse player_death events: %s", e)

        segments = {"Full Match": 0}
        if round_starts:
            for i, tick in enumerate(round_starts):
                r_num = i + 1
                if r_num == 1:
                    segments["First Half"] = tick
                elif r_num == 13:
                    segments["Second Half"] = tick
                elif r_num == 25:
                    segments["Overtime"] = tick

        result = {default_map: (frames, game_events, segments)}

        # --- 4. MAP TENSORS INJECTION ---
        try:
            map_tensors_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "map_tensors.json"
            )
            if os.path.exists(map_tensors_path):
                import json

                with open(map_tensors_path, "r") as f:
                    map_tensors = json.load(f)

                # Attach map-specific tensors if available
                if default_map in map_tensors:
                    app_logger.debug("Loaded map tensors for %s", default_map)
                    result["map_tensors"] = map_tensors[default_map]
                else:
                    app_logger.debug("No specific tensors found for %s", default_map)
            else:
                app_logger.debug("map_tensors.json not found")
        except Exception as e:
            app_logger.warning("Error loading map tensors: %s", e)

        app_logger.info("Finished parsing. Maps found: %s. Saving cache", list(result.keys()))
        _pickle_dump_signed(result, cache_path)
        return result
