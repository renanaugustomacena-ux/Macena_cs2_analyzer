import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
from Programma_CS2_RENAN.backend.nn.persistence import load_nn
from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAP_POSITION_SCALE
from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import FeatureExtractor
from Programma_CS2_RENAN.backend.processing.tensor_factory import get_tensor_factory
from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.nn.ghost_engine")


class GhostEngine:
    """
    Real-time Inference Engine for the RAP Coach (The 'Ghost').
    Translates raw game state (ticks) into optimal coaching suggestions.
    """

    def __init__(self, device: str = None):
        from Programma_CS2_RENAN.backend.nn.config import get_device

        self.device = device if device else str(get_device())
        self.model = None
        self.is_trained = False
        self._load_brain()

    def _load_brain(self):
        """Loads the verified RAP Coach model."""
        try:
            self.model = ModelFactory.get_model(ModelFactory.TYPE_RAP)

            try:
                ckpt_name = ModelFactory.get_checkpoint_name(ModelFactory.TYPE_RAP)
                load_nn(ckpt_name, self.model)
                self.is_trained = True
                app_logger.info("GhostEngine: Brain Loaded (%s).", ckpt_name)
            except Exception:
                app_logger.warning(
                    "GhostEngine: No trained checkpoint found. Predictions disabled until training completes."
                )
                self.model = None
                self.is_trained = False
                return

            self.model.to(self.device)
            self.model.eval()

        except Exception as e:
            app_logger.critical("GhostEngine Lobotomy: Failed to load model. %s", e)
            self.model = None
            self.is_trained = False

    def predict_tick(
        self,
        tick_data: Dict[str, Any],
        game_state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, float]:
        """Predict the OPTIMAL position (Ghost) for a given tick.

        Args:
            tick_data: Current tick state (dict or dataclass with pos_x, pos_y, yaw, etc.)
            game_state: Optional dict with Player-POV context for richer tensors.
                Keys: 'all_players' (list), 'events' (list), 'recent_history' (dict).
                When provided, builds PlayerKnowledge and generates real
                Player-POV tensors at full resolution instead of legacy zeros.

        Returns:
            (ghost_x, ghost_y) world coordinates.
        """
        if not self.model:
            app_logger.warning(
                "GhostEngine: predict_tick called but model is LOBOTOMIZED (no model loaded)"
            )
            return (0.0, 0.0)

        try:
            # 1. Prepare Tensors using TensorFactory (VISION BRIDGE - TASK 3.2)
            tensor_factory = get_tensor_factory()

            # Extract map name for spatial context
            if isinstance(tick_data, dict):
                map_name = tick_data.get("map_name", tick_data.get("map", None))
            else:
                map_name = getattr(tick_data, "map_name", getattr(tick_data, "map", None))
            if not map_name:
                app_logger.warning(
                    "GhostEngine: No map_name in tick data — cannot produce spatial prediction"
                )
                return (0.0, 0.0)

            # Build PlayerKnowledge when game_state is available
            knowledge = self._build_knowledge_from_game_state(tick_data, game_state)

            # A. Map Frame - tactical overlay (Player-POV when knowledge available)
            tick_list = [tick_data]
            map_t = (
                tensor_factory.generate_map_tensor(tick_list, map_name, knowledge=knowledge)
                .unsqueeze(0)
                .to(self.device)
            )

            # B. View Frame - FOV + visible entities + utility zones
            view_t = (
                tensor_factory.generate_view_tensor(tick_list, map_name, knowledge=knowledge)
                .unsqueeze(0)
                .to(self.device)
            )

            # C. Motion - trajectory + velocity + crosshair
            motion_t = (
                tensor_factory.generate_motion_tensor(tick_list, map_name)
                .unsqueeze(0)
                .to(self.device)
            )

            # D. Metadata - Use UNIFIED FeatureExtractor (Critical for consistency)
            # Build context dict for features 20-24 (available from live game state)
            context = {}
            if isinstance(tick_data, dict):
                context["time_in_round"] = tick_data.get("time_in_round", 0.0)
                context["bomb_planted"] = tick_data.get("bomb_planted", False)
                context["teammates_alive"] = tick_data.get("teammates_alive", 0)
                context["enemies_alive"] = tick_data.get("enemies_alive", 0)
                context["team_economy"] = tick_data.get("team_economy", 0)
            else:
                context["time_in_round"] = getattr(tick_data, "time_in_round", 0.0)
                context["bomb_planted"] = getattr(tick_data, "bomb_planted", False)
                context["teammates_alive"] = getattr(tick_data, "teammates_alive", 0)
                context["enemies_alive"] = getattr(tick_data, "enemies_alive", 0)
                context["team_economy"] = getattr(tick_data, "team_economy", 0)
            meta_vec = FeatureExtractor.extract(tick_data, map_name=map_name, context=context)
            meta_t = (
                torch.tensor(meta_vec, dtype=torch.float32)
                .unsqueeze(0)
                .unsqueeze(1)
                .to(self.device)
            )

            # 2. Inference
            with torch.no_grad():
                out = self.model(
                    view_frame=view_t, map_frame=map_t, motion_diff=motion_t, metadata=meta_t
                )

            # 3. Decode Output
            # Model output["optimal_pos"] is a delta [dx, dy] normalized
            optimal_delta = out["optimal_pos"].cpu().numpy()[0]  # [dx, dy]

            # Use the canonical scale factor shared with the overlay code (F3-05).
            # Key name resolution: DB models use pos_x/pos_y; dict frames may use
            # pos_x, X, or x — try pos_x first for consistency with FeatureExtractor. (F3-06)
            if isinstance(tick_data, dict):
                current_x = float(tick_data.get("pos_x", tick_data.get("X", tick_data.get("x", 0))))
                current_y = float(tick_data.get("pos_y", tick_data.get("Y", tick_data.get("y", 0))))
            else:
                current_x = float(getattr(tick_data, "pos_x", getattr(tick_data, "x", 0)))
                current_y = float(getattr(tick_data, "pos_y", getattr(tick_data, "y", 0)))

            ghost_x = current_x + (optimal_delta[0] * RAP_POSITION_SCALE)
            ghost_y = current_y + (optimal_delta[1] * RAP_POSITION_SCALE)

            return (ghost_x, ghost_y)

        except RuntimeError as e:
            app_logger.error("GhostEngine inference RuntimeError (CUDA/tensor): %s", e)
            return (0.0, 0.0)
        except Exception as e:
            app_logger.warning("GhostEngine inference failed: %s", e)
            return (0.0, 0.0)

    @staticmethod
    def _build_knowledge_from_game_state(tick_data, game_state):
        """Build PlayerKnowledge from game_state dict, if provided.

        Returns PlayerKnowledge or None (for legacy tensor fallback).
        """
        if game_state is None:
            return None

        try:
            from Programma_CS2_RENAN.backend.processing.player_knowledge import (
                PlayerKnowledgeBuilder,
            )

            all_players = game_state.get("all_players", [])
            events = game_state.get("events", [])
            recent_history = game_state.get("recent_history")

            if not all_players:
                return None

            kb = PlayerKnowledgeBuilder()
            return kb.build_knowledge(
                tick_data,
                all_players,
                recent_all_players_history=recent_history,
                active_events=events if events else None,
            )
        except Exception as e:
            app_logger.debug("PlayerKnowledge build failed, using legacy tensors: %s", e)
            return None
