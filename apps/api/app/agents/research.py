from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET
import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ContentItem, ContentOpportunity, ResearchSource, UserProfile
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.gemini_service import ModelRouterService
from app.services.brand_learning import BrandLearningService




_RESEARCH_TARGET = 10
_RESEARCH_SOURCE_POOL = 48
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "that", "the", "their", "this",
    "to", "with", "your", "you", "my", "our", "how", "what", "why", "when",
}


def _tokens(value: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    tokens: set[str] = set()
    for word in words:
        if len(word) < 3 or word in _STOP_WORDS:
            continue
        tokens.add(word)
        if len(word) >= 7:
            tokens.add(word[:6])
    return tokens


def _weighted_profile_terms(profile: UserProfile, brand_memory: dict, learning_memory: dict, requested_topic: str | None) -> dict[str, float]:
    fields = [
        (profile.professional_title, 3.0),
        (profile.industry, 3.0),
        (requested_topic, 4.0),
        (brand_memory.get("summary"), 1.5),
    ]
    identity = brand_memory.get("identity") or {}
    if isinstance(identity, dict):
        fields.extend((value, 2.5) for values in identity.values() if isinstance(values, list) for value in values)
    expertise = brand_memory.get("expertise") or []
    if isinstance(expertise, list):
        fields.extend(((item.get("area") or ""), 3.0) for item in expertise if isinstance(item, dict))
    themes = brand_memory.get("themes") or []
    if isinstance(themes, list):
        fields.extend(((item.get("theme") or ""), 2.0) for item in themes if isinstance(item, dict))
    memories = learning_memory.get("memories") or []
    if isinstance(memories, list):
        fields.extend(((item.get("content") or ""), 2.0) for item in memories if isinstance(item, dict))
    semantic = (learning_memory.get("semantic_matches") or {}).get("memories", [])
    if isinstance(semantic, list):
        fields.extend(((item.get("content") or ""), 1.5) for item in semantic if isinstance(item, dict))

    weighted: dict[str, float] = {}
    for value, weight in fields:
        for token in _tokens(value):
            weighted[token] = max(weighted.get(token, 0.0), weight)
    return weighted


def _profile_relevance(candidate: dict, profile_terms: dict[str, float], requested_topic: str | None) -> float:
    candidate_text = " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "topic", "angle", "pillar", "objective")
    )
    candidate_tokens = _tokens(candidate_text)
    if not profile_terms or not candidate_tokens:
        return 0.0

    total_weight = sum(profile_terms.values())
    matched_weight = sum(weight for token, weight in profile_terms.items() if token in candidate_tokens)
    base = matched_weight / total_weight if total_weight else 0.0

    requested_tokens = _tokens(requested_topic)
    requested_match = (
        len(requested_tokens & candidate_tokens) / len(requested_tokens)
        if requested_tokens else 0.0
    )
    anchor_bonus = min(0.18, 0.06 * max(0, len(profile_terms.keys() & candidate_tokens) - 1))
    score = (base * 0.78) + (requested_match * 0.22) + anchor_bonus
    return round(max(0.0, min(100.0, score * 100.0)), 1)


def _candidate_similarity(left: dict, right: dict) -> float:
    a = _tokens(" ".join(str(left.get(k) or "") for k in ("title", "topic")))
    b = _tokens(" ".join(str(right.get(k) or "") for k in ("title", "topic")))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ResearchService:
    """Real-time research and evidence discovery with durable multi-provider AI."""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def _live_sources(self, profile: UserProfile, requested_topic: str | None, learned_queries: list[str] | None = None) -> list[dict]:
        queries = []
        if requested_topic:
            queries.append(requested_topic)
        if profile.industry:
            queries.append(f"{profile.industry} technology business")
        if profile.professional_title:
            queries.append(profile.professional_title)
        if profile.experience_years is not None:
            queries.append(f"{profile.industry or 'professional'} {profile.experience_years:g} years experience")
        for learned in (learned_queries or [])[:4]:
            if learned and learned not in queries:
                queries.append(learned)
        if not queries:
            queries = ["technology business leadership AI"]

        async def fetch_query(client: httpx.AsyncClient, query: str) -> list[dict]:
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-IN&gl=IN&ceid=IN:en"
            response = await client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items: list[dict] = []
            for node in root.findall("./channel/item")[:6]:
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                pub = (node.findtext("pubDate") or "").strip()
                source_node = node.find("source")
                source_name = (source_node.text or "").strip() if source_node is not None else ""
                if title and link:
                    items.append({"title": title, "url": link, "published_at": pub, "source": source_name, "query": query})
            return items

        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, headers={"User-Agent": "BrandOS/1.0"}) as client:
            batches = await asyncio.gather(*(fetch_query(client, query) for query in queries[:4]), return_exceptions=True)

        seen: set[str] = set()
        items: list[dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            for item in batch:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    items.append(item)
        return items[:32]

    async def _gdelt_sources(self, profile: UserProfile, requested_topic: str | None, learned_queries: list[str] | None = None) -> list[dict]:
        queries: list[str] = []
        if requested_topic:
            queries.append(requested_topic)
        if profile.industry:
            queries.append(f"{profile.industry} technology business")
        if profile.professional_title:
            queries.append(profile.professional_title)
        if profile.experience_years is not None:
            queries.append(f"{profile.industry or 'professional'} {profile.experience_years:g} years experience")
        for learned in (learned_queries or [])[:2]:
            if learned and learned not in queries:
                queries.append(learned)
        if not queries:
            queries = ["technology business leadership AI"]

        async def fetch_query(client: httpx.AsyncClient, query: str) -> list[dict]:
            url = (
                "https://api.gdeltproject.org/api/v2/doc/doc?"
                + "query=" + quote_plus(query)
                + "&mode=artlist&maxrecords=8&timespan=7d&sort=datedesc&format=json"
            )
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "title": str(article.get("title") or "").strip(),
                    "url": str(article.get("url") or "").strip(),
                    "published_at": str(article.get("seendate") or ""),
                    "source": str(article.get("domain") or ""),
                    "query": query,
                }
                for article in (data.get("articles") or [])[:8]
                if str(article.get("url") or "").startswith(("https://", "http://")) and str(article.get("title") or "").strip()
            ]

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers={"User-Agent": "BrandOS/1.0"}) as client:
            batches = await asyncio.gather(*(fetch_query(client, query) for query in queries[:4]), return_exceptions=True)

        seen: set[str] = set()
        items: list[dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            for item in batch:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    items.append(item)
        return items[:32]

    async def _source_context(self, client: httpx.AsyncClient, source: dict) -> dict:
        """Fetch a small, source-grounded text excerpt for research summaries.

        This deliberately stays dependency-free: it uses the standard library to
        remove obvious HTML chrome and keeps the excerpt small enough for the
        ranking prompt. If a publisher blocks extraction, the original URL and
        metadata remain usable.
        """
        url = str(source.get("url") or "").strip()
        if not url:
            return source

        try:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                return source

            raw = response.text[:500_000]
            raw = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
            paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw)
            text_parts = []
            for paragraph in paragraphs:
                cleaned = re.sub(r"(?is)<[^>]+>", " ", paragraph)
                cleaned = html.unescape(cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if len(cleaned) >= 50:
                    text_parts.append(cleaned)
                if sum(len(item) for item in text_parts) >= 6000:
                    break

            excerpt = " ".join(text_parts)[:6000].strip()
            if not excerpt:
                description_match = re.search(
                    r'(?is)<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
                    raw,
                )
                excerpt = html.unescape(description_match.group(1)).strip() if description_match else ""

            canonical_url = str(response.url) or url
            if excerpt:
                return source | {"url": canonical_url, "source_excerpt": excerpt}
            if canonical_url and canonical_url != url:
                return source | {"url": canonical_url}
        except Exception:
            pass
        return source

    async def _enrich_source_context(self, sources: list[dict]) -> list[dict]:
        if not sources:
            return sources
        async with httpx.AsyncClient(
            timeout=2.5,
            follow_redirects=True,
            headers={"User-Agent": "BrandOS/1.0"},
        ) as client:
            enrichable = sources[:4]
            results = await asyncio.gather(
                *(self._source_context(client, source) for source in enrichable),
                return_exceptions=True,
            )
        enriched = []
        for source, result in zip(enrichable, results):
            enriched.append(result if isinstance(result, dict) else source)
        return enriched + sources[len(enrichable):]

    async def research_and_rank(
        self,
        *,
        profile_id: int,
        requested_topic: str | None = None,
        candidate_limit: int = _RESEARCH_TARGET,
    ) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required for live research.")

        profile = await self.session.get(UserProfile, profile_id)
        if profile is None:
            raise ValueError("Profile is not initialized.")

        brand = BrandIntelligenceService(self.session)
        context = await brand.generation_context(profile_id, query=requested_topic or "current topics relevant to my professional brand")
        historical = await brand.get_posts(profile_id, limit=12)
        learning_memory = context.get("learning_memory") or {}
        learned_queries = [
            str(item.get("content") or "").strip()[:240]
            for item in (learning_memory.get("memories") or [])
            if item.get("type") in {"topic", "interest"} and str(item.get("content") or "").strip()
        ][:2]
        semantic_interest_queries = [
            str(item.get("content") or "").strip()[:240]
            for item in (learning_memory.get("semantic_matches") or {}).get("memories", [])
            if str(item.get("content") or "").strip()
        ][:2]
        learned_queries = list(dict.fromkeys(learned_queries + semantic_interest_queries))[:3]
        recent_content_result = await self.session.execute(
            select(ContentItem.topic, ContentItem.created_at)
            .where(ContentItem.profile_id == profile_id)
            .order_by(ContentItem.created_at.desc())
            .limit(20)
        )
        recent_content = [{"topic": row[0], "created_at": row[1].isoformat() if row[1] else None} for row in recent_content_result.all()]

        brand_memory = context.get("brand_memory") or {}
        profile_terms = _weighted_profile_terms(profile, brand_memory, learning_memory, requested_topic)
        source_errors: list[str] = []
        google_task = asyncio.create_task(self._live_sources(profile, requested_topic, learned_queries))
        gdelt_task = asyncio.create_task(self._gdelt_sources(profile, requested_topic, learned_queries))
        google_result, gdelt_result = await asyncio.gather(google_task, gdelt_task, return_exceptions=True)

        live_sources: list[dict] = []
        for label, result in (("Google News RSS", google_result), ("GDELT", gdelt_result)):
            if isinstance(result, Exception):
                source_errors.append(f"{label}: {result}")
                continue
            live_sources.extend(result)

        deduped_sources: list[dict] = []
        seen_urls: set[str] = set()
        for source in live_sources:
            if source["url"] not in seen_urls:
                seen_urls.add(source["url"])
                deduped_sources.append(source)
        # Keep live research responsive on mobile and serverless runtimes.
        # RSS/GDELT metadata is already sufficient for fallback evidence, while
        # only a small set of sources needs article-body enrichment for ranking.
        live_sources = deduped_sources[:_RESEARCH_SOURCE_POOL]
        live_sources = await self._enrich_source_context(live_sources)

        if requested_topic:
            await BrandLearningService(self.session).record_event(
                profile_id=profile_id,
                event_type="RESEARCH_QUERY",
                source_type="research",
                source_id=f"{datetime.now(timezone.utc).date().isoformat()}:{requested_topic.strip().lower()[:220]}",
                content=requested_topic.strip(),
                metadata={"explicit_user_query": True},
            )

        if not live_sources:
            # Do not turn a temporary public-feed outage into a hard Research failure.
            # Return the latest persisted opportunities so the workspace remains usable.
            cached = await self.list_opportunities(profile_id, min(candidate_limit, _RESEARCH_TARGET))
            if cached:
                return cached
            raise RuntimeError("Live source discovery failed. " + " | ".join(source_errors))

        prompt = json.dumps({
            "date": datetime.now(timezone.utc).date().isoformat(),
            "profile": {
                "title": profile.professional_title,
                "industry": profile.industry,
                "experience_years": profile.experience_years,
                "tone": profile.tone,
            },
            "brand_intelligence": context["brand_memory"],
            "recent_historical_posts": [p.body[:600] for p in historical[:6]],
            "recent_content_topics": recent_content[:10],
            "requested_topic": requested_topic,
            "candidate_limit": max(_RESEARCH_TARGET, candidate_limit),
            "live_sources": [
                {key: value for key, value in source.items() if key != "source_excerpt" or value}
                for source in live_sources[:_RESEARCH_SOURCE_POOL]
            ],
        }, ensure_ascii=False)

        system = """You are the live research and content-opportunity engine for a professional LinkedIn personal-brand system.

You are given current public-news RSS results collected immediately before this request. Use only the supplied sources as current evidence. Prioritize credible, primary or authoritative sources when the source list contains them.

Hard rules:
- Never invent a personal experience, credential, client, employer, metric or opinion.
- Do not recommend a topic merely because it is popular.
- Prefer developments where the user's documented expertise gives them a useful lens.
- Use learning_memory to understand recurring interests and avoid stale or repetitive suggestions.
- A research query signals interest, not belief. Never turn research activity into a claimed opinion.
- Penalize topics already covered in recent content or historical posts.
- Distinguish facts from interpretation.
- If evidence is weak, say so and lower evidence_strength.
- Do not make political persuasion content or infer political preferences.
- Return JSON only.

Return:
{"opportunities":[{"title":"","topic":"","angle":"","pillar":"","format":"","objective":"","why_now":"","evidence_summary":"","source_hints":[],"source_urls":[],"brand_fit":0,"context_relevance":0,"timeliness":0,"evidence_strength":0,"novelty":0,"conversation_potential":0,"authenticity":0,"risk":0,"rationale":""}]}

Generate 12-16 genuinely different opportunities so the application can independently score, deduplicate and select the strongest 10. Every opportunity must cite at least one supplied source URL in source_urls. For evidence_summary, write one useful 80-120 word paragraph explaining what the supplied source says and why it matters. Only use claims supported by the supplied source excerpt or metadata. If no article text was available, be explicit that the summary is based on the available source metadata rather than inventing details.
"""

        try:
            data = await asyncio.wait_for(
                ModelRouterService().generate_json(system, prompt, max_output_tokens=3600, task="research"),
                timeout=12.0,
            )
            opportunities = data.get("opportunities") or []
        except Exception:
            # Research should remain useful even when a configured LLM provider
            # is temporarily unavailable. The public source feed is still valid
            # evidence, so create deterministic source-grounded candidates and
            # mark them as fallback opportunities instead of failing the request.
            opportunities = [
                {
                    "title": source["title"][:180],
                    "topic": source["title"][:300],
                    "angle": f"What this development means for professionals working in {profile.industry or 'technology and business'}",
                    "pillar": "Industry insights",
                    "format": "Insight post",
                    "objective": "Build informed professional visibility",
                    "why_now": "This item appeared in the live public source feed during the research run.",
                    "evidence_summary": (source.get("source_excerpt") or source["title"])[:900],
                    "source_hints": [source.get("source") or source.get("domain") or ""],
                    "source_urls": [source["url"]],
                    "brand_fit": 62,
                    "context_relevance": 60,
                    "timeliness": 82,
                    "evidence_strength": 72,
                    "novelty": 58,
                    "conversation_potential": 55,
                    "authenticity": 60,
                    "risk": 20,
                    "rationale": "Deterministic fallback based only on a current public source because the configured ranking model was unavailable.",
                }
                for source in live_sources[:_RESEARCH_TARGET]
            ]
        created: list[dict] = []
        source_by_url = {item["url"]: item for item in live_sources}

        for raw in opportunities:
            try:
                brand_fit = _profile_relevance(raw, profile_terms, requested_topic)
                scores = {
                    "brand_fit": brand_fit,
                    "audience_relevance": max(0.0, min(100.0, float(raw.get("context_relevance", raw.get("audience_relevance", 0)) or 0))),
                    "timeliness": max(0.0, min(100.0, float(raw.get("timeliness", 0) or 0))),
                    "evidence_strength": max(0.0, min(100.0, float(raw.get("evidence_strength", 0) or 0))),
                    "novelty": max(0.0, min(100.0, float(raw.get("novelty", 0) or 0))),
                    "conversation_potential": max(0.0, min(100.0, float(raw.get("conversation_potential", 0) or 0))),
                    "authenticity": max(0.0, min(100.0, float(raw.get("authenticity", 0) or 0))),
                    "risk": max(0.0, min(100.0, float(raw.get("risk", 0) or 0))),
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

        ranked = sorted(created, key=lambda item: item["total_score"], reverse=True)
        selected: list[dict] = []
        for item in ranked:
            if any(_candidate_similarity(item, existing) >= 0.72 for existing in selected):
                continue
            selected.append(item)
            if len(selected) >= max(1, min(candidate_limit, _RESEARCH_TARGET)):
                break

        await self.session.commit()
        return selected

    async def list_opportunities(self, profile_id: int, limit: int = 20) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required.")
        result = await self.session.execute(
            select(ContentOpportunity)
            .where(ContentOpportunity.profile_id == profile_id)
            .order_by(ContentOpportunity.total_score.desc(), ContentOpportunity.created_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        items = list(result.scalars().all())
        source_ids: set[int] = set()
        for item in items:
            source_ids.update(
                int(source_id)
                for source_id in json.loads(item.research_source_ids_json or "[]")
                if str(source_id).isdigit()
            )

        sources_by_id: dict[int, ResearchSource] = {}
        if source_ids:
            source_result = await self.session.execute(
                select(ResearchSource).where(
                    ResearchSource.profile_id == profile_id,
                    ResearchSource.id.in_(source_ids),
                )
            )
            sources_by_id = {int(source.id): source for source in source_result.scalars().all()}

        serialized: list[dict] = []
        for item in items:
            item_sources = []
            for raw_id in json.loads(item.research_source_ids_json or "[]"):
                try:
                    source = sources_by_id.get(int(raw_id))
                except (TypeError, ValueError):
                    source = None
                if source is not None and source.url:
                    item_sources.append({
                        "title": source.title,
                        "url": source.url,
                        "domain": source.domain,
                    })
            serialized.append(self.serialize(item, sources=item_sources))
        return serialized

    def serialize(self, item: ContentOpportunity, sources: list[dict] | None = None) -> dict:
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
            "sources": sources or [],
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def build_evidence_pack(self, topic: str, sources: list[dict]) -> dict:
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
            "facts": facts,
            "sources": sources,
            "confidence": "medium",
            "notes": "Use only as supporting context; validate claims before publishing.",
        }
