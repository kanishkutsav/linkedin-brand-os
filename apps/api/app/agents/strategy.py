from __future__ import annotations

from datetime import date, timedelta


class ContentStrategyService:
    """Owns content pillars, topic scoring, and recommended publishing mix."""

    default_pillars = [
        "Expertise",
        "Industry insights",
        "Lessons learned",
        "Personal experiences",
        "Case studies",
        "Educational content",
        "Opinions",
        "Leadership",
        "Career lessons",
        "Product and business insights",
    ]

    def recommend(self, goal: str, audience: str) -> dict:
        content_mix = [
            {"pillar": "Expertise", "weight": 0.32, "purpose": "Demonstrate subject-matter depth"},
            {"pillar": "Industry insights", "weight": 0.22, "purpose": "Align to current conversations"},
            {"pillar": "Lessons learned", "weight": 0.18, "purpose": "Build trust and authenticity"},
            {"pillar": "Case studies", "weight": 0.14, "purpose": "Translate outcomes into proof"},
            {"pillar": "Opinions", "weight": 0.14, "purpose": "Create differentiated viewpoints"},
        ]

        start = date.today()
        content_calendar = [
            {
                "date": (start + timedelta(days=1)).isoformat(),
                "topic": f"How {goal.lower()} actually works in practice",
                "pillar": "Expertise",
                "format": "Long-form insight",
                "audience": audience,
                "objective": "Build authority",
                "status": "IDEA",
            },
            {
                "date": (start + timedelta(days=3)).isoformat(),
                "topic": f"Three patterns I see in {audience.lower()}",
                "pillar": "Industry insights",
                "format": "Opinion post",
                "audience": audience,
                "objective": "Drive discussion",
                "status": "IDEA",
            },
            {
                "date": (start + timedelta(days=6)).isoformat(),
                "topic": "What I would do differently in a new cycle",
                "pillar": "Lessons learned",
                "format": "Reflective post",
                "audience": audience,
                "objective": "Increase relatability",
                "status": "IDEA",
            },
        ]

        return {
            "goal": goal,
            "audience": audience,
            "content_mix": content_mix,
            "content_calendar": content_calendar,
            "pillars": self.default_pillars,
        }
