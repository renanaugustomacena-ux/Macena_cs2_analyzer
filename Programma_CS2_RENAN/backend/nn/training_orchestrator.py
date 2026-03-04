import numpy as np
import torch

from Programma_CS2_RENAN.backend.nn.config import get_device
from Programma_CS2_RENAN.backend.nn.persistence import StaleCheckpointError, load_nn, save_nn
from Programma_CS2_RENAN.backend.nn.training_callbacks import CallbackRegistry
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.orchestrator")


class TrainingOrchestrator:
    """
    Unified Orchestrator for managing the details of the training lifecycle.
    Implements:
    - Epoch Loop
    - Validation frequency
    - Early Stopping
    - Checkpointing (Best/Latest)
    - Learning Rate Scheduling
    - Real-time Progress Reporting
    """

    def __init__(
        self,
        manager,
        model_type="jepa",
        max_epochs=100,
        patience=10,
        batch_size=32,
        callbacks: CallbackRegistry = None,
    ):
        self.manager = manager
        self.model_type = model_type
        self.max_epochs = max_epochs
        self.patience = patience
        self.batch_size = batch_size
        self.device = get_device()
        self.best_val_loss = float("inf")
        self.patience_counter = 0
        self.callbacks = callbacks or CallbackRegistry()
        # Deterministic RNG for JEPA negative sampling (F3-02).
        # Seeded once at construction so training runs are reproducible.
        self._neg_rng = np.random.default_rng(seed=42)

        # Determine internal model/trainer classes based on type
        if model_type in ("jepa", "vl-jepa"):
            from Programma_CS2_RENAN.backend.nn.jepa_trainer import JEPATrainer

            self.TrainerClass = JEPATrainer
            self.model_name = "vl_jepa_brain" if model_type == "vl-jepa" else "jepa_brain"
            self.learning_rate = 1e-4
            self._use_vl = model_type == "vl-jepa"

        elif model_type == "rap":
            from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

            self.TrainerClass = RAPTrainer
            self.model_name = "rap_coach"
            self.learning_rate = 5e-5
            self._use_vl = False
        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def run_training(self, context=None):
        """Execute the full training pipeline."""
        logger.info("Orchestrator Starting: %s Cycle", self.model_name.upper())

        # 1. Initialize Model via Factory
        # This unifies instantiation logic with Inference Engine
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        # Mapping generic orchestrator type to Factory constants if needed,
        # but they seem to match ("jepa", "rap").
        # If model_type is 'rap', we assume it's ModelFactory.TYPE_RAP.

        model = ModelFactory.get_model(self.model_type).to(self.device)
        try:
            # Try loading existing checkpoint to resume
            load_nn(self.model_name, model)
            logger.info("Resumed training from %s", self.model_name)
        except FileNotFoundError:
            logger.info("No checkpoint found — starting fresh training for %s", self.model_name)
        except StaleCheckpointError:
            logger.warning(
                "Stale checkpoint for %s — architecture changed. Starting fresh training.",
                self.model_name,
            )
        except Exception as e:
            logger.warning(
                "Checkpoint load failed for %s (possible corruption): %s. Starting fresh.",
                self.model_name,
                e,
            )

        trainer = self.TrainerClass(model, lr=self.learning_rate)

        # 2. Prepare Data
        # Phase 5.2 Alignment: Using standardized fetching with splits
        train_data = self._fetch_batches(is_train=True)
        val_data = self._fetch_batches(is_train=False)

        if not train_data:
            logger.warning("Training Aborted: Insufficient Training Data")
            return

        logger.info(
            "Training on %s samples, Validating on %s",
            len(train_data) * self.batch_size,
            len(val_data) * self.batch_size if val_data else 0,
        )

        # Fire: on_train_start
        self.callbacks.fire(
            "on_train_start",
            model=model,
            config={
                "model_type": self.model_type,
                "max_epochs": self.max_epochs,
                "batch_size": self.batch_size,
                "lr": self.learning_rate,
            },
        )

        # 3. Epoch Loop
        for epoch in range(1, self.max_epochs + 1):
            if context:
                context.check_state()

            # Fire: on_epoch_start
            self.callbacks.fire("on_epoch_start", epoch=epoch)

            # A. Train
            train_loss = self._run_epoch(trainer, train_data, is_train=True, context=context)

            # B. Validate
            val_loss = 0.0
            if val_data:
                val_loss = self._run_epoch(trainer, val_data, is_train=False, context=context)
            else:
                val_loss = train_loss  # Fallback if no val data

            # C. Scheduler Step (if trainer has one)
            if hasattr(trainer, "scheduler"):
                # Note: JEPATrainer steps per batch, but we can also step per epoch if configured
                pass

            # D. Logging & Reporting
            self._report_progress(epoch, train_loss, val_loss)

            # Fire: on_epoch_end
            self.callbacks.fire(
                "on_epoch_end",
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_loss,
                model=model,
                optimizer=trainer.optimizer if hasattr(trainer, "optimizer") else None,
            )

            # E. Checkpointing & Early Stopping
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.patience_counter = 0
                save_nn(model, self.model_name, user_id=None)  # Save BEST
                logger.info("New Best Model Saved (Val Loss: %s)", format(val_loss, ".6f"))
            else:
                self.patience_counter += 1

            # Save LATEST checkpoint regardless
            save_nn(model, f"{self.model_name}_latest", user_id=None)

            if self.patience_counter >= self.patience:
                logger.info("Early Stopping Triggered at Epoch %s", epoch)
                break

        # Fire: on_train_end
        self.callbacks.fire(
            "on_train_end",
            model=model,
            final_metrics={
                "best_val_loss": self.best_val_loss,
                "final_epoch": epoch,
                "model_type": self.model_type,
            },
        )

        logger.info("Training Cycle Complete.")

    def _fetch_batches(self, is_train=True):
        """Fetch and batch data from Manager."""
        # Use manager's fetch logic (which now respects splits)
        # For JEPA, use _fetch_jepa_ticks
        # For RAP, use generic _fetch_training_data (needs updating to ticks likely)

        split = "train" if is_train else "val"
        is_pro = True  # Start with Pro baseline by default

        raw_items = []
        if self.model_type in ("jepa", "vl-jepa"):
            raw_items = self.manager._fetch_jepa_ticks(is_pro=is_pro, split=split)
        else:
            # RAP data loading reuses JEPA tick fetcher (stub — Bug #5).
            # RAP-specific data pipeline (windowed ticks) not yet implemented.
            logger.warning(
                "RAP data loading reuses JEPA tick fetcher (stub). "
                "RAP-specific data pipeline not yet implemented."
            )
            raw_items = self.manager._fetch_jepa_ticks(is_pro=is_pro, split=split)

        if not raw_items:
            return []

        # Temporal ordering preserved — no shuffle for sequence models (JEPA/RAP)

        batches = []
        for i in range(0, len(raw_items), self.batch_size):
            batch = raw_items[i : i + self.batch_size]
            batches.append(batch)

        return batches

    def _run_epoch(self, trainer, batches, is_train=True, context=None):
        """Run a single epoch (Train or Eval)."""
        total_loss = 0.0

        if is_train:
            trainer.model.train()
        else:
            trainer.model.eval()

        for batch_idx, batch in enumerate(batches):
            if context:
                context.check_state()

            # Convert raw DB objects to Tensors
            tensor_batch = self._prepare_tensor_batch(batch)
            if tensor_batch is None:
                continue  # Skip empty batches

            if is_train:
                # Trainer handles zero_grad, backward, optimizer
                if self.model_type in ("jepa", "vl-jepa"):
                    # JEPA signature: context, target, negatives
                    if self._use_vl:
                        result = trainer.train_step_vl(
                            tensor_batch["context"],
                            tensor_batch["target"],
                            tensor_batch.get("negatives"),
                            round_stats=tensor_batch.get("round_stats"),
                        )
                        loss = result["total_loss"]
                    else:
                        result = trainer.train_step(
                            tensor_batch["context"],
                            tensor_batch["target"],
                            tensor_batch.get("negatives"),
                        )
                        loss = result["loss"] if isinstance(result, dict) else result
                else:
                    # RAP signature: batch dict directly — returns dict with "loss" key
                    try:
                        result = trainer.train_step(tensor_batch)
                        loss = result["loss"] if isinstance(result, dict) else result
                    except (KeyError, TypeError) as e:
                        logger.warning("RAP train_step failed (missing tensor key): %s", e)
                        continue

                # Fire: on_batch_end (training batches only)
                batch_outputs = result if isinstance(result, dict) else {"loss": float(loss)}
                self.callbacks.fire(
                    "on_batch_end",
                    batch_idx=batch_idx,
                    loss=float(loss),
                    outputs=batch_outputs,
                )
            else:
                # Validation (No Grad)
                with torch.no_grad():
                    if self.model_type in ("jepa", "vl-jepa"):
                        # For validation, just compute loss without backward
                        pred, target = trainer.model.forward_jepa_pretrain(
                            tensor_batch["context"], tensor_batch["target"]
                        )
                        from Programma_CS2_RENAN.backend.nn.jepa_model import jepa_contrastive_loss

                        # Encode negatives into latent space (same as pred/target)
                        # Expected shape: raw_neg [batch, n_neg, feat_dim]
                        # Must produce neg_latent [batch, n_neg, latent_dim] for contrastive loss
                        raw_neg = tensor_batch.get("negatives")
                        b, n_neg, feat_dim = raw_neg.shape
                        # Flatten batch*n_neg, encode, then reshape back
                        raw_neg_flat = raw_neg.reshape(b * n_neg, feat_dim)
                        neg_encoded_flat = trainer.model.target_encoder(raw_neg_flat)
                        latent_dim = neg_encoded_flat.shape[-1]
                        neg_latent = neg_encoded_flat.reshape(b, n_neg, latent_dim)

                        loss = jepa_contrastive_loss(pred, target, neg_latent).item()
                    else:
                        # RAP validation (Bug #5: guard against missing tensor keys)
                        try:
                            outputs = trainer.model(
                                tensor_batch["view"],
                                tensor_batch["map"],
                                tensor_batch["motion"],
                                tensor_batch["metadata"],
                            )
                            loss = trainer.criterion_val(
                                outputs["value_estimate"], tensor_batch["target_val"]
                            ).item()
                        except (KeyError, TypeError) as e:
                            logger.warning("RAP validation failed (missing tensor key): %s", e)
                            continue

            total_loss += loss

        return total_loss / max(len(batches), 1)

    def _prepare_tensor_batch(self, raw_items):
        """Convert list of DB objects (PlayerTickState) to Tensor Dictionary.

        Uses the unified FeatureExtractor to ensure consistency between training and inference.
        For RAP model: builds real Player-POV tensors from per-match databases when available,
        with graceful fallback to legacy zero-init when match DB is unavailable.
        """
        import numpy as np

        from Programma_CS2_RENAN.backend.processing.feature_engineering import (
            METADATA_DIM,
            FeatureExtractor,
        )

        b = len(raw_items)
        if b == 0:
            # CRITICAL: Never train on all-zero tensors — return None to signal skip
            logger.warning("Empty batch encountered — skipping (refusing to train on zeros)")
            return None

        # Extract features using the unified FeatureExtractor
        features = FeatureExtractor.extract_batch(raw_items)  # Shape: (b, METADATA_DIM)
        features_tensor = torch.tensor(features, dtype=torch.float32).to(self.device)

        if self.model_type in ("jepa", "vl-jepa"):
            # JEPA expects context (sequence), target, and negatives
            # Context: use sliding window of features
            context_len = min(10, b)
            context = features_tensor[:context_len].unsqueeze(0)  # (1, context_len, METADATA_DIM)
            # Pad to 10 if needed
            if context.shape[1] < 10:
                padding = torch.zeros(1, 10 - context.shape[1], METADATA_DIM).to(self.device)
                context = torch.cat([context, padding], dim=1)

            # Target: next item prediction (or last item if at end)
            target = features_tensor[-1:].mean(dim=0, keepdim=True)  # (1, METADATA_DIM)

            # Negatives: random samples from batch — require at least 5 real samples
            if b >= 5:
                neg_indices = self._neg_rng.choice(b, 5, replace=False)
                negatives = features_tensor[neg_indices].unsqueeze(0)  # (1, 5, METADATA_DIM)
            else:
                logger.debug(
                    "JEPA batch too small for contrastive negatives (%d < 5) — skipping batch", b
                )
                return None

            result = {"context": context, "target": target, "negatives": negatives}

            # G-01: For VL-JEPA, fetch RoundStats to provide outcome-based concept labels
            # (eliminates label leakage from heuristic labeling)
            if self._use_vl:
                round_stats = self._fetch_round_stats_for_batch(raw_items[:context_len])
                if round_stats is not None:
                    result["round_stats"] = round_stats

            return result
        else:
            return self._prepare_rap_batch(raw_items, features, features_tensor, b)

    def _prepare_rap_batch(self, raw_items, _features, features_tensor, b):
        """Build RAP tensor batch with real Player-POV tensors.

        For each sample, attempts to:
        1. Resolve the per-match DB from match_id
        2. Query all players at tick + recent history + events
        3. Build PlayerKnowledge (NO-WALLHACK sensorial model)
        4. Generate real map/view/motion tensors at 64x64 training resolution

        Falls back to legacy zero-init per-sample when match DB is unavailable.
        """
        from Programma_CS2_RENAN.backend.processing.player_knowledge import PlayerKnowledgeBuilder
        from Programma_CS2_RENAN.backend.processing.tensor_factory import (
            TensorFactory,
            TrainingTensorConfig,
        )

        tf = TensorFactory(TrainingTensorConfig())
        kb = PlayerKnowledgeBuilder()
        match_mgr = self._get_match_manager()

        metadata = features_tensor
        view_list = []
        map_list = []
        motion_list = []
        target_val_list = []
        target_strat_list = []

        # Per-batch caches to avoid re-querying same match/tick
        _all_players_cache: dict = {}
        _window_cache: dict = {}
        _event_cache: dict = {}
        _metadata_cache: dict = {}
        pov_count = 0

        for i, item in enumerate(raw_items):
            match_id = getattr(item, "match_id", None)
            tick = int(getattr(item, "tick", 0))
            player_name = str(getattr(item, "player_name", ""))
            demo_name = str(getattr(item, "demo_name", ""))

            # Resolve map name (from match metadata or demo_name pattern)
            map_name = self._resolve_map_name(match_id, demo_name, match_mgr, _metadata_cache)

            knowledge = None
            tick_list = [item]

            if match_id is not None and match_mgr is not None:
                try:
                    knowledge, tick_list = self._build_sample_knowledge(
                        match_id,
                        tick,
                        player_name,
                        item,
                        match_mgr,
                        kb,
                        _all_players_cache,
                        _window_cache,
                        _event_cache,
                    )
                    if knowledge is not None:
                        pov_count += 1
                except Exception as e:
                    logger.debug(
                        "Match DB unavailable for match_id=%s tick=%s: %s",
                        match_id,
                        tick,
                        e,
                    )

            # Generate tensors (real POV or legacy zero-fallback)
            map_t = tf.generate_map_tensor(tick_list, map_name, knowledge=knowledge)
            view_t = tf.generate_view_tensor(tick_list, map_name, knowledge=knowledge)
            motion_t = tf.generate_motion_tensor(tick_list, map_name)

            map_list.append(map_t)
            view_list.append(view_t)
            motion_list.append(motion_t)

            # --- Targets ---
            # Advantage function (continuous [0, 1]) when per-match data available
            all_players = _all_players_cache.get((match_id, tick), [])
            if all_players and knowledge is not None:
                val = self._compute_advantage(
                    all_players,
                    str(getattr(item, "team", "CT")),
                    knowledge.bomb_planted,
                )
            else:
                outcome = getattr(item, "round_outcome", None)
                val = float(outcome) if outcome is not None else 0.5
            target_val_list.append(val)

            # Tactical role label (10 classes)
            strat_idx = self._classify_tactical_role(item, knowledge, all_players)
            strat_vec = torch.zeros(10)
            strat_vec[strat_idx] = 1.0
            target_strat_list.append(strat_vec)

        # F3-11: Track zero-tensor fallback rate — train step proceeds but tensors are meaningless.
        fallback_count = b - pov_count
        if pov_count > 0:
            logger.debug("RAP batch: %d/%d samples with real Player-POV tensors", pov_count, b)
        if fallback_count > 0:
            logger.warning(
                "RAP batch: %d/%d samples fell back to ZERO tensors (match DB unavailable). "
                "Training on zero-tensor data degrades model quality.",
                fallback_count,
                b,
            )

        view = torch.stack(view_list).to(self.device)
        map_tensor = torch.stack(map_list).to(self.device)
        motion_tensor = torch.stack(motion_list).to(self.device)
        target_val = torch.tensor(target_val_list, dtype=torch.float32).unsqueeze(1).to(self.device)
        target_strat = torch.stack(target_strat_list).to(self.device)

        return {
            "view": view,
            "map": map_tensor,
            "motion": motion_tensor,
            "metadata": metadata.unsqueeze(1),
            "target_strat": target_strat,
            "target_val": target_val,
        }

    def _build_sample_knowledge(
        self,
        match_id,
        tick,
        player_name,
        item,
        match_mgr,
        kb,
        all_players_cache,
        window_cache,
        event_cache,
    ):
        """Build PlayerKnowledge for a single training sample.

        Returns (knowledge, tick_list) or (None, [item]) on failure.
        Uses per-batch caches to avoid redundant queries.
        """
        # All players at this tick
        ap_key = (match_id, tick)
        if ap_key not in all_players_cache:
            all_players_cache[ap_key] = match_mgr.get_all_players_at_tick(match_id, tick)
        all_players = all_players_cache[ap_key]

        if not all_players:
            return None, [item]

        # Find our player in per-match data
        our_player_tick = None
        for p in all_players:
            if str(getattr(p, "player_name", "")) == player_name:
                our_player_tick = p
                break

        if our_player_tick is None:
            return None, [item]

        # Recent history for enemy memory (320-tick window)
        wnd_key = (match_id, tick)
        if wnd_key not in window_cache:
            window_cache[wnd_key] = match_mgr.get_all_players_tick_window(
                match_id, tick, window_size=320
            )
        recent_history = window_cache[wnd_key]

        # Events for sound + utility
        evt_key = (match_id, tick)
        if evt_key not in event_cache:
            event_cache[evt_key] = match_mgr.get_events_for_tick_range(
                match_id, max(0, tick - 320), tick + 64
            )
        events = event_cache[evt_key]

        knowledge = kb.build_knowledge(
            our_player_tick,
            all_players,
            recent_all_players_history=recent_history,
            active_events=events,
        )

        return knowledge, [our_player_tick]

    def _get_match_manager(self):
        """Get the match data manager singleton, or None if unavailable."""
        try:
            from Programma_CS2_RENAN.backend.storage.match_data_manager import (
                get_match_data_manager,
            )

            return get_match_data_manager()
        except Exception as e:
            logger.debug("Match data manager unavailable: %s", e)
            return None

    @staticmethod
    def _resolve_map_name(match_id, demo_name, match_mgr, metadata_cache):
        """Resolve map name from match metadata or demo_name pattern.

        Priority: match metadata DB > regex on demo_name > fallback "de_mirage".
        """
        # Try match metadata first
        if match_id is not None and match_mgr is not None:
            if match_id not in metadata_cache:
                try:
                    metadata_cache[match_id] = match_mgr.get_metadata(match_id)
                except Exception:
                    logger.debug("Metadata cache miss for match_id=%s", match_id, exc_info=True)
                    metadata_cache[match_id] = None

            meta = metadata_cache.get(match_id)
            if meta is not None and getattr(meta, "map_name", ""):
                return (
                    "de_" + meta.map_name if not meta.map_name.startswith("de_") else meta.map_name
                )

        # Fallback: extract from demo_name
        known_maps = (
            "mirage",
            "inferno",
            "dust2",
            "ancient",
            "nuke",
            "anubis",
            "overpass",
            "vertigo",
        )
        demo_lower = demo_name.lower()
        for m in known_maps:
            if m in demo_lower:
                return f"de_{m}"

        return "de_mirage"

    # ============ G-01: RoundStats Fetch for VL-JEPA ============

    def _fetch_round_stats_for_batch(self, raw_items):
        """Fetch RoundStats for batch items to provide outcome-based concept labels.

        Returns a list of RoundStats objects (one per item, None if unavailable),
        or None if no RoundStats could be found at all.
        """
        try:
            from sqlmodel import select

            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import RoundStats

            db = get_db_manager()

            # Collect unique (demo_name, player_name) pairs
            demo_player_pairs = set()
            for item in raw_items:
                demo = getattr(item, "demo_name", None)
                player = getattr(item, "player_name", None)
                if demo and player:
                    demo_player_pairs.add((demo, player))

            if not demo_player_pairs:
                return None

            # Fetch all relevant RoundStats in one query
            with db.get_session() as session:
                stats_by_key = {}
                for demo, player in demo_player_pairs:
                    rows = session.exec(
                        select(RoundStats)
                        .where(RoundStats.demo_name == demo, RoundStats.player_name == player)
                        .limit(50)
                    ).all()
                    for rs in rows:
                        stats_by_key[(demo, player, rs.round_number)] = rs

            if not stats_by_key:
                return None

            # Map each batch item to its RoundStats (use round_number estimate from tick)
            result = []
            found = 0
            for item in raw_items:
                demo = getattr(item, "demo_name", None)
                player = getattr(item, "player_name", None)
                tick = getattr(item, "tick", 0)
                # Estimate round number from tick (64 tick/s, ~115s per round)
                est_round = max(1, tick // (64 * 115) + 1)

                rs = None
                if demo and player:
                    # Try exact round, then nearest
                    rs = stats_by_key.get((demo, player, est_round))
                    if rs is None:
                        # Try round 1 as fallback (common for early ticks)
                        rs = stats_by_key.get((demo, player, 1))

                result.append(rs)
                if rs is not None:
                    found += 1

            if found == 0:
                return None

            return result

        except Exception as e:
            logger.debug("RoundStats fetch for VL-JEPA failed (non-fatal): %s", e)
            return None

    # ============ Training Target Computation ============

    # Advantage function weights
    _ADV_W_ALIVE = 0.4
    _ADV_W_HP = 0.2
    _ADV_W_EQUIP = 0.2
    _ADV_W_BOMB = 0.2

    # Tactical role thresholds
    _SAVE_EQUIP_THRESHOLD = 1500
    _LURK_DISTANCE_THRESHOLD = 1500.0
    _ENTRY_DISTANCE_THRESHOLD = 800.0
    _SUPPORT_DISTANCE_THRESHOLD = 500.0

    # Tactical role indices
    ROLE_SITE_TAKE = 0
    ROLE_ROTATION = 1
    ROLE_ENTRY_FRAG = 2
    ROLE_SUPPORT = 3
    ROLE_ANCHOR = 4
    ROLE_LURK = 5
    ROLE_RETAKE = 6
    ROLE_SAVE = 7
    ROLE_AGGRESSIVE_PUSH = 8
    ROLE_PASSIVE_HOLD = 9

    @staticmethod
    def _compute_advantage(all_players_at_tick, player_team, bomb_planted):
        """Compute continuous advantage value [0, 1] from game state.

        Formula: 0.4 * alive_diff + 0.2 * hp_ratio + 0.2 * equip_ratio + 0.2 * bomb_factor

        This replaces binary win/lose (G-04) with a granular signal that
        reflects the actual tactical advantage at each tick.
        """
        team_alive = 0
        team_hp = 0
        team_equip = 0
        enemy_alive = 0
        enemy_hp = 0
        enemy_equip = 0

        for p in all_players_at_tick:
            if not getattr(p, "is_alive", True):
                continue
            p_team = str(getattr(p, "team", ""))
            hp = int(getattr(p, "health", 100))
            equip = int(getattr(p, "equipment_value", 0))

            if p_team == player_team:
                team_alive += 1
                team_hp += hp
                team_equip += equip
            else:
                enemy_alive += 1
                enemy_hp += hp
                enemy_equip += equip

        # alive_diff: normalize [-5, 5] → [0, 1]
        alive_diff = (team_alive - enemy_alive + 5) / 10.0
        alive_diff = max(0.0, min(1.0, alive_diff))

        # HP ratio: team HP / total HP
        total_hp = team_hp + enemy_hp
        hp_ratio = team_hp / total_hp if total_hp > 0 else 0.5

        # Equipment ratio: team equip / total equip
        total_equip = team_equip + enemy_equip
        equip_ratio = team_equip / total_equip if total_equip > 0 else 0.5

        # Bomb factor: planted → advantage for T, disadvantage for CT
        bomb_factor = 0.5
        if bomb_planted:
            bomb_factor = 0.7 if player_team == "T" else 0.3

        advantage = (
            TrainingOrchestrator._ADV_W_ALIVE * alive_diff
            + TrainingOrchestrator._ADV_W_HP * hp_ratio
            + TrainingOrchestrator._ADV_W_EQUIP * equip_ratio
            + TrainingOrchestrator._ADV_W_BOMB * bomb_factor
        )
        return max(0.0, min(1.0, advantage))

    def _classify_tactical_role(self, item, knowledge, all_players):
        """Classify tactical role from game state heuristics.

        Returns index 0-9 for one of:
        site_take, rotation, entry_frag, support, anchor,
        lurk, retake, save, aggressive_push, passive_hold

        When PlayerKnowledge is available, uses teammate distances, enemy
        visibility, and bomb state for classification. Falls back to
        simplified team-based default when knowledge is unavailable.
        """
        team = str(getattr(item, "team", "CT"))
        is_ct = team == "CT"
        equip = int(getattr(item, "equipment_value", 0) or 0)
        is_crouching = bool(getattr(item, "is_crouching", False))

        # Save round detection (lowest priority override — equipment too low)
        if equip < self._SAVE_EQUIP_THRESHOLD:
            return self.ROLE_SAVE

        # Without knowledge, use simple team-based defaults
        if knowledge is None:
            return self.ROLE_PASSIVE_HOLD if is_ct else self.ROLE_SITE_TAKE

        # --- Knowledge-informed classification ---
        bomb_planted = knowledge.bomb_planted
        has_visible_enemies = knowledge.visible_enemy_count > 0
        teammates = knowledge.teammate_positions

        avg_team_dist = 0.0
        if teammates:
            avg_team_dist = sum(tm.distance for tm in teammates) / len(teammates)

        # CT + bomb planted → retake
        if is_ct and bomb_planted:
            return self.ROLE_RETAKE

        # Lurk (far from team, no visible enemies)
        if avg_team_dist > self._LURK_DISTANCE_THRESHOLD and not has_visible_enemies:
            return self.ROLE_LURK

        # Entry frag (visible enemies + close range)
        if has_visible_enemies and knowledge.visible_enemies:
            closest_dist = min(e.distance for e in knowledge.visible_enemies)
            if closest_dist < self._ENTRY_DISTANCE_THRESHOLD:
                return self.ROLE_ENTRY_FRAG
            # Visible enemies but farther → aggressive push
            return self.ROLE_AGGRESSIVE_PUSH

        # CT-specific roles
        if is_ct:
            if is_crouching:
                return self.ROLE_ANCHOR
            return self.ROLE_PASSIVE_HOLD

        # T-specific roles
        if avg_team_dist < self._SUPPORT_DISTANCE_THRESHOLD and len(teammates) >= 2:
            return self.ROLE_SUPPORT

        return self.ROLE_SITE_TAKE

    def _report_progress(self, epoch, t_loss, v_loss):
        """Update Dashboard State."""
        msg = f"Epoch {epoch}/{self.max_epochs} | Train: {t_loss:.4f} | Val: {v_loss:.4f}"
        logger.info(msg)
        self.manager._update_state("Training", msg)
