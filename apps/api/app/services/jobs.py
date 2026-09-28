from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import JobSearchCache, ObservabilityEvent


def _clean_text(value: Any, limit: int = 4000) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _years_terms(years: float | None) -> list[str]:
    if years is None:
        return []
    if years < 2:
        return ["entry level", "junior"]
    if years < 5:
        return ["mid level", "mid-level"]
    if years < 8:
        return ["senior"]
    return ["senior", "lead", "principal"]


def _query(title: str, years: float | None, domain: str) -> str:
    parts = [title.strip(), domain.strip()]
    seniority = _years_terms(years)
    if seniority:
        parts.append(seniority[0])
    return " ".join(part for part in parts if part)[:240]


def _normalize(**kwargs: Any) -> dict[str, Any]:
    return {
        "provider": kwargs["provider"],
        "provider_job_id": str(kwargs.get("job_id") or kwargs.get("url") or ""),
        "title": _clean_text(kwargs.get("title"), 300),
        "company": _clean_text(kwargs.get("company"), 220) or "Company not specified",
        "description": _clean_text(kwargs.get("description"), 5000),
        "location": _clean_text(kwargs.get("location"), 300) or "Location not specified",
        "remote_type": _clean_text(kwargs.get("remote_type"), 80) or None,
        "employment_type": _clean_text(kwargs.get("employment_type"), 80) or None,
        "experience_level": _clean_text(kwargs.get("experience_level"), 100) or None,
        "salary": _clean_text(kwargs.get("salary"), 180) or None,
        "posted_at": kwargs.get("posted_at"),
        "application_url": str(kwargs.get("url") or ""),
        "source_url": str(kwargs.get("source_url") or kwargs.get("url") or ""),
    }


async def _adzuna(query: str) -> list[dict[str, Any]]:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{settings.adzuna_country}/search/1"
    params = {"app_id": settings.adzuna_app_id, "app_key": settings.adzuna_app_key,
              "results_per_page": min(settings.job_search_max_results, 20),
              "what": query, "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    return [_normalize(provider="Adzuna", job_id=item.get("id"), title=item.get("title"),
        company=(item.get("company") or {}).get("display_name"), description=item.get("description"),
        location=(item.get("location") or {}).get("display_name"), url=item.get("redirect_url"),
        posted_at=item.get("created"),
        salary=(f'{item.get("salary_min")} - {item.get("salary_max")}' if item.get("salary_min") else None))
        for item in (data.get("results") or [])]


async def _jooble(query: str) -> list[dict[str, Any]]:
    if not settings.jooble_api_key:
        return []
    endpoint = f"{settings.jooble_base_url.rstrip('/')}/{settings.jooble_api_key}"
    payload = {"keywords": query, "location": "India", "page": 1,
               "ResultOnPage": min(settings.job_search_max_results, 20), "SearchMode": 0, "companysearch": False}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    return [_normalize(provider="Jooble", job_id=item.get("id") or item.get("link"),
        title=item.get("title"), company=item.get("company"), description=item.get("snippet"),
        location=item.get("location"), url=item.get("link"), posted_at=item.get("updated"), salary=item.get("salary"))
        for item in (data.get("jobs") or [])]


async def _themuse(query: str) -> list[dict[str, Any]]:
    if not settings.themuse_api_key:
        return []
    params = {"page": 0, "api_key": settings.themuse_api_key, "location": "India"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(f"{settings.themuse_base_url.rstrip('/')}/jobs", params=params)
        response.raise_for_status()
        data = response.json()
    terms = [part.lower() for part in query.split() if len(part) > 2]
    output = []
    for item in (data.get("results") or []):
        title = _clean_text(item.get("name"))
        company = _clean_text((item.get("company") or {}).get("name"))
        haystack = f"{title} {company} {_clean_text(item.get('contents'))} {' '.join(str(x) for x in (item.get('categories') or []))}".lower()
        if terms and not any(term in haystack for term in terms):
            continue
        levels = item.get("levels") or []
        locations = item.get("locations") or []
        output.append(_normalize(provider="The Muse", job_id=item.get("id"), title=title, company=company,
            description=item.get("contents"), location=", ".join(_clean_text(x.get("name")) for x in locations[:3]),
            url=(item.get("refs") or {}).get("landing_page"), posted_at=item.get("publication_date"),
            experience_level=", ".join(_clean_text(x.get("name")) for x in levels[:3])))
    return output[:settings.job_search_max_results]


async def _remotive(query: str) -> list[dict[str, Any]]:
    if not settings.remotive_enabled:
        return []
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get("https://remotive.com/api/remote-jobs",
                                    params={"search": query, "limit": min(settings.job_search_max_results, 50)})
        response.raise_for_status()
        data = response.json()
    return [_normalize(provider="Remotive", job_id=item.get("id"), title=item.get("title"),
        company=item.get("company_name"), description=item.get("description"),
        location=item.get("candidate_required_location"), url=item.get("url"),
        posted_at=item.get("publication_date"), employment_type=item.get("job_type"),
        salary=item.get("salary"), remote_type="Remote")
        for item in (data.get("jobs") or [])]


def _dedupe(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for job in jobs:
        key = hashlib.sha256(f"{job['title'].lower()}|{job['company'].lower()}|{job['application_url']}".encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            output.append(job)
    return output


async def search_jobs(session: AsyncSession, title: str, years: float | None, domain: str, query: str | None = None) -> dict[str, Any]:
    search_query = (query or _query(title, years, domain)).strip()[:240]
    if not search_query:
        search_query = _query(title, years, domain)
    key = hashlib.sha256(f"{search_query.lower()}|{title.lower()}|{years}|{domain.lower()}".encode()).hexdigest()
    cached = (await session.execute(select(JobSearchCache).where(JobSearchCache.cache_key == key))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if cached and cached.expires_at > now:
        payload = json.loads(cached.payload_json)
        payload["cached"] = True
        return payload

    providers = [("Adzuna", _adzuna), ("Jooble", _jooble), ("The Muse", _themuse), ("Remotive", _remotive)]
    async def call(name: str, fn: Any) -> tuple[str, list[dict[str, Any]], str | None, int]:
        started = time.perf_counter()
        try:
            items = await fn(search_query)
            return name, items, None, int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            return name, [], str(exc)[:300], int((time.perf_counter() - started) * 1000)

    results = await asyncio.gather(*(call(name, fn) for name, fn in providers))
    jobs: list[dict[str, Any]] = []
    provider_status = []
    configured = {
        "Adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "Jooble": bool(settings.jooble_api_key),
        "The Muse": bool(settings.themuse_api_key),
        "Remotive": bool(settings.remotive_enabled),
    }
    for name, items, error, latency_ms in results:
        provider_status.append({"provider": name, "configured": configured[name],
                                "available": error is None, "returned_jobs": len(items), "error": error})
        session.add(ObservabilityEvent(
            correlation_id=key[:24], event_type="ProviderSucceeded" if error is None else "ProviderFailed",
            activity_type="JOB_SEARCH", status="SUCCESS" if error is None else "FAILED",
            user_visible_failure=False, provider=name, latency_ms=latency_ms,
            failure_category=("PROVIDER_UNAVAILABLE" if error else None),
            details_json=json.dumps({"returned_jobs": len(items), "configured": configured[name]}, ensure_ascii=False),
        ))
        jobs.extend(items)

    payload = {"query": search_query, "jobs": _dedupe(jobs)[:settings.job_search_max_results],
               "providers": provider_status, "cached": False}
    if cached:
        cached.payload_json = json.dumps(payload, ensure_ascii=False)
        cached.expires_at = now + timedelta(seconds=settings.job_search_cache_seconds)
    else:
        session.add(JobSearchCache(cache_key=key, payload_json=json.dumps(payload, ensure_ascii=False),
                                   expires_at=now + timedelta(seconds=settings.job_search_cache_seconds)))
    await session.commit()
    return payload
