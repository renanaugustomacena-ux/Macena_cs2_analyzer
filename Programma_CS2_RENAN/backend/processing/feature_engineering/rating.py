"""
Unified HLTV 2.0 Rating Calculator.

CRITICAL: All rating computations across the pipeline MUST go through this module.
Both demo_parser.py and base_features.py MUST use these functions to prevent
'Inference-Training Skew' where the parser produces one rating but the
training pipeline produces another.

Reference: Reverse-engineered HLTV 2.0 coefficients (Leetify / open-source match data).

CONTRACT — kast argument semantics (CRITICAL — do NOT mix up):
  - compute_hltv2_rating()            → kast as RATIO  (0.0 – 1.0,  e.g. 0.72)
  - compute_hltv2_rating_regression() → kast_pct as PERCENTAGE (0 – 100, e.g. 72.0)

The regression function includes a runtime guard that auto-converts a ratio to a
percentage and emits a warning, because confusing these two produces silently wrong
ratings (error ~×100 on the KAST term).
"""

import logging as _logging
_rating_logger = _logging.getLogger("cs2analyzer.rating")

# --- HLTV 2.0 Pro Baseline Constants ---
# These represent the average professional player.
# Dividing each component by its baseline normalizes to ~1.0 for an average pro.
BASELINE_KPR = 0.679
BASELINE_DPR_COMPLEMENT = 0.317  # 1 - avg_DPR
BASELINE_KAST = 0.70
BASELINE_IMPACT = 1.0
BASELINE_ADR = 73.3

# --- HLTV 2.0 Regression Coefficients ---
# Reverse-engineered via linear regression on scraped HLTV player data.
# R²=0.995, RMSE=0.0046, MAE=0.0021 on 80/20 holdout.
# See docs/strategic_insights/HLTV_RATING_2_0_REVERSE_ENGINEERING.md
HLTV2_COEFF_KAST = 0.00738764
HLTV2_COEFF_KPR = 0.35912389
HLTV2_COEFF_DPR = -0.53295080
HLTV2_COEFF_IMPACT = 0.23726030
HLTV2_COEFF_ADR = 0.00323970
HLTV2_INTERCEPT = 0.15872723


def compute_impact_rating(kpr: float, avg_adr: float = 0.0, dpr: float = None) -> float:
    """
    Computes HLTV 2.0 Impact Rating.

    Full formula: 2.13*KPR + 0.42*AssistPR - 0.41*SurvivalPR
    When dpr is provided, the survival penalty (-0.41*(1-dpr)) is applied.
    When dpr is None, the term is omitted — result is systematically
    ~0.1–0.2 pts higher than the true impact for typical DPR values.

    Args:
        kpr:     Kills per round (ratio, e.g. 0.72)
        avg_adr: Average damage per round (raw, e.g. 85.3)
        dpr:     Deaths per round (ratio, e.g. 0.65). Optional.
                 When provided, the survival penalty is included.

    Returns:
        Impact rating (raw, typically ~0.8 – 1.4 for pros)
    """
    result = (kpr * 2.13) + (avg_adr / 100.0 * 0.42)
    if dpr is not None:
        survival_pr = 1.0 - dpr
        result -= 0.41 * survival_pr
    return result


def compute_survival_rating(dpr: float) -> float:
    """
    Computes HLTV 2.0 Survival Rating component.

    Args:
        dpr: Deaths per round (ratio, e.g. 0.65)

    Returns:
        Survival rating (raw, higher is better)
    """
    return 1.0 - dpr


def compute_hltv2_rating(
    kpr: float,
    dpr: float,
    kast: float,
    avg_adr: float,
    impact: float = None,
) -> float:
    """
    Computes the unified HLTV 2.0 Rating.

    Each of the 5 components is normalized against pro-baseline:
        R = (kill + survival + kast + impact + damage) / 5

    Args:
        kpr: Kills per round (ratio, e.g. 0.72)
        dpr: Deaths per round (ratio, e.g. 0.65)
        kast: KAST ratio (0.0 - 1.0, e.g. 0.72)
        avg_adr: Average damage per round (raw, e.g. 85.3)
        impact: Pre-computed impact rating. If None, auto-computed from kpr+adr.

    Returns:
        HLTV 2.0 Rating (float, ~1.0 for average pro)
    """
    if impact is None:
        impact = compute_impact_rating(kpr, avg_adr, dpr=dpr)

    r_kill = kpr / BASELINE_KPR
    r_surv = compute_survival_rating(dpr) / BASELINE_DPR_COMPLEMENT
    r_kast = kast / BASELINE_KAST
    r_imp = impact / BASELINE_IMPACT
    r_dmg = avg_adr / BASELINE_ADR

    # NOTE (F2-40): This per-component average deliberately diverges from
    # compute_hltv2_rating_regression(). The two functions serve different purposes:
    # this one is for per-component deviation analysis (each term is independently
    # interpretable), the regression formula matches HLTV's published values.
    # Do NOT reconcile them — the divergence is by design.
    return (r_kill + r_surv + r_kast + r_imp + r_dmg) / 5.0


# F2-39: DEAD CODE — never called anywhere in the production codebase.
# Retained for reference only (matches HLTV's published coefficients).
# Consider deleting when the regression approach is formally deprecated.
def compute_hltv2_rating_regression(
    kpr: float,
    dpr: float,
    kast_pct: float,
    avg_adr: float,
    impact: float = None,
) -> float:
    """
    Computes HLTV 2.0 Rating using regression coefficients.

    This reproduces HLTV's published rating to within +/-0.01.
    Use this when you need to match HLTV's exact number (e.g.,
    validating scraped data or displaying a rating on the UI).

    For coaching deviation analysis (comparing player vs pro per
    component), use compute_hltv2_rating() instead.

    Args:
        kpr: Kills per round (e.g. 0.78)
        dpr: Deaths per round (e.g. 0.62)
        kast_pct: KAST as percentage (e.g. 72.0 for 72%)
        avg_adr: Average damage per round (e.g. 82.0)
        impact: HLTV Impact rating. If None, auto-computed from kpr+adr.

    Returns:
        HLTV 2.0 Rating (float, rounded to 2 decimal places)
    """
    # F2-39 guard: kast_pct must be a percentage (0–100), NOT a ratio (0.0–1.0).
    # HLTV2_COEFF_KAST = 0.00738764 multiplies the percentage value.
    # Passing 0.72 (ratio) instead of 72.0 (percent) produces a KAST contribution
    # of ~0.005 instead of ~0.532 — a 100× error that silently corrupts the rating.
    if kast_pct <= 1.0:
        _rating_logger.warning(
            "compute_hltv2_rating_regression() received kast_pct=%.4f which looks like "
            "a ratio (0.0-1.0). Auto-converting to percentage (×100). "
            "Pass kast_pct as a percentage, e.g. 72.0 for 72%%.",
            kast_pct,
        )
        kast_pct = kast_pct * 100.0

    if impact is None:
        impact = compute_impact_rating(kpr, avg_adr, dpr=dpr)

    raw = (
        HLTV2_COEFF_KAST * kast_pct
        + HLTV2_COEFF_KPR * kpr
        + HLTV2_COEFF_DPR * dpr
        + HLTV2_COEFF_IMPACT * impact
        + HLTV2_COEFF_ADR * avg_adr
        + HLTV2_INTERCEPT
    )
    return round(raw, 2)
