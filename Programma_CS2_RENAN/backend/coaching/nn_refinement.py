"""
NN Refinement

Applies neural-network weight adjustments to pre-computed coaching corrections,
scaling each correction's weighted Z-score by the NN-suggested feature weight.
"""

from typing import Any, Dict, List


def apply_nn_refinement(
    corrections: List[Dict[str, Any]],
    nn_adjustments: Dict[str, float],
) -> List[Dict[str, Any]]:
    refined: List[Dict[str, Any]] = []

    for c in corrections:
        feature = c["feature"]

        adjustment = nn_adjustments.get(f"{feature}_weight", 0.0)
        refined_z = c["weighted_z"] * (1 + adjustment)

        refined.append({**c, "weighted_z": refined_z})

    return refined
