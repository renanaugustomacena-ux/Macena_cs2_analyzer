"""
Tests for DatabaseGovernor & E2E Pipeline — Phase 10 Coverage Expansion.

Covers:
  DatabaseGovernor (db_governor.py) — audit_storage, verify_integrity, rebuild_indexes
  E2E: ModelFactory → RAPCoachModel → forward, skill_vec curriculum
"""

import sys


from unittest.mock import MagicMock, patch

import torch


# ---------------------------------------------------------------------------
# DatabaseGovernor
# ---------------------------------------------------------------------------
class TestDatabaseGovernor:
    """Tests for the DatabaseGovernor using mocked DB/match managers."""

    def _make_governor(self):
        from Programma_CS2_RENAN.backend.control.db_governor import DatabaseGovernor

        gov = DatabaseGovernor.__new__(DatabaseGovernor)
        gov.db_manager = MagicMock()
        gov.match_manager = MagicMock()
        return gov

    def test_audit_storage_structure(self):
        gov = self._make_governor()
        gov.match_manager.list_available_matches.return_value = ["m1", "m2"]
        gov.match_manager.get_total_storage_bytes.return_value = 1024000

        report = gov.audit_storage()
        assert "tier1_2_size" in report
        assert "tier3_count" in report
        assert report["tier3_count"] == 2
        assert report["tier3_total_size"] == 1024000
        assert "anomalies" in report

    def test_audit_storage_no_db(self, tmp_path):
        """When monolith DB doesn't exist, reports anomaly."""
        gov = self._make_governor()
        gov.match_manager.list_available_matches.return_value = []
        gov.match_manager.get_total_storage_bytes.return_value = 0

        with patch("Programma_CS2_RENAN.backend.control.db_governor.DB_DIR", str(tmp_path)), \
             patch("Programma_CS2_RENAN.backend.control.db_governor.CORE_DB_DIR", str(tmp_path)):
            report = gov.audit_storage()
        assert any("not found" in a for a in report["anomalies"])

    def test_verify_integrity_light(self):
        """Light integrity check (SELECT 1)."""
        gov = self._make_governor()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 1
        gov.db_manager.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        gov.db_manager.get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = gov.verify_integrity(full=False)
        assert result["monolith"] is True

    def test_verify_integrity_full(self):
        """Full integrity check (PRAGMA quick_check)."""
        gov = self._make_governor()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = "ok"
        gov.db_manager.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        gov.db_manager.get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = gov.verify_integrity(full=True)
        assert result["monolith"] is True

    def test_rebuild_indexes(self):
        """Rebuild indexes should call REINDEX."""
        gov = self._make_governor()
        mock_session = MagicMock()
        gov.db_manager.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        gov.db_manager.get_session.return_value.__exit__ = MagicMock(return_value=False)

        gov.rebuild_indexes()
        mock_session.execute.assert_called_once()

    def test_prune_match_data(self):
        gov = self._make_governor()
        gov.match_manager.delete_match.return_value = True
        assert gov.prune_match_data(42) is True
        gov.match_manager.delete_match.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# E2E: ModelFactory → RAP Coach → Forward
# ---------------------------------------------------------------------------
class TestE2EPipeline:
    """End-to-end tests for the RAP Coach inference pipeline."""

    def test_factory_creates_rap_model(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        model = ModelFactory.get_model("rap")
        assert model is not None
        assert hasattr(model, "forward")

    def test_rap_forward_full_pipeline(self):
        """Full forward pass: perception → memory → strategy → pedagogy."""
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM

        torch.manual_seed(42)
        model = ModelFactory.get_model("rap")
        model.eval()

        batch, seq = 2, 5
        inputs = {
            "view_frame": torch.randn(batch, 3, 64, 64),
            "map_frame": torch.randn(batch, 3, 64, 64),
            "motion_diff": torch.randn(batch, 3, 64, 64),
            "metadata": torch.randn(batch, seq, METADATA_DIM),
            "skill_vec": torch.zeros(batch, 10),
        }

        with torch.no_grad():
            output = model(**inputs)

        assert "advice_probs" in output
        assert "value_estimate" in output
        assert "gate_weights" in output
        assert output["advice_probs"].shape[0] == batch
        assert output["value_estimate"].shape == (batch, 1)

    def test_skill_vec_modulates_output(self):
        """Different skill vectors should produce different outputs."""
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM

        torch.manual_seed(42)
        model = ModelFactory.get_model("rap")
        model.eval()

        batch, seq = 1, 3
        base_inputs = {
            "view_frame": torch.randn(batch, 3, 64, 64),
            "map_frame": torch.randn(batch, 3, 64, 64),
            "motion_diff": torch.randn(batch, 3, 64, 64),
            "metadata": torch.randn(batch, seq, METADATA_DIM),
        }

        with torch.no_grad():
            out1 = model(**base_inputs, skill_vec=torch.zeros(batch, 10))
            out2 = model(**base_inputs, skill_vec=torch.ones(batch, 10))

        # skill_vec modulates pedagogy (value_estimate), not strategy (advice_probs)
        assert not torch.allclose(out1["value_estimate"], out2["value_estimate"], atol=1e-6)

    def test_rap_no_nan_in_output(self):
        """No NaN values in any output tensor."""
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM

        torch.manual_seed(0)
        model = ModelFactory.get_model("rap")
        model.eval()

        inputs = {
            "view_frame": torch.randn(2, 3, 64, 64),
            "map_frame": torch.randn(2, 3, 64, 64),
            "motion_diff": torch.randn(2, 3, 64, 64),
            "metadata": torch.randn(2, 5, METADATA_DIM),
            "skill_vec": torch.randn(2, 10),
        }

        with torch.no_grad():
            output = model(**inputs)

        for key, tensor in output.items():
            if isinstance(tensor, torch.Tensor):
                assert not torch.isnan(tensor).any(), f"NaN in {key}"

    def test_sparsity_loss_with_gate(self):
        """compute_sparsity_loss should return scalar when gate_weights present."""
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM

        torch.manual_seed(42)
        model = ModelFactory.get_model("rap")

        inputs = {
            "view_frame": torch.randn(2, 3, 64, 64),
            "map_frame": torch.randn(2, 3, 64, 64),
            "motion_diff": torch.randn(2, 3, 64, 64),
            "metadata": torch.randn(2, 5, METADATA_DIM),
            "skill_vec": torch.zeros(2, 10),
        }

        output = model(**inputs)
        loss = model.compute_sparsity_loss(output.get("gate_weights"))
        assert isinstance(loss, torch.Tensor)
        assert loss.dim() == 0  # Scalar
        assert loss.item() >= 0
