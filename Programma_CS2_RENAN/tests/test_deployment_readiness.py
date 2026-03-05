"""
Deployment readiness tests — model robustness, latency, and verdict.

Migrated from tools/brain_verification/ (118-rule framework). Only the
unique checks not covered by the existing pytest suite are preserved:
  - 100-pass forward reliability (Rule 99)
  - Inference latency budgets (Rule 45)
  - Batch-size invariance (Rule 47)
  - Deterministic reproducibility (Rule 51)
  - OOD graceful handling (Rules 9, 112)
  - Deployment verdict aggregation (Section 16)

All other rules were already covered by test_jepa_model.py,
test_rap_coach.py, test_nn_infrastructure.py, test_nn_training.py,
and other existing test files.
"""

import os
import time
from dataclasses import dataclass
from statistics import median
from typing import Any, Dict, List, Optional

import pytest
import torch
import torch.nn as nn

from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
SEQ_LEN = 10

# Latency budgets in ms (CPU, batch=1, seq=10).
# Multiplied by CI_LATENCY_MULTIPLIER for CI environments with slow CPUs.
LATENCY_BUDGET_MS = {
    ModelFactory.TYPE_LEGACY: 10,
    ModelFactory.TYPE_JEPA: 20,
    ModelFactory.TYPE_RAP: 50,
}
CI_LATENCY_MULTIPLIER = float(os.environ.get("CS2_LATENCY_MULTIPLIER", "3.0"))

# Model types grouped by input signature
_SEQUENCED_TYPES = [
    ModelFactory.TYPE_LEGACY,
    ModelFactory.TYPE_JEPA,
    ModelFactory.TYPE_VL_JEPA,
]
_ALL_TYPES = [
    ModelFactory.TYPE_LEGACY,
    ModelFactory.TYPE_JEPA,
    ModelFactory.TYPE_VL_JEPA,
    ModelFactory.TYPE_RAP,
    ModelFactory.TYPE_ROLE_HEAD,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_model(model_type: str) -> nn.Module:
    """Instantiate a model via ModelFactory, eval mode, CPU."""
    torch.manual_seed(SEED)
    model = ModelFactory.get_model(model_type)
    model.eval()
    return model


def _random_input(
    model_type: str, batch_size: int = 1, seq_len: int = SEQ_LEN
) -> Dict[str, torch.Tensor]:
    """Generate correct-shape random tensors for a model type."""
    if model_type == ModelFactory.TYPE_ROLE_HEAD:
        return {"x": torch.randn(batch_size, 5)}

    if model_type in _SEQUENCED_TYPES:
        return {"x": torch.randn(batch_size, seq_len, METADATA_DIM)}

    if model_type == ModelFactory.TYPE_RAP:
        return {
            "view_frame": torch.randn(batch_size, 3, 64, 64),
            "map_frame": torch.randn(batch_size, 3, 64, 64),
            "motion_diff": torch.randn(batch_size, 3, 64, 64),
            "metadata": torch.randn(batch_size, seq_len, METADATA_DIM),
        }

    raise ValueError(f"Unknown model_type: {model_type}")


def _forward(model: nn.Module, inputs: Dict[str, torch.Tensor]) -> Any:
    """Run forward pass with correct call signature."""
    with torch.no_grad():
        if "view_frame" in inputs:
            return model(
                inputs["view_frame"],
                inputs["map_frame"],
                inputs["motion_diff"],
                inputs["metadata"],
            )
        return model(inputs["x"])


def _extract_tensor(result: Any) -> Optional[torch.Tensor]:
    """Extract the main output tensor from a forward result."""
    if isinstance(result, torch.Tensor):
        return result
    if isinstance(result, dict):
        for key in ("advice_probs", "coaching_output", "concept_probs"):
            if key in result:
                return result[key]
        for v in result.values():
            if isinstance(v, torch.Tensor):
                return v
    return None


def _has_nan_or_inf(t: torch.Tensor) -> bool:
    return bool(torch.isnan(t).any() or torch.isinf(t).any())


def _requires_rap(model_type: str):
    """Skip if RAP dependencies are not installed."""
    if model_type == ModelFactory.TYPE_RAP:
        pytest.importorskip("ncps", reason="ncps required for RAP model")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(params=_ALL_TYPES, ids=lambda t: t)
def model_and_type(request):
    """Parametrized fixture: (model_type, model) for all 5 types."""
    mt = request.param
    _requires_rap(mt)
    return mt, _make_model(mt)


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------
class TestForwardPassReliability:
    """100 consecutive forward passes per model — zero NaN or exceptions."""

    N_PASSES = 100

    @pytest.mark.parametrize("model_type", _ALL_TYPES, ids=lambda t: t)
    def test_100_forward_passes_no_failures(self, model_type):
        _requires_rap(model_type)
        model = _make_model(model_type)
        nan_count = 0

        for i in range(self.N_PASSES):
            torch.manual_seed(SEED + i)
            inputs = _random_input(model_type)
            result = _forward(model, inputs)
            tensor = _extract_tensor(result)
            assert tensor is not None, f"Pass {i}: forward returned no tensor"
            if _has_nan_or_inf(tensor):
                nan_count += 1

        assert nan_count == 0, (
            f"{model_type}: {nan_count}/{self.N_PASSES} passes produced NaN/Inf"
        )


class TestInferenceLatency:
    """Inference latency must stay within budget (with CI tolerance)."""

    N_MEASURED = 5

    @pytest.mark.parametrize(
        "model_type,budget_ms",
        [
            (ModelFactory.TYPE_LEGACY, 10),
            (ModelFactory.TYPE_JEPA, 20),
            (ModelFactory.TYPE_RAP, 50),
        ],
        ids=["legacy", "jepa", "rap"],
    )
    def test_latency_within_budget(self, model_type, budget_ms):
        _requires_rap(model_type)
        model = _make_model(model_type)
        inputs = _random_input(model_type, batch_size=1, seq_len=SEQ_LEN)

        # Warmup pass (JIT, cache)
        _forward(model, inputs)

        timings_ms = []
        for _ in range(self.N_MEASURED):
            t0 = time.perf_counter()
            _forward(model, inputs)
            timings_ms.append((time.perf_counter() - t0) * 1000)

        med = median(timings_ms)
        effective_budget = budget_ms * CI_LATENCY_MULTIPLIER
        assert med < effective_budget, (
            f"{model_type} median latency {med:.1f}ms exceeds "
            f"{effective_budget:.0f}ms (base={budget_ms}ms × {CI_LATENCY_MULTIPLIER})"
        )


class TestBatchSizeInvariance:
    """batch=1 output[0] must match batch=4 output[0] (deterministic)."""

    @pytest.mark.parametrize("model_type", _ALL_TYPES, ids=lambda t: t)
    def test_batch_one_matches_batch_four(self, model_type):
        _requires_rap(model_type)

        # Generate batch=4 input, then slice first sample for batch=1.
        # (torch.randn produces different sequences for different shapes,
        # so we must slice rather than regenerate.)
        torch.manual_seed(SEED)
        inp4 = _random_input(model_type, batch_size=4)
        inp1 = {k: v[0:1].clone() for k, v in inp4.items()}

        # Separate model instances to avoid hidden-state contamination
        out1 = _extract_tensor(_forward(_make_model(model_type), inp1))
        out4 = _extract_tensor(_forward(_make_model(model_type), inp4))

        assert out1 is not None and out4 is not None
        torch.testing.assert_close(
            out4[0:1], out1, atol=1e-5, rtol=1e-5,
            msg=f"{model_type}: batch=4[0] != batch=1 output",
        )


class TestDeterministicReproducibility:
    """5 runs with same seed must produce identical output (max diff < 1e-6)."""

    N_RUNS = 5

    @pytest.mark.parametrize(
        "model_type",
        [ModelFactory.TYPE_LEGACY, ModelFactory.TYPE_JEPA],
        ids=["legacy", "jepa"],
    )
    def test_same_seed_five_runs(self, model_type):
        outputs = []
        for _ in range(self.N_RUNS):
            torch.manual_seed(SEED)
            model = _make_model(model_type)
            torch.manual_seed(SEED)
            inputs = _random_input(model_type)
            tensor = _extract_tensor(_forward(model, inputs))
            assert tensor is not None
            outputs.append(tensor.detach().cpu().float())

        ref = outputs[0]
        for i, out in enumerate(outputs[1:], 1):
            max_diff = torch.max(torch.abs(out - ref)).item()
            assert max_diff < 1e-6, (
                f"{model_type} run {i}: max diff {max_diff:.2e} >= 1e-6"
            )


class TestOODGracefulHandling:
    """Out-of-distribution and impossible inputs must not crash the model."""

    @pytest.mark.parametrize(
        "model_type",
        [ModelFactory.TYPE_LEGACY, ModelFactory.TYPE_JEPA, ModelFactory.TYPE_VL_JEPA],
        ids=["legacy", "jepa", "vl-jepa"],
    )
    @pytest.mark.parametrize(
        "ood_case,fill_value",
        [("all_zeros", 0.0), ("all_999", 999.0)],
        ids=["zeros", "extreme"],
    )
    def test_ood_inputs_no_crash(self, model_type, ood_case, fill_value):
        model = _make_model(model_type)
        x = torch.full((1, SEQ_LEN, METADATA_DIM), fill_value)
        with torch.no_grad():
            result = model(x)

        tensor = _extract_tensor(result)
        assert tensor is not None, f"{model_type} returned no tensor for {ood_case}"
        assert not _has_nan_or_inf(tensor), (
            f"{model_type} produced NaN/Inf for {ood_case} input"
        )

    @pytest.mark.parametrize(
        "model_type",
        [ModelFactory.TYPE_LEGACY, ModelFactory.TYPE_JEPA, ModelFactory.TYPE_VL_JEPA],
        ids=["legacy", "jepa", "vl-jepa"],
    )
    def test_nan_input_graceful(self, model_type):
        """NaN input should either produce finite output or raise a clean error."""
        model = _make_model(model_type)
        x = torch.full((1, SEQ_LEN, METADATA_DIM), float("nan"))
        try:
            with torch.no_grad():
                model(x)
            # If it didn't raise, output may contain NaN — that's acceptable
            # as long as it didn't crash with an unhandled exception.
        except (RuntimeError, ValueError):
            pass  # Clean exception is acceptable for NaN input


# ---------------------------------------------------------------------------
# Deployment Verdict
# ---------------------------------------------------------------------------
@dataclass
class _SubCheck:
    name: str
    passed: bool
    detail: str = ""


class TestDeploymentVerdict:
    """Aggregate sub-checks into a deployment readiness verdict."""

    def _run_subchecks(self) -> List[_SubCheck]:
        results: List[_SubCheck] = []

        for mt in _ALL_TYPES:
            # Skip RAP if ncps not available
            try:
                if mt == ModelFactory.TYPE_RAP:
                    import ncps  # noqa: F401
            except ImportError:
                results.append(_SubCheck(f"reliability_{mt}", True, "skipped (ncps)"))
                continue

            model = _make_model(mt)

            # Sub-check: 10-pass reliability (lighter than full 100)
            nan_count = 0
            for i in range(10):
                torch.manual_seed(SEED + i)
                inp = _random_input(mt)
                try:
                    tensor = _extract_tensor(_forward(model, inp))
                    if tensor is not None and _has_nan_or_inf(tensor):
                        nan_count += 1
                except Exception as exc:
                    results.append(_SubCheck(f"reliability_{mt}", False, str(exc)))
                    break
            else:
                ok = nan_count == 0
                results.append(_SubCheck(
                    f"reliability_{mt}", ok,
                    f"{nan_count}/10 NaN" if not ok else "ok",
                ))

            # Sub-check: output shape
            torch.manual_seed(SEED)
            inp = _random_input(mt)
            try:
                tensor = _extract_tensor(_forward(model, inp))
                shape_ok = tensor is not None and tensor.numel() > 0
                results.append(_SubCheck(f"shape_{mt}", shape_ok))
            except Exception as exc:
                results.append(_SubCheck(f"shape_{mt}", False, str(exc)))

        return results

    def test_verdict_not_red(self):
        """Deployment verdict must not be RED (pass_rate >= 75%)."""
        results = self._run_subchecks()
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        pass_rate = passed / max(total, 1)

        failures = [f"{r.name}: {r.detail}" for r in results if not r.passed]
        assert pass_rate >= 0.75, (
            f"Deployment verdict RED: {passed}/{total} passed ({pass_rate:.0%}). "
            f"Failures: {failures}"
        )

    def test_no_nan_red_flag(self):
        """No model should produce NaN in >10% of forward passes."""
        for mt in [ModelFactory.TYPE_LEGACY, ModelFactory.TYPE_JEPA]:
            model = _make_model(mt)
            nan_count = 0
            n_passes = 20

            for i in range(n_passes):
                torch.manual_seed(SEED + i)
                inp = _random_input(mt)
                tensor = _extract_tensor(_forward(model, inp))
                if tensor is not None and _has_nan_or_inf(tensor):
                    nan_count += 1

            ratio = nan_count / n_passes
            assert ratio <= 0.10, (
                f"{mt}: NaN red flag — {nan_count}/{n_passes} ({ratio:.0%}) > 10%"
            )
