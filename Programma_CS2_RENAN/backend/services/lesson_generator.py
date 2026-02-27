"""
Demo Lesson Generator

Generates educational coaching lessons from demo analysis using:
1. RAP model for tactical insights
2. LLM service for natural language explanation
3. Pro baseline comparisons for context

Usage:
    from lesson_generator import LessonGenerator
    generator = LessonGenerator()
    lesson = generator.generate_lesson(demo_path)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Programma_CS2_RENAN.backend.services.llm_service import check_ollama_status, get_llm_service

# F5-18: Named thresholds — no magic numbers in lesson generation logic.
_ADR_STRONG_THRESHOLD: float = 75.0       # ADR above this = "good impact"
_ADR_WEAK_THRESHOLD: float = 60.0         # ADR below this = needs improvement
_HS_STRONG_THRESHOLD: float = 0.40        # HS% above this = "strong aim"
_HS_WEAK_THRESHOLD: float = 0.35          # HS% below this = needs work
_RATING_ABOVE_AVG: float = 1.0            # Rating above this = above average
_KAST_STRONG_THRESHOLD: float = 0.70      # KAST above this = "consistent"
_DEATH_RATIO_WARNING: float = 1.5         # deaths > kills * this ratio = over-dying
_MIN_DEATHS_FOR_WARNING: int = 15         # Minimum deaths before ratio warning applies


class LessonGenerator:
    """Generates natural language coaching lessons from demo files."""

    def __init__(self):
        self.llm = get_llm_service()
        self._db = None  # Lazy-loaded database connection

    @property
    def db(self):
        """Lazy-load database connection."""
        if self._db is None:
            from Programma_CS2_RENAN.backend.storage.database import get_db_manager

            self._db = get_db_manager()
        return self._db

    def generate_lesson(self, demo_name: str, focus_area: Optional[str] = None) -> Dict[str, Any]:
        """Generate a complete lesson from a demo file.

        Args:
            demo_name: Name of the demo (without .dem extension)
            focus_area: Optional focus area (positioning, economy, aim, utility)

        Returns:
            Dict containing lesson structure with sections
        """
        # Get match stats for this demo
        match_data = self._get_match_data(demo_name)

        if not match_data:
            return {
                "status": "error",
                "message": f"No data found for demo: {demo_name}",
                "lesson": None,
            }

        # Build lesson structure
        lesson = {
            "demo_name": demo_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "focus_area": focus_area or "general",
            "sections": {},
        }

        # Generate each section
        lesson["sections"]["overview"] = self._generate_overview(match_data)
        lesson["sections"]["strengths"] = self._generate_strengths(match_data)
        lesson["sections"]["improvements"] = self._generate_improvements(match_data, focus_area)
        lesson["sections"]["pro_tips"] = self._generate_pro_tips(match_data, focus_area)

        # If LLM is available, enhance with natural language
        if self.llm.is_available():
            lesson["sections"]["coaching_narrative"] = self._generate_narrative(match_data)
        else:
            lesson["sections"]["coaching_narrative"] = {
                "available": False,
                "message": "Start Ollama for natural language coaching",
            }

        return {"status": "success", "lesson": lesson}

    def _get_match_data(self, demo_name: str) -> Optional[Dict[str, Any]]:
        """Fetch match data from database."""
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        with self.db.get_session() as session:
            stmt = select(PlayerMatchStats).where(PlayerMatchStats.demo_name == demo_name)
            result = session.exec(stmt).first()

            if result:
                return result.model_dump()

        return None

    def _generate_overview(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate match overview section."""
        return {
            "title": "Match Overview",
            "demo_name": match_data.get("demo_name", "Unknown"),
            "player_name": match_data.get("player_name", "Unknown"),
            "stats": {
                "kills": match_data.get("avg_kills", 0),
                "deaths": match_data.get("avg_deaths", 0),
                "adr": round(match_data.get("avg_adr", 0), 1),
                "rating": round(match_data.get("rating", 0), 2),
                "hs_percentage": round(match_data.get("avg_hs", 0) * 100, 1),
            },
        }

    def _generate_strengths(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Identify and highlight player strengths."""
        strengths = []

        # ADR above average
        adr = match_data.get("avg_adr", 0)
        if adr > _ADR_STRONG_THRESHOLD:
            strengths.append(
                {
                    "category": "Impact",
                    "stat": f"ADR: {adr:.1f}",
                    "message": "Good damage output - you're making your shots count",
                }
            )

        # HS percentage
        hs = match_data.get("avg_hs", 0)
        if hs > _HS_STRONG_THRESHOLD:
            strengths.append(
                {
                    "category": "Aim",
                    "stat": f"HS: {hs*100:.0f}%",
                    "message": "Strong headshot accuracy - keep prioritizing head-level crosshair",
                }
            )

        # KAST
        kast = match_data.get("avg_kast", 0)
        if kast > _KAST_STRONG_THRESHOLD:
            strengths.append(
                {
                    "category": "Consistency",
                    "stat": f"KAST: {kast*100:.0f}%",
                    "message": "You're contributing positively to most rounds",
                }
            )

        # Rating
        rating = match_data.get("rating", 0)
        if rating > _RATING_ABOVE_AVG:
            strengths.append(
                {
                    "category": "Overall",
                    "stat": f"Rating: {rating:.2f}",
                    "message": "Above average performance this match",
                }
            )

        return {
            "title": "Your Strengths",
            "items": (
                strengths
                if strengths
                else [
                    {
                        "category": "Growth Mindset",
                        "stat": "",
                        "message": "Every game is a learning opportunity - keep practicing!",
                    }
                ]
            ),
        }

    def _generate_improvements(
        self, match_data: Dict[str, Any], focus_area: Optional[str] = None
    ) -> Dict[str, Any]:
        """Identify areas for improvement."""
        improvements = []

        # Low ADR
        adr = match_data.get("avg_adr", 0)
        if adr < _ADR_WEAK_THRESHOLD:
            improvements.append(
                {
                    "category": "Impact",
                    "stat": f"ADR: {adr:.1f}",
                    "suggestion": "Focus on dealing damage even when not getting kills",
                    "drill": "Practice spray transfers in Aim Lab or workshop maps",
                }
            )

        # Low HS percentage
        hs = match_data.get("avg_hs", 0)
        if hs < _HS_WEAK_THRESHOLD:
            improvements.append(
                {
                    "category": "Aim",
                    "stat": f"HS: {hs*100:.0f}%",
                    "suggestion": "Work on crosshair placement at head level",
                    "drill": "Community FFA DM focusing only on one-taps",
                }
            )

        # Deaths too high
        deaths = match_data.get("avg_deaths", 0)
        kills = match_data.get("avg_kills", 0)
        if deaths > kills * _DEATH_RATIO_WARNING and deaths > _MIN_DEATHS_FOR_WARNING:
            improvements.append(
                {
                    "category": "Positioning",
                    "stat": f"K/D: {kills}/{deaths}",
                    "suggestion": "You're dying too often - consider safer positions",
                    "drill": "Watch where pros hold on this map",
                }
            )

        # Filter by focus area if specified
        if focus_area:
            improvements = [
                i for i in improvements if i["category"].lower() == focus_area.lower()
            ] or improvements[:1]

        return {
            "title": "Areas to Improve",
            "items": (
                improvements
                if improvements
                else [
                    {
                        "category": "Maintenance",
                        "stat": "",
                        "suggestion": "Solid fundamentals - focus on advanced utility usage",
                        "drill": "Learn 1-2 new smoke/flash lineups this week",
                    }
                ]
            ),
        }

    def _generate_pro_tips(
        self, match_data: Dict[str, Any], focus_area: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate contextual pro tips."""
        # Extract map name from demo_name (e.g. "match20260103_de_mirage" -> "mirage")
        demo = match_data.get("demo_name", "")
        map_name = ""
        for known_map in (
            "mirage",
            "inferno",
            "dust2",
            "ancient",
            "nuke",
            "anubis",
            "overpass",
            "vertigo",
        ):
            if known_map in demo.lower():
                map_name = known_map
                break

        tips = {
            "mirage": [
                "NaVi's s1mple often plays window aggro early - if you're dying mid, try this angle",
                "Learn the A-site smoke from T spawn - it's used in 90% of pro A executes",
            ],
            "inferno": [
                "FaZe ropz holds banana with minimal utility - watch his VODs for positioning",
                "The deep banana smoke from second mid can win you more rounds than aim alone",
            ],
            "dust2": [
                "Liquid's AWPer often peeks mid doors before the smoke - timing is everything",
                "CT side: retake kits are more valuable than your 4th flashbang",
            ],
            "ancient": [
                "The mid control battle is won by utility, not aim - study pro mid control",
                "A-site retakes are easier than B - consider your rotations carefully",
            ],
            "nuke": [
                "Outside plays are mind games - watch how pros jiggle A main",
                "The ramp smoke from T side can completely change the round dynamic",
            ],
        }

        general_tips = [
            "Economy wins matches - full save after a lost pistol round is almost always correct",
            "Pre-aim common angles - most duels are won before the crosshair moves",
            "Communication > Aim in team play - callouts win more rounds than frags",
        ]

        selected_tips = tips.get(map_name, general_tips)

        return {
            "title": "Pro Tips",
            "map_specific": map_name if map_name in tips else None,
            "tips": selected_tips[:2],  # Limit to avoid overwhelming
        }

    def _generate_narrative(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate natural language narrative using LLM."""
        # Prepare insights for LLM
        insights = {
            "player": match_data.get("player_name", "Player"),
            "demo": match_data.get("demo_name", "Unknown"),
            "kills": match_data.get("avg_kills", 0),
            "deaths": match_data.get("avg_deaths", 0),
            "adr": match_data.get("avg_adr", 0),
            "rating": match_data.get("rating", 0),
            "hs_percentage": match_data.get("avg_hs", 0),
            "kast": match_data.get("avg_kast", 0),
        }

        narrative = self.llm.generate_lesson(insights)

        return {"available": True, "content": narrative}

    def get_available_demos(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get list of demos available for lesson generation."""
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        with self.db.get_session() as session:
            stmt = (
                select(PlayerMatchStats)
                .where(PlayerMatchStats.is_pro == False)  # noqa: E712
                .order_by(PlayerMatchStats.processed_at.desc())
                .limit(limit)
            )

            results = session.exec(stmt).all()

            return [
                {
                    "demo_name": r.demo_name,
                    "player_name": r.player_name,
                    "rating": r.rating,
                    "processed_at": r.processed_at.isoformat() if r.processed_at else None,
                }
                for r in results
            ]


def check_lesson_system_status() -> Dict[str, Any]:
    """Check the overall status of the lesson generation system."""
    llm_status = check_ollama_status()

    # Check database connectivity
    db_ok = False
    demo_count = 0
    try:
        from sqlmodel import func, select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        db = get_db_manager()
        with db.get_session() as session:
            count = session.exec(select(func.count(PlayerMatchStats.id))).one()
            demo_count = count
            db_ok = True
    except Exception as e:
        db_ok = False

    return {
        "llm": llm_status,
        "database": {"connected": db_ok, "demo_count": demo_count},
        "ready": db_ok and demo_count > 0,  # LLM is optional but enhances experience
    }
