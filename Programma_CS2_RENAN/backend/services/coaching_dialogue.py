"""
Coaching Dialogue Engine

Multi-turn coaching dialogue with RAG and Experience Bank augmentation.
Evolves the single-shot OllamaCoachWriter into an interactive session
where players can ask follow-up questions about their performance.

Integration Points:
    - llm_service.py: LLMService.chat() for multi-turn Ollama conversations
    - rag_knowledge.py: KnowledgeRetriever for tactical knowledge retrieval
    - experience_bank.py: ExperienceBank for COPER experience retrieval
    - coaching_service.py: Existing push-coaching (unchanged, parallel capability)
"""

import threading
from typing import Dict, List, Optional

from sqlmodel import desc, select

from Programma_CS2_RENAN.backend.services.llm_service import get_llm_service
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.coaching_dialogue")

# Intent classification keywords for retrieval routing
INTENT_KEYWORDS: Dict[str, List[str]] = {
    "positioning": [
        "position",
        "angle",
        "spot",
        "hold",
        "peek",
        "stand",
        "rotate",
        "flank",
        "site",
        "where",
        "place",
    ],
    "utility": [
        "smoke",
        "flash",
        "molotov",
        "HE",
        "grenade",
        "utility",
        "nade",
        "lineup",
        "throw",
    ],
    "economy": [
        "eco",
        "buy",
        "save",
        "money",
        "force",
        "full buy",
        "pistol",
        "budget",
        "invest",
    ],
    "aim": [
        "aim",
        "spray",
        "crosshair",
        "headshot",
        "accuracy",
        "recoil",
        "flick",
        "tracking",
        "sens",
        "sensitivity",
    ],
}

SYSTEM_PROMPT_TEMPLATE = """\
You are an expert CS2 tactical coach in an interactive session with a player.

Player context:
{player_context}

Guidelines:
- Be specific, actionable, and encouraging.
- Reference the player's actual stats and recent coaching insights when relevant.
- If the player asks about positioning, utility, economy, or aim, give concrete examples.
- Keep responses concise (2-4 sentences for simple questions, up to a short paragraph for complex ones).
- When referencing pro players or techniques, be specific about what to do.
- Do NOT repeat raw numbers — interpret and explain them.
- If you don't have enough information to answer, say so honestly.\
"""


class CoachingDialogueEngine:
    """Multi-turn coaching dialogue with RAG-augmented responses."""

    MAX_CONTEXT_TURNS = 6
    RETRIEVAL_TOP_K = 3

    def __init__(self):
        self._llm = get_llm_service()
        self._player_context: Dict = {}
        self._system_prompt: str = ""
        self._history: List[Dict[str, str]] = []
        self._session_active: bool = False
        # C-06: Protect mutable session state from concurrent UI thread access
        self._state_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        player_name: str,
        demo_name: Optional[str] = None,
    ) -> str:
        """Load player context and return an opening coaching message."""
        with self._state_lock:
            self._player_context = self._build_player_context(player_name, demo_name)
            self._system_prompt = self._build_system_prompt()
            self._history = []
            self._session_active = True

            opening = self._generate_opening()
            self._history.append({"role": "assistant", "content": opening})
            logger.info("Dialogue session started for player=%s", player_name)
            return opening

    def respond(self, user_message: str) -> str:
        """Process a user question and return a coaching response."""
        with self._state_lock:
            if not self._session_active:
                return self._fallback_response(user_message, self._classify_intent(user_message))

            intent = self._classify_intent(user_message)
            retrieval_context = self._retrieve_context(user_message, intent)

            # Build the augmented user message with retrieval context
            augmented_user = user_message
            if retrieval_context:
                augmented_user = (
                    f"{user_message}\n\n"
                    f"[Retrieved coaching knowledge for reference — "
                    f"use if relevant, ignore if not]\n{retrieval_context}"
                )

            # Build message array for Ollama (sliding window — history NOT yet mutated)
            messages = self._build_chat_messages(augmented_user)

            # F5-06: append user message only after we have a valid response so that
            # an LLM exception cannot leave the history in an inconsistent state.
            try:
                response = self._llm.chat(messages, system_prompt=self._system_prompt)
            except Exception as exc:
                logger.error("LLM chat raised an exception: %s", exc)
                response = self._fallback_response(user_message, intent)

            # Check for LLM error markers → fall back
            if response.startswith("[LLM"):
                logger.warning("LLM error in dialogue: %s", response)
                response = self._fallback_response(user_message, intent)

            # Safe to append now that we have a usable response
            self._history.append({"role": "user", "content": user_message})
            self._history.append({"role": "assistant", "content": response})
            return response

    def get_history(self) -> List[Dict[str, str]]:
        """Return the full conversation history."""
        with self._state_lock:
            return list(self._history)

    def clear_session(self):
        """Reset the dialogue session."""
        with self._state_lock:
            self._history = []
            self._player_context = {}
            self._session_active = False
            logger.info("Dialogue session cleared")

    @property
    def is_available(self) -> bool:
        """True when Ollama is reachable."""
        return self._llm.is_available()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_player_context(self, player_name: str, demo_name: Optional[str]) -> Dict:
        """Fetch recent coaching insights and stats from DB."""
        context: Dict = {"player_name": player_name, "demo_name": demo_name}

        try:
            db = get_db_manager()
            with db.get_session() as session:
                stmt = (
                    select(CoachingInsight)
                    .where(CoachingInsight.player_name == player_name)
                    .order_by(desc(CoachingInsight.created_at))
                    .limit(5)
                )
                recent_insights = session.exec(stmt).all()

                if recent_insights:
                    context["recent_insights"] = [
                        {
                            "title": i.title,
                            "focus_area": i.focus_area,
                            "severity": i.severity,
                            "message": i.message[:200],
                        }
                        for i in recent_insights
                    ]
                    # Identify recurring focus areas
                    areas = [i.focus_area for i in recent_insights]
                    context["primary_focus"] = max(set(areas), key=areas.count)
        except Exception as exc:
            logger.warning("Failed to load player context: %s", exc)

        return context

    def _build_system_prompt(self) -> str:
        """Create system prompt with player context embedded."""
        parts = [f"Player: {self._player_context.get('player_name', 'Unknown')}"]

        if self._player_context.get("demo_name"):
            parts.append(f"Current demo: {self._player_context['demo_name']}")

        if self._player_context.get("primary_focus"):
            parts.append(f"Primary improvement area: {self._player_context['primary_focus']}")

        insights = self._player_context.get("recent_insights", [])
        if insights:
            parts.append("Recent coaching insights:")
            for ins in insights[:3]:
                parts.append(f"  - [{ins['severity']}] {ins['title']}: " f"{ins['message'][:120]}")

        player_context_str = "\n".join(parts)
        return SYSTEM_PROMPT_TEMPLATE.format(player_context=player_context_str)

    def _classify_intent(self, message: str) -> str:
        """Keyword-based intent classification for retrieval routing."""
        message_lower = message.lower()
        scores: Dict[str, int] = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            scores[intent] = sum(1 for kw in keywords if kw in message_lower)
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best if scores[best] > 0 else "general"

    def _retrieve_context(self, user_message: str, intent: str) -> str:
        """Retrieve RAG knowledge and experiences relevant to the question."""
        blocks: List[str] = []

        # RAG tactical knowledge
        category = intent if intent != "general" else None
        try:
            from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeRetriever

            retriever = KnowledgeRetriever()
            entries = retriever.retrieve(
                query=user_message,
                top_k=self.RETRIEVAL_TOP_K,
                category=category,
            )
            if entries:
                rag_lines = ["Tactical knowledge:"]
                for e in entries:
                    rag_lines.append(f"- {e.title}: {e.description}")
                blocks.append("\n".join(rag_lines))
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)

        # Experience Bank
        try:
            from Programma_CS2_RENAN.backend.knowledge.experience_bank import (
                ExperienceContext,
                get_experience_bank,
            )

            bank = get_experience_bank()  # Singleton — avoids re-loading SBERT model (F5-04)
            map_name = self._player_context.get("map_name", "unknown")
            ctx = ExperienceContext(
                map_name=map_name,
                round_phase=self._player_context.get("round_phase", "unknown"),
                side=self._player_context.get("side", "unknown"),
            )
            experiences = bank.retrieve_similar(ctx, top_k=self.RETRIEVAL_TOP_K)
            if experiences:
                exp_lines = ["Similar experiences:"]
                for exp in experiences:
                    source = f"(pro: {exp.pro_player_name})" if exp.pro_player_name else ""
                    exp_lines.append(
                        f"- {exp.action_taken} → {exp.outcome} " f"on {exp.map_name} {source}"
                    )
                blocks.append("\n".join(exp_lines))
        except Exception as exc:
            logger.warning("Experience Bank retrieval failed: %s", exc)

        return "\n\n".join(blocks)

    def _build_chat_messages(self, augmented_user: str) -> List[Dict[str, str]]:
        """Build message array for Ollama with sliding context window."""
        # Take the last MAX_CONTEXT_TURNS * 2 messages from history
        # (excluding the user message we just appended — it goes in augmented form)
        window_size = self.MAX_CONTEXT_TURNS * 2
        # History already has the user message appended; slice before it
        prior = self._history[:-1][-window_size:]

        messages: List[Dict[str, str]] = list(prior)
        messages.append({"role": "user", "content": augmented_user})
        return messages

    def _generate_opening(self) -> str:
        """Generate a session opening message."""
        if not self._llm.is_available():
            return self._offline_opening()

        prompt_parts = ["Greet the player briefly and offer to help with their gameplay."]
        insights = self._player_context.get("recent_insights", [])
        if insights:
            focus = self._player_context.get("primary_focus", "gameplay")
            prompt_parts.append(
                f"Mention that you've noticed their recent coaching focused on "
                f"'{focus}' and ask if they'd like to dig deeper into that."
            )

        messages = [{"role": "user", "content": " ".join(prompt_parts)}]
        response = self._llm.chat(messages, system_prompt=self._system_prompt)

        if response.startswith("[LLM"):
            return self._offline_opening()
        return response

    def _offline_opening(self) -> str:
        """Opening message when Ollama is unavailable."""
        name = self._player_context.get("player_name", "player")
        focus = self._player_context.get("primary_focus")
        msg = (
            f"[Offline Coach] Hey {name}! I can help with your CS2 gameplay. "
            f"I'm running in offline mode — my answers will be based on the "
            f"tactical knowledge base."
        )
        if focus:
            msg += f" Your recent coaching focused on {focus}."
        msg += " What would you like to work on?"
        return msg

    def _fallback_response(self, user_message: str, intent: str) -> str:
        """Template-based response when Ollama is unavailable."""
        # Try to at least provide RAG knowledge
        retrieval = self._retrieve_context(user_message, intent)
        if retrieval:
            return (
                f"[Offline Coach] Here's what I found in the knowledge base:\n\n"
                f"{retrieval}\n\n"
                f"Start Ollama for a more interactive coaching experience."
            )
        return (
            "[Offline Coach] I don't have specific knowledge on that topic yet. "
            "Try asking about positioning, utility, economy, or aim. "
            "Start Ollama for full interactive coaching."
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_engine: Optional[CoachingDialogueEngine] = None
_engine_lock = threading.Lock()


def get_dialogue_engine() -> CoachingDialogueEngine:
    """Get or create the global CoachingDialogueEngine singleton (thread-safe)."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            _engine = CoachingDialogueEngine()
    return _engine
