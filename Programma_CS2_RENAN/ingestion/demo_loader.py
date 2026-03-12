import hashlib
import hmac
import os
import pickle
from typing import Dict, List, Tuple

import numpy as np
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

    try:
        from Programma_CS2_RENAN.core.config import DATA_DIR as _DATA_DIR
        CACHE_DIR = os.path.join(_DATA_DIR, "demo_cache")
    except ImportError:
        CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
    CACHE_VERSION = "v21_vectorized_parse"  # D-26: groupby + pre-vectorized columns

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

        # D-26: Pre-vectorize columns to minimize per-row Python overhead.
        # Iterates ~172K tick groups instead of ~1.7M individual rows.
        frames: List[DemoFrame] = []

        if not rows_df.empty:
            # --- Money: coalesce across demoparser2 field name variants (H-03) ---
            _money_series = pd.Series(np.nan, index=rows_df.index)
            _found_money_col = False
            for _mf in ("balance", "cash", "money", "m_iAccount"):
                if _mf in rows_df.columns:
                    _money_series = _money_series.fillna(rows_df[_mf])
                    _found_money_col = True
            if not _found_money_col:
                # R3-02: No money column at all — log once instead of per-row
                app_logger.warning(
                    "R3-02: No money column found in parsed data — all money values default to 0"
                )
            rows_df["money_resolved"] = _money_series.fillna(0).astype(int)

            # --- Team: vectorized string classification ---
            _tu = rows_df["team_name"].fillna("").astype(str).str.upper()
            rows_df["team_resolved"] = np.where(
                _tu.str.contains("CT", na=False), "CT",
                np.where(_tu.str.contains("TER", na=False), "T", "SPEC"),
            )

            # --- Round index: O(n log m) via searchsorted (replaces O(n*m) linear scan) ---
            if round_starts:
                _rs_arr = np.array(round_starts)
                rows_df["round_resolved"] = np.clip(
                    np.searchsorted(_rs_arr, rows_df["tick"].values, side="right"),
                    1, len(_rs_arr),
                )
            else:
                rows_df["round_resolved"] = 1

            # --- NaN-safe numeric fills (one vectorized pass instead of per-row getattr) ---
            _fill_map = {
                "X": 0.0, "Y": 0.0, "Z": 0.0, "yaw": 0.0,
                "armor_value": 0, "flash_duration": 0.0,
                "equipment_value": 0, "kills_total": 0, "deaths_total": 0,
                "assists_total": 0, "mvps": 0,
            }
            for _col, _default in _fill_map.items():
                if _col in rows_df.columns:
                    rows_df[_col] = rows_df[_col].fillna(_default)

            # Health: NaN → 0 if column exists, else default 100 (column missing entirely)
            if "health" in rows_df.columns:
                rows_df["health"] = rows_df["health"].fillna(0)
            else:
                rows_df["health"] = 100

            _rs_list = round_starts if round_starts else []
            _team_map = {"CT": Team.CT, "T": Team.T, "SPEC": Team.SPECTATOR}

            for tick_val, group in rows_df.groupby("tick", sort=True):
                tick_int = int(tick_val)
                r_idx = int(group.iloc[0]["round_resolved"])
                st_t = _rs_list[r_idx - 1] if (_rs_list and r_idx <= len(_rs_list)) else 0

                players = []
                for row in group.itertuples():
                    sid = int(getattr(row, "steamid", 0) or 0)
                    team = _team_map.get(row.team_resolved, Team.SPECTATOR)

                    hp_val = int(row.health)

                    # R3-H01: active weapon only (demoparser2 limitation)
                    active_weapon = str(getattr(row, "active_weapon_name", "None"))
                    _inventory = (
                        [active_weapon] if active_weapon and active_weapon != "None" else []
                    )

                    players.append(
                        PlayerState(
                            player_id=sid,
                            name=str(getattr(row, "name", "Unknown")),
                            team=team,
                            x=float(row.X),
                            y=float(row.Y),
                            z=float(row.Z),
                            yaw=float(row.yaw),
                            hp=hp_val,
                            armor=int(row.armor_value),
                            is_alive=bool(getattr(row, "is_alive", False)),
                            is_flashed=float(row.flash_duration) > 0.5,
                            has_defuser=bool(getattr(row, "defuse_kit_owned", False)),
                            weapon=active_weapon,
                            is_crouching=bool(getattr(row, "is_crouching", False)),
                            is_scoped=bool(getattr(row, "is_scoped", False)),
                            equipment_value=int(row.equipment_value),
                            money=int(row.money_resolved),
                            kills=int(row.kills_total),
                            deaths=int(row.deaths_total),
                            assists=int(row.assists_total),
                            mvps=int(row.mvps),
                            inventory=_inventory,
                        )
                    )

                frames.append(
                    DemoFrame(
                        tick=tick_int,
                        round_number=r_idx,
                        time_in_round=(tick_int - st_t) / tick_rate,
                        map_name=default_map,
                        players=players,
                        nades=nades_by_tick.get(tick_int, []),
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
