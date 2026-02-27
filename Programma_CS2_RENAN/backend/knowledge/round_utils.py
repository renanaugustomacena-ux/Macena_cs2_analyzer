"""
Shared round-phase utilities for the knowledge and services layers.

Extracted from coaching_service.py, experience_bank.py, and rag_knowledge.py
to eliminate duplication (F5-20).
"""

from typing import Dict

# Equipment-value thresholds that define round economy phases.
_PISTOL_MAX_EQUIP: int = 1500
_ECO_MAX_EQUIP: int = 3000
_FORCE_MAX_EQUIP: int = 4000


def infer_round_phase(tick_data: Dict) -> str:
    """Infer round economy phase from equipment value.

    Args:
        tick_data: Tick snapshot containing ``equipment_value`` key.

    Returns:
        One of: "pistol", "eco", "force", "full_buy".
    """
    equip = tick_data.get("equipment_value", 0)
    if equip < _PISTOL_MAX_EQUIP:
        return "pistol"
    if equip < _ECO_MAX_EQUIP:
        return "eco"
    if equip < _FORCE_MAX_EQUIP:
        return "force"
    return "full_buy"
