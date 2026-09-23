from __future__ import annotations


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

        content_calendar = [
            {
                "date": "2026-09-25",
                "topic": f"How {goal.lower()} actually works in practice",
                "pillar": "Expertise",
                "format": "Long-form insight",
                "audience": audience,
                "objective": "Build authority",
                "status": "IDEA",
            },
            {
                "date": "2026-09-27",
                "topic": f"Three patterns I see in {audience.lower()}",
                "pillar": "Industry insights",
                "format": "Opinion post",
                "audience": audience,
                "objective": "Drive discussion",
                "status": "IDEA",
            },
            {
                "date": "2026-09-30",
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
