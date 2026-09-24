from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET
import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ContentItem, ContentOpportunity, ResearchSource, UserProfile
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.gemini_service import ModelRouterService


class ResearchService:
    """Real-time research and evidence discovery using Gemini Google Search grounding."""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def _live_sources(self, profile: UserProfile, requested_topic: str | None) -> list[dict]:
        queries = []
        if requested_topic:
            queries.append(requested_topic)
        if profile.industry:
            queries.append(f"{profile.industry} technology business")
        if profile.brand_positioning:
            queries.append(profile.brand_positioning)
        if not queries:
            queries = ["technology business leadership AI"]

        items: list[dict] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "BrandOS/1.0"}) as client:
            for query in queries[:3]:
                url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-IN&gl=IN&ceid=IN:en"
                response = await client.get(url)
                response.raise_for_status()
                root = ET.fromstring(response.text)
                for node in root.findall("./channel/item")[:8]:
                    title = (node.findtext("title") or "").strip()
                    link = (node.findtext("link") or "").strip()
                    pub = (node.findtext("pubDate") or "").strip()
                    source_node = node.find("source")
                    source_name = (source_node.text or "").strip() if source_node is not None else ""
                    if not title or not link or link in seen:
                        continue
                    seen.add(link)
                    items.append({"title": title, "url": link, "published_at": pub, "source": source_name, "query": query})
        return items[:20]

    async def _gdelt_sources(self, profile: UserProfile, requested_topic: str | None) -> list[dict]:
        queries: list[str] = []
        if requested_topic:
            queries.append(requested_topic)
        if profile.industry:
            queries.append(f"{profile.industry} technology business")
        if profile.brand_positioning:
            queries.append(profile.brand_positioning)
        if not queries:
            queries = ["technology business leadership AI"]

        items: list[dict] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "BrandOS/1.0"},
        ) as client:
            for query in queries[:3]:
                url = (
                    "https://api.gdeltproject.org/api/v2/doc/doc?"
                    + "query=" + quote_plus(query)
                    + "&mode=artlist&maxrecords=10&timespan=7d&sort=datedesc&format=json"
                )
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                for article in (data.get("articles") or [])[:10]:
                    link = str(article.get("url") or "").strip()
                    title = str(article.get("title") or "").strip()
                    if not link.startswith(("https://", "http://")) or not title or link in seen:
                        continue
                    seen.add(link)
                    items.append({
                        "title": title,
                        "url": link,
                        "published_at": str(article.get("seendate") or ""),
                        "source": str(article.get("domain") or ""),
                        "query": query,
                    })
        return items[:20]

    async def research_and_rank(
        self,
        *,
        profile_id: int = 1,
        requested_topic: str | None = None,
        candidate_limit: int = 8,
    ) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required for live research.")

        profile = await self.session.get(UserProfile, profile_id)
        if profile is None:
            raise ValueError("Profile is not initialized.")

        brand = BrandIntelligenceService(self.session)
        context = await brand.generation_context(profile_id)
        historical = await brand.get_posts(profile_id, limit=12)
        recent_content_result = await self.session.execute(
            select(ContentItem.topic, ContentItem.created_at).order_by(ContentItem.created_at.desc()).limit(20)
        )
        recent_content = [{"topic": row[0], "created_at": row[1].isoformat() if row[1] else None} for row in recent_content_result.all()]

        source_errors: list[str] = []
        try:
            live_sources = await self._live_sources(profile, requested_topic)
        except Exception as exc:
            source_errors.append(f"Google News RSS: {exc}")
            live_sources = []

        if not live_sources:
            try:
                live_sources = await self._gdelt_sources(profile, requested_topic)
            except Exception as exc:
                source_errors.append(f"GDELT: {exc}")
                live_sources = []

        if not live_sources:
            raise RuntimeError("Live source discovery failed. " + " | ".join(source_errors))

        prompt = json.dumps({
            "date": datetime.now(timezone.utc).date().isoformat(),
            "profile": {
                "title": profile.professional_title,
                "industry": profile.industry,
                "audience": profile.audience,
                "goals": profile.goals,
                "positioning": profile.brand_positioning,
            },
            "brand_intelligence": context["brand_memory"],
            "recent_historical_posts": [p.body[:1200] for p in historical],
            "recent_content_topics": recent_content,
            "requested_topic": requested_topic,
            "candidate_limit": candidate_limit,
            "live_sources": live_sources,
        }, ensure_ascii=False)

        system = """You are the live research and content-opportunity engine for a professional LinkedIn personal-brand system.

You are given current public-news RSS results collected immediately before this request. Use only the supplied sources as current evidence. Prioritize credible, primary or authoritative sources when the source list contains them.

Hard rules:
- Never invent a personal experience, credential, client, employer, metric or opinion.
- Do not recommend a topic merely because it is popular.
- Prefer developments where the user's documented expertise gives them a useful lens.
- Penalize topics already covered in recent content or historical posts.
- Distinguish facts from interpretation.
- If evidence is weak, say so and lower evidence_strength.
- Do not make political persuasion content or infer political preferences.
- Return JSON only.

Return:
{"opportunities":[{"title":"","topic":"","angle":"","pillar":"","format":"","objective":"","why_now":"","evidence_summary":"","source_hints":[],"source_urls":[],"brand_fit":0,"audience_relevance":0,"timeliness":0,"evidence_strength":0,"novelty":0,"conversation_potential":0,"authenticity":0,"risk":0,"rationale":""}]}

Generate 6-8 genuinely different opportunities. Every opportunity must cite at least one supplied source URL in source_urls.
"""

        data = await ModelRouterService().generate_json(system, prompt, max_output_tokens=3600)
        opportunities = data.get("opportunities") or []
        created: list[dict] = []
        source_by_url = {item["url"]: item for item in live_sources}

        for raw in opportunities:
            try:
                scores = {
                    key: max(0.0, min(100.0, float(raw.get(key, 0) or 0)))
                    for key in ("brand_fit","audience_relevance","timeliness","evidence_strength","novelty","conversation_potential","authenticity","risk")
                }
                total = (
                    scores["brand_fit"] * 0.22 + scores["audience_relevance"] * 0.18 +
                    scores["timeliness"] * 0.15 + scores["evidence_strength"] * 0.15 +
                    scores["novelty"] * 0.12 + scores["conversation_potential"] * 0.08 +
                    scores["authenticity"] * 0.07 - scores["risk"] * 0.03
                )
                if scores["evidence_strength"] < 55 or scores["brand_fit"] < 55:
                    total *= 0.75

                urls = [str(u).strip() for u in (raw.get("source_urls") or []) if str(u).strip()]
                linked_sources = [source_by_url[u] for u in urls if u in source_by_url][:5]
                if not linked_sources:
                    linked_sources = live_sources[:1]

                records = []
                for source in linked_sources:
                    record = ResearchSource(
                        profile_id=profile_id,
                        topic=str(raw.get("topic") or requested_topic or "live brand opportunity"),
                        title=source["title"][:500],
                        url=source["url"],
                        domain=urlparse(source["url"]).netloc.lower() or None,
                        source_type="public_news_rss",
                        evidence_json=json.dumps({"published_at": source["published_at"], "source": source["source"]}, ensure_ascii=False),
                        search_queries_json=json.dumps([source["query"]], ensure_ascii=False),
                        confidence="medium",
                    )
                    self.session.add(record)
                    records.append(record)
                await self.session.flush()

                opportunity = ContentOpportunity(
                    profile_id=profile_id,
                    title=str(raw.get("title") or raw.get("topic") or "Untitled opportunity")[:300],
                    topic=str(raw.get("topic") or "")[:500],
                    angle=str(raw.get("angle") or ""),
                    pillar=str(raw.get("pillar") or "Industry insights")[:100],
                    format=str(raw.get("format") or "Insight post")[:100],
                    objective=str(raw.get("objective") or "")[:300],
                    status="RANKED",
                    **scores,
                    total_score=round(total, 2),
                    rationale=str(raw.get("rationale") or ""),
                    research_source_ids_json=json.dumps([s.id for s in records], ensure_ascii=False),
                    evidence_json=json.dumps({
                        "why_now": raw.get("why_now"),
                        "summary": raw.get("evidence_summary"),
                        "source_hints": raw.get("source_hints") or [],
                        "source_urls": [s["url"] for s in linked_sources],
                    }, ensure_ascii=False),
                )
                self.session.add(opportunity)
                created.append({
                    "title": opportunity.title, "topic": opportunity.topic, "angle": opportunity.angle,
                    "pillar": opportunity.pillar, "format": opportunity.format, "objective": opportunity.objective,
                    "total_score": opportunity.total_score, "scores": scores, "rationale": opportunity.rationale,
                    "evidence": json.loads(opportunity.evidence_json or "{}"),
                    "source_ids": [s.id for s in records],
                    "sources": [{"title": s.title, "url": s.url, "domain": s.domain} for s in records],
                })
            except (TypeError, ValueError):
                continue

        await self.session.commit()
        created.sort(key=lambda item: item["total_score"], reverse=True)
        return created

    async def list_opportunities(self, profile_id: int = 1, limit: int = 20) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required.")
        result = await self.session.execute(
            select(ContentOpportunity)
            .where(ContentOpportunity.profile_id == profile_id)
            .order_by(ContentOpportunity.total_score.desc(), ContentOpportunity.created_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        return [self.serialize(item) for item in result.scalars().all()]

    def serialize(self, item: ContentOpportunity) -> dict:
        return {
            "id": item.id,
            "title": item.title,
            "topic": item.topic,
            "angle": item.angle,
            "pillar": item.pillar,
            "format": item.format,
            "objective": item.objective,
            "status": item.status,
            "total_score": item.total_score,
            "scores": {
                "brand_fit": item.brand_fit,
                "audience_relevance": item.audience_relevance,
                "timeliness": item.timeliness,
                "evidence_strength": item.evidence_strength,
                "novelty": item.novelty,
                "conversation_potential": item.conversation_potential,
                "authenticity": item.authenticity,
                "risk": item.risk,
            },
            "rationale": item.rationale,
            "evidence": json.loads(item.evidence_json or "{}"),
            "source_ids": json.loads(item.research_source_ids_json or "[]"),
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def build_evidence_pack(self, topic: str, audience: str, sources: list[dict]) -> dict:
        facts = [
            {
                "claim": source.get("summary", "Public source suggests this is relevant."),
                "source_title": source.get("title", "Source"),
                "source_url": source.get("url", ""),
            }
            for source in sources
        ]
        return {
            "topic": topic,
            "audience": audience,
            "facts": facts,
            "sources": sources,
            "confidence": "medium",
            "notes": "Use only as supporting context; validate claims before publishing.",
        }
