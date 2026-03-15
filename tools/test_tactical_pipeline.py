#!/usr/bin/env python3
"""
Headless end-to-end test of the tactical viewer pipeline.

Loads a real .dem file through every stage the Qt tactical viewer uses,
catches ALL errors instead of crashing on the first one, and reports
a full summary at the end.

Usage:
    python tools/test_tactical_pipeline.py [path_to.dem]

If no path is given, uses the first .dem found in DEMO_PRO_PLAYERS/.
"""

import os
import sys
import time
import traceback

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# ── Add project root to path ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

ERRORS: list[tuple[str, str]] = []
WARNINGS: list[str] = []
PASSES: list[str] = []


def record_pass(label: str):
    PASSES.append(label)
    print(f"  [PASS] {label}")


def record_error(label: str, exc: Exception | str):
    tb = traceback.format_exc() if isinstance(exc, Exception) else str(exc)
    ERRORS.append((label, tb))
    print(f"  [FAIL] {label}: {exc}")


def record_warn(label: str, msg: str):
    WARNINGS.append(f"{label}: {msg}")
    print(f"  [WARN] {label}: {msg}")


def find_demo() -> str:
    """Find a .dem file to test with."""
    demo_dir = os.path.join(
        os.path.dirname(PROJECT_ROOT), "DEMO_PRO_PLAYERS"
    )
    if os.path.isdir(demo_dir):
        for f in sorted(os.listdir(demo_dir)):
            if f.endswith(".dem"):
                return os.path.join(demo_dir, f)
    return ""


def main():
    print("=" * 70)
    print("TACTICAL VIEWER PIPELINE — HEADLESS END-TO-END TEST")
    print("=" * 70)

    # ── Resolve demo path ──
    demo_path = sys.argv[1] if len(sys.argv) > 1 else find_demo()
    if not demo_path or not os.path.isfile(demo_path):
        print(f"ERROR: No .dem file found. Pass a path as argument.")
        sys.exit(1)

    print(f"\nDemo: {os.path.basename(demo_path)}")
    print(f"Size: {os.path.getsize(demo_path) / 1e6:.1f} MB\n")

    # ══════════════════════════════════════════════════════════════
    # STAGE 1: DemoLoader.load_demo()
    # ══════════════════════════════════════════════════════════════
    print("[Stage 1] DemoLoader.load_demo()")
    raw_data = None
    t0 = time.time()
    try:
        from Programma_CS2_RENAN.ingestion.demo_loader import DemoLoader
        loader = DemoLoader()
        raw_data = loader.load_demo(demo_path)
        elapsed = time.time() - t0
        record_pass(f"load_demo completed in {elapsed:.1f}s")
    except Exception as e:
        record_error("load_demo", e)
        print("\n*** Cannot proceed without demo data. ***")
        _print_summary()
        sys.exit(1)

    # ── Check returned structure ──
    print("\n[Stage 2] Validate DemoLoader output structure")
    if not isinstance(raw_data, dict):
        record_error("output type", f"Expected dict, got {type(raw_data)}")
        _print_summary()
        sys.exit(1)
    record_pass(f"output is dict with {len(raw_data)} keys: {list(raw_data.keys())}")

    # ── Filter map_tensors (as the real code does) ──
    map_data = {
        k: v for k, v in raw_data.items()
        if isinstance(v, tuple) and len(v) == 3
    }
    non_map_keys = [k for k in raw_data if k not in map_data]
    if non_map_keys:
        record_warn("non-map keys filtered", str(non_map_keys))
    if not map_data:
        record_error("no map data", "All keys filtered out — no valid (frames, events, segments) tuples")
        _print_summary()
        sys.exit(1)
    record_pass(f"{len(map_data)} map(s) after filtering: {list(map_data.keys())}")

    # ══════════════════════════════════════════════════════════════
    # STAGE 3: Validate each map's data
    # ══════════════════════════════════════════════════════════════
    for map_name, (frames, events, segments) in map_data.items():
        print(f"\n[Stage 3] Validate map: {map_name}")
        print(f"  Frames: {len(frames)}, Events: {len(events)}, Segments: {len(segments)}")

        # ── Frames ──
        try:
            from Programma_CS2_RENAN.core.demo_frame import DemoFrame
            assert len(frames) > 0, "No frames"
            assert isinstance(frames[0], DemoFrame), f"First frame is {type(frames[0])}, not DemoFrame"
            record_pass(f"frames: {len(frames)} DemoFrame objects, ticks {frames[0].tick}..{frames[-1].tick}")
        except Exception as e:
            record_error(f"{map_name} frames", e)

        # ── Events ──
        try:
            from Programma_CS2_RENAN.core.demo_frame import GameEvent
            for i, ev in enumerate(events[:5]):
                assert isinstance(ev, GameEvent), f"Event {i} is {type(ev)}"
            record_pass(f"events: {len(events)} GameEvent objects")
        except Exception as e:
            record_error(f"{map_name} events", e)

        # ── Segments ──
        try:
            assert isinstance(segments, dict), f"Segments is {type(segments)}"
            for k, v in list(segments.items())[:3]:
                assert isinstance(v, int), f"Segment '{k}' tick is {type(v)}, not int"
            record_pass(f"segments: {len(segments)} rounds")
        except Exception as e:
            record_error(f"{map_name} segments", e)

        # ── Player data completeness ──
        print(f"\n[Stage 4] Player field access test ({map_name})")
        sample_frames = [frames[0], frames[len(frames) // 2], frames[-1]]
        player_fields = [
            "player_id", "name", "team", "x", "y", "z", "yaw",
            "hp", "armor", "is_alive", "is_flashed", "weapon",
            "money", "kills", "deaths", "assists", "mvps",
            "inventory", "is_crouching", "is_scoped", "equipment_value",
        ]
        field_errors = []
        for fi, frame in enumerate(sample_frames):
            for pi, player in enumerate(frame.players):
                for field_name in player_fields:
                    try:
                        val = getattr(player, field_name)
                        # Check types that would crash Qt widgets
                        if field_name == "weapon" and val is None:
                            field_errors.append(f"frame[{fi}].player[{pi}].weapon is None")
                        if field_name == "name" and val is None:
                            field_errors.append(f"frame[{fi}].player[{pi}].name is None")
                    except AttributeError:
                        field_errors.append(f"frame[{fi}].player[{pi}] missing '{field_name}'")
        if field_errors:
            for fe in field_errors:
                record_error("player field", fe)
        else:
            record_pass(f"all {len(player_fields)} player fields accessible on {len(sample_frames)*10} samples")

        # ── Nade data completeness ──
        print(f"\n[Stage 5] Grenade field access test ({map_name})")
        nade_fields = [
            "base_id", "nade_type", "x", "y", "z",
            "starting_tick", "ending_tick", "throw_tick", "trajectory",
        ]
        total_nades = 0
        nade_errors = []
        nade_type_counts = {}
        for frame in sample_frames:
            for nade in frame.nades:
                total_nades += 1
                nt = getattr(nade, "nade_type", None)
                nade_type_counts[str(nt)] = nade_type_counts.get(str(nt), 0) + 1
                for field_name in nade_fields:
                    try:
                        getattr(nade, field_name)
                    except AttributeError:
                        nade_errors.append(f"nade missing '{field_name}'")
        if nade_errors:
            for ne in nade_errors:
                record_error("nade field", ne)
        else:
            record_pass(f"all nade fields accessible ({total_nades} nades in samples, types: {nade_type_counts})")

        # ══════════════════════════════════════════════════════════
        # STAGE 6: PlaybackEngine — load + interpolate
        # ══════════════════════════════════════════════════════════
        print(f"\n[Stage 6] PlaybackEngine interpolation ({map_name})")
        try:
            from Programma_CS2_RENAN.core.playback_engine import PlaybackEngine, InterpolatedFrame

            engine = PlaybackEngine()
            engine.load_frames(frames)

            received_frames: list[InterpolatedFrame] = []
            engine.set_on_frame_update(lambda f: received_frames.append(f))

            # Simulate seeking to several points
            test_ticks = [0, frames[len(frames) // 4].tick, frames[len(frames) // 2].tick, frames[-1].tick]
            for tick in test_ticks:
                engine.seek_to_tick(tick)

            assert len(received_frames) == len(test_ticks), (
                f"Expected {len(test_ticks)} frames, got {len(received_frames)}"
            )
            record_pass(f"seek + emit works for {len(test_ticks)} test points")

            # Validate InterpolatedFrame structure
            for iframe in received_frames:
                assert hasattr(iframe, "tick"), "InterpolatedFrame missing 'tick'"
                assert hasattr(iframe, "players"), "InterpolatedFrame missing 'players'"
                assert hasattr(iframe, "nades"), "InterpolatedFrame missing 'nades'"
            record_pass("InterpolatedFrame structure valid")

            # Test interpolation (simulate one tick advance)
            engine.seek_to_tick(frames[100].tick if len(frames) > 100 else frames[0].tick)
            received_frames.clear()
            engine._sub_tick = 0.5  # Force mid-frame interpolation
            engine._emit_frame()
            if received_frames:
                iframe = received_frames[0]
                for p in iframe.players:
                    # Access every field the map widget uses
                    _ = p.x, p.y, p.yaw, p.hp, p.is_alive, p.team, p.name
                    _ = p.is_ghost
                record_pass(f"interpolated frame: {len(iframe.players)} players, {len(iframe.nades)} nades")
            else:
                record_error("interpolation", "No frame emitted after _emit_frame()")

        except Exception as e:
            record_error("PlaybackEngine", e)

        # ══════════════════════════════════════════════════════════
        # STAGE 7: SpatialEngine coordinate transform
        # ══════════════════════════════════════════════════════════
        print(f"\n[Stage 7] SpatialEngine coordinate transform ({map_name})")
        try:
            from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine
            from Programma_CS2_RENAN.core.spatial_data import get_map_metadata

            meta = get_map_metadata(map_name)
            if meta is None:
                record_warn("spatial", f"No MapMetadata for '{map_name}' — map will render without background")
            else:
                record_pass(f"MapMetadata found: pos=({meta.pos_x}, {meta.pos_y}), scale={meta.scale}")

                # Transform a sample of player positions
                test_players = frames[len(frames) // 2].players[:3]
                coord_issues = []
                for p in test_players:
                    nx, ny = SpatialEngine.world_to_normalized(p.x, p.y, map_name)
                    if not (0.0 <= nx <= 1.0):
                        coord_issues.append(f"{p.name} nx={nx:.3f} out of [0,1]")
                    if not (0.0 <= ny <= 1.0):
                        coord_issues.append(f"{p.name} ny={ny:.3f} out of [0,1]")

                if coord_issues:
                    for ci in coord_issues:
                        record_warn("coord range", ci)
                else:
                    record_pass(f"all {len(test_players)} sample positions in [0,1] range")

        except Exception as e:
            record_error("SpatialEngine", e)

        # ══════════════════════════════════════════════════════════
        # STAGE 8: Map image resolution
        # ══════════════════════════════════════════════════════════
        print(f"\n[Stage 8] Map image resolution ({map_name})")
        try:
            from Programma_CS2_RENAN.core.config import get_resource_path
            clean = map_name.lower().strip().replace(".dem", "").replace(".vpk", "").replace("maps/", "")
            maps_dir = get_resource_path(os.path.join("PHOTO_GUI", "maps"))
            found_image = None
            for candidate in [clean, f"de_{clean}"]:
                path = os.path.join(maps_dir, f"{candidate}.png")
                if os.path.exists(path):
                    found_image = path
                    break
            if not found_image and os.path.isdir(maps_dir):
                for fname in os.listdir(maps_dir):
                    if clean in fname and fname.endswith(".png"):
                        found_image = os.path.join(maps_dir, fname)
                        break
            if found_image:
                sz = os.path.getsize(found_image)
                record_pass(f"map image found: {os.path.basename(found_image)} ({sz / 1024:.0f} KB)")
            else:
                record_warn("map image", f"No PNG found for '{clean}' in {maps_dir}")
        except Exception as e:
            record_error("map image", e)

        # ══════════════════════════════════════════════════════════
        # STAGE 9: Simulate map_widget rendering calls (no Qt)
        # ══════════════════════════════════════════════════════════
        print(f"\n[Stage 9] Simulate rendering calls ({map_name})")
        try:
            from Programma_CS2_RENAN.core.playback_engine import InterpolatedPlayerState
            from Programma_CS2_RENAN.core.demo_frame import NadeType, Team

            # Simulate _world_to_screen for players
            if meta:
                render_errors = []
                test_frame = frames[len(frames) // 2]
                for p in test_frame.players:
                    try:
                        nx, ny = SpatialEngine.world_to_normalized(p.x, p.y, map_name)
                        # Simulate _world_to_screen with a 600px viewport
                        ms = 600
                        sx, sy = nx * ms, ny * ms
                        # Simulate team check (as map_widget does)
                        is_ct = p.team == Team.CT if isinstance(p.team, Team) else "CT" in str(p.team).upper()
                        # Simulate FoV rotation calc
                        rotation = 90 - p.yaw
                    except Exception as e:
                        render_errors.append(f"player {p.name}: {e}")

                for nade in test_frame.nades:
                    try:
                        nx, ny = SpatialEngine.world_to_normalized(nade.x, nade.y, map_name)
                        sx, sy = nx * ms, ny * ms
                        # Check nade_type is valid NadeType
                        _ = nade.nade_type in (NadeType.SMOKE, NadeType.MOLOTOV, NadeType.FLASH, NadeType.HE)
                        # Check trajectory access
                        if nade.trajectory:
                            for pt in nade.trajectory[:3]:
                                assert len(pt) == 3, f"Trajectory point has {len(pt)} coords, not 3"
                    except Exception as e:
                        render_errors.append(f"nade {nade.base_id}: {e}")

                if render_errors:
                    for re_err in render_errors:
                        record_error("render sim", re_err)
                else:
                    record_pass(
                        f"all {len(test_frame.players)} players + "
                        f"{len(test_frame.nades)} nades render-simulated OK"
                    )
            else:
                record_warn("render sim", "Skipped — no MapMetadata")

        except Exception as e:
            record_error("render simulation", e)

    # ══════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════
    _print_summary()


def _print_summary():
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  PASSED:   {len(PASSES)}")
    print(f"  WARNINGS: {len(WARNINGS)}")
    print(f"  ERRORS:   {len(ERRORS)}")

    if WARNINGS:
        print("\nWarnings:")
        for w in WARNINGS:
            print(f"  ⚠ {w}")

    if ERRORS:
        print("\nErrors:")
        for label, tb in ERRORS:
            print(f"\n  ✗ {label}")
            for line in tb.strip().split("\n"):
                print(f"    {line}")
        print(f"\n{'=' * 70}")
        print("VERDICT: FAIL")
        print(f"{'=' * 70}")
        sys.exit(1)
    else:
        print(f"\n{'=' * 70}")
        print("VERDICT: PASS — Pipeline is ready for live rendering")
        print(f"{'=' * 70}")
        sys.exit(0)


if __name__ == "__main__":
    main()
