"""
OllamaCoachWriter — Natural language polishing for coaching insights.

Uses the existing LLMService (Ollama) to transform structured coaching data
into conversational, actionable advice. Falls back gracefully when Ollama
is unavailable, returning the original template text unchanged.

Integration:
    coaching_service.py calls polish() after generating each CoachingInsight.
"""

from functools import lru_cache
from typing import Dict, Optional

from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.ollama_writer")

# F5-24: System prompt is a module constant for now. To tune without code changes,
# override via config: get_setting("COACH_SYSTEM_PROMPT", default=_DEFAULT_PROMPT).
# coaching_dialogue.py and llm_service.py have similar prompts that should also be
# made configurable when prompt engineering becomes a priority.
COACH_SYSTEM_PROMPT = (
    "You are a CS2 tactical coach. Based on the analysis data provided, "
    "write a brief, actionable coaching tip (2-3 sentences). "
    "Be specific and encouraging. Do NOT repeat raw numbers — interpret them."
)


class OllamaCoachWriter:
    """Polishes CoachingInsight messages via local Ollama LLM."""

    def __init__(self):
        self._service = None
        self._enabled: Optional[bool] = None

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            self._enabled = get_setting("USE_OLLAMA_COACHING", default=False)
        return self._enabled

    @property
    def service(self):
        if self._service is None:
            from Programma_CS2_RENAN.backend.services.llm_service import get_llm_service

            self._service = get_llm_service()
        return self._service

    def polish(
        self,
        title: str,
        message: str,
        focus_area: str,
        severity: str,
        map_name: str = "",
    ) -> str:
        """Enhance a coaching message with natural language via Ollama.

        Args:
            title: Insight title (e.g. "Positioning Gap: de_mirage").
            message: Raw template message to polish.
            focus_area: Coaching category (positioning, economy, aim, etc.).
            severity: Info / Medium / High.
            map_name: CS2 map name for context.

        Returns:
            Polished message string if Ollama is available and enabled,
            or the original *message* unchanged as fallback.
        """
        if not self.enabled:
            return message

        if not self.service.is_available():
            logger.debug("Ollama unavailable — returning template text")
            return message

        prompt = (
            f"Title: {title}\n"
            f"Focus: {focus_area}\n"
            f"Severity: {severity}\n"
            f"Map: {map_name or 'unknown'}\n\n"
            f"Raw Analysis:\n{message}\n\n"
            "Rewrite the above into a concise, encouraging coaching tip."
        )

        try:
            result = self.service.generate(prompt, system_prompt=COACH_SYSTEM_PROMPT)
            if result and not result.startswith("[LLM"):
                logger.debug("Ollama polished insight: %s", title)
                return result.strip()
            logger.debug("Ollama returned error marker — using original text")
        except Exception as e:
            logger.warning("Ollama polish failed: %s", e)

        return message


_writer: Optional[OllamaCoachWriter] = None


def get_ollama_writer() -> OllamaCoachWriter:
    """Singleton accessor."""
    global _writer
    if _writer is None:
        _writer = OllamaCoachWriter()
    return _writer
