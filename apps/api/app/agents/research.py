from __future__ import annotations


class ResearchService:
    """Provides evidence packs, citations, and source-backed insight summaries."""

    def build_evidence_pack(self, topic: str, audience: str, sources: list[dict]) -> dict:
        facts = []
        for source in sources:
            facts.append(
                {
                    "claim": source.get("summary", "Public source suggests this is relevant."),
                    "source_title": source.get("title", "Source"),
                    "source_url": source.get("url", ""),
                }
            )

        return {
            "topic": topic,
            "audience": audience,
            "facts": facts,
            "sources": sources,
            "confidence": "medium",
            "notes": "Use only as supporting context; validate claims before publishing.",
        }
