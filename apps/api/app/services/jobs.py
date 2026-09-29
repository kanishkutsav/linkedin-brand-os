from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus

from fastapi import Request
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import JobSearchCache, ObservabilityEvent


# Job-market location aliases used for deterministic provider filtering. The primary
# signal is Vercel's IP country/city headers; LinkedIn locale is only a fallback.
_COUNTRY_NAMES = {
    "AE": "United Arab Emirates", "AU": "Australia", "BR": "Brazil", "CA": "Canada",
    "CH": "Switzerland", "DE": "Germany", "ES": "Spain", "FR": "France",
    "GB": "United Kingdom", "IE": "Ireland", "IN": "India", "IT": "Italy",
    "JP": "Japan", "MX": "Mexico", "MY": "Malaysia", "NL": "Netherlands",
    "NZ": "New Zealand", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "PT": "Portugal", "SG": "Singapore", "ZA": "South Africa", "SE": "Sweden",
    "TR": "Türkiye", "US": "United States", "VN": "Vietnam",
}
_COUNTRY_ALIASES = {
    "AE": {"uae", "united arab emirates"}, "AU": {"australia"}, "BR": {"brazil"},
    "CA": {"canada"}, "CH": {"switzerland"}, "DE": {"germany"}, "ES": {"spain"},
    "FR": {"france"}, "GB": {"uk", "united kingdom", "great britain", "england", "scotland", "wales"},
    "IE": {"ireland"}, "IN": {"india", "bharat"}, "IT": {"italy"}, "JP": {"japan"},
    "MX": {"mexico"}, "MY": {"malaysia"}, "NL": {"netherlands", "holland"},
    "NZ": {"new zealand"}, "PH": {"philippines"}, "PK": {"pakistan"}, "PL": {"poland"},
    "PT": {"portugal"}, "SG": {"singapore"}, "ZA": {"south africa"}, "SE": {"sweden"},
    "TR": {"turkey", "türkiye"}, "US": {"usa", "us", "united states", "united states of america"},
    "VN": {"vietnam", "viet nam"},
}
_WORLDWIDE_TERMS = {
    "worldwide", "global", "anywhere", "any location", "all locations",
    "work from anywhere", "remote - worldwide", "remote worldwide",
}


def _header_location(request: Request) -> tuple[str | None, str | None]:
    country = (request.headers.get("x-vercel-ip-country") or "").strip().upper()
    city = unquote_plus((request.headers.get("x-vercel-ip-city") or "").strip())
    return country[:2] or None, city[:120] or None


def _locale_country(locale: str | None) -> str | None:
    raw = str(locale or "").strip().replace("_", "-")
    if not raw:
        return None
    parts = [part.strip().upper() for part in raw.split("-") if part.strip()]
    for part in reversed(parts):
        if len(part) == 2 and part.isalpha():
            return part
    return None


def resolve_job_location(
    request: Request,
    linkedin_locale: str | None,
    default_country: str = "IN",
) -> dict[str, str]:
    ip_country, ip_city = _header_location(request)
    if ip_country:
        return {"country_code": ip_country, "country": _COUNTRY_NAMES.get(ip_country, ip_country),
                "city": ip_city or "", "source": "ip"}

    linkedin_country = _locale_country(linkedin_locale)
    if linkedin_country:
        return {"country_code": linkedin_country, "country": _COUNTRY_NAMES.get(linkedin_country, linkedin_country),
                "city": "", "source": "linkedin"}

    fallback = (default_country or "IN").strip().upper()[:2]
    return {"country_code": fallback, "country": _COUNTRY_NAMES.get(fallback, fallback),
            "city": "", "source": "configured_default"}


def _contains_location_term(location: str, term: str) -> bool:
    if len(term) <= 2:
        return bool(re.search(rf"\b{re.escape(term)}\b", location))
    return term in location


def _location_matches(job_location: str, remote_type: str | None, target: dict[str, str]) -> bool:
    location = _clean_text(job_location, 500).lower()
    remote = _clean_text(remote_type, 120).lower()
    if not location:
        return "remote" in remote
    if any(term in location for term in _WORLDWIDE_TERMS):
        return True

    country_code = target.get("country_code", "").upper()
    country_name = target.get("country", "").lower()
    aliases = _COUNTRY_ALIASES.get(country_code, set())
    if country_name and country_name.lower() not in aliases:
        aliases = set(aliases) | {country_name}
    if any(_contains_location_term(location, alias) for alias in aliases):
        return True

    city = target.get("city", "").strip().lower()
    if city and len(city) >= 3 and city in location:
        return True

    restricted_markets = ("usa", "us", "united states", "uk", "united kingdom", "canada", "australia")
    if "remote" in location and not any(
        _contains_location_term(location, restricted)
        for restricted in restricted_markets if restricted not in aliases
    ):
        return True
    return False


def _filter_jobs_to_location(jobs: list[dict[str, Any]], target: dict[str, str]) -> list[dict[str, Any]]:
    # Provider-side location queries are useful but not sufficient: providers
    # can still return broad/global results. Apply the same deterministic
    # market guard to every normalized result before it reaches the user.
    return [
        job for job in jobs
        if _location_matches(job.get("location", ""), job.get("remote_type"), target)
    ]


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


async def _adzuna(query: str, target: dict[str, str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []
    country = target.get("country_code", "").lower() or settings.adzuna_country.lower()
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {"app_id": settings.adzuna_app_id, "app_key": settings.adzuna_app_key,
              "results_per_page": min(settings.job_search_max_results, 20),
              "what": query, "content-type": "application/json"}
    if target.get("city"):
        params["where"] = target["city"]
    response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    return [_normalize(provider="Adzuna", job_id=item.get("id"), title=item.get("title"),
        company=(item.get("company") or {}).get("display_name"), description=item.get("description"),
        location=(item.get("location") or {}).get("display_name"), url=item.get("redirect_url"),
        posted_at=item.get("created"),
        salary=(f'{item.get("salary_min")} - {item.get("salary_max")}' if item.get("salary_min") else None))
        for item in (data.get("results") or [])]


async def _jooble(query: str, target: dict[str, str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    if not settings.jooble_api_key:
        return []
    configured_country = (settings.jooble_country or "").strip().upper()
    target_country = target.get("country_code", "").strip().upper()
    if configured_country and target_country and configured_country != target_country:
        return []
    endpoint = f"{settings.jooble_base_url.rstrip('/')}/{settings.jooble_api_key}"
    location = target.get("city") or target.get("country") or "India"
    payload = {"keywords": query, "location": location, "page": 1,
               "ResultOnPage": min(settings.job_search_max_results, 20), "SearchMode": 0, "companysearch": False}
    response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    return [_normalize(provider="Jooble", job_id=item.get("id") or item.get("link"),
        title=item.get("title"), company=item.get("company"), description=item.get("snippet"),
        location=item.get("location"), url=item.get("link"), posted_at=item.get("updated"), salary=item.get("salary"))
        for item in (data.get("jobs") or [])]


async def _themuse(query: str, target: dict[str, str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    if not settings.themuse_api_key:
        return []
    params = {"page": 0, "api_key": settings.themuse_api_key,
              "location": target.get("city") or target.get("country")}
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


async def _remotive(query: str, target: dict[str, str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    if not settings.remotive_enabled:
        return []
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


def _filter_jobs_to_query(jobs: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return jobs
    terms = [term.lower() for term in re.findall(r"[\\w-]+", query.lower()) if len(term) > 1]
    if not terms:
        return jobs
    return [
        job for job in jobs
        if all(
            term in str(job.get("title") or "").lower()
            or term in str(job.get("company") or "").lower()
            for term in terms
        )
    ]


def _dedupe(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for job in jobs:
        key = hashlib.sha256(f"{job['title'].lower()}|{job['company'].lower()}|{job['application_url']}".encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            output.append(job)
    return output


def _cache_key(
    search_query: str,
    title: str,
    years: float | None,
    domain: str,
    target: dict[str, str],
) -> str:
    location_key = f"{target.get('country_code','')}|{target.get('city','').lower()}"
    return hashlib.sha256(
        f"{search_query.lower()}|{title.lower()}|{years}|{domain.lower()}|{location_key}".encode()
    ).hexdigest()


async def search_jobs(
    session: AsyncSession,
    title: str,
    years: float | None,
    domain: str,
    query: str | None = None,
    location: dict[str, str] | None = None,
) -> dict[str, Any]:
    target = location or {
        "country_code": (settings.adzuna_country or "IN").upper()[:2],
        "country": _COUNTRY_NAMES.get((settings.adzuna_country or "IN").upper()[:2], settings.adzuna_country),
        "city": "",
        "source": "configured_default",
    }
    search_query = (query or _query(title, years, domain)).strip()[:240]
    if not search_query:
        search_query = _query(title, years, domain)
    key = _cache_key(search_query, title, years, domain, target)
    cached = (await session.execute(select(JobSearchCache).where(JobSearchCache.cache_key == key))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if cached and cached.expires_at > now:
        payload = json.loads(cached.payload_json)
        payload["cached"] = True
        return payload

    providers = [
        ("Adzuna", lambda q: _adzuna(q, target)),
        ("Jooble", lambda q: _jooble(q, target)),
        ("The Muse", lambda q: _themuse(q, target)),
        ("Remotive", lambda q: _remotive(q, target)),
    ]
    async def call(name: str, fn: Any) -> tuple[str, list[dict[str, Any]], str | None, int]:
        started = time.perf_counter()
        try:
            items = await fn(search_query)
            return name, items, None, int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            return name, [], str(exc)[:300], int((time.perf_counter() - started) * 1000)

    timeout = httpx.Timeout(6.0, connect=2.5)
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=8)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        results = await asyncio.gather(
            *(call(name, lambda q, fn=fn: fn(q, target, client)) for name, fn in providers)
        )
    jobs: list[dict[str, Any]] = []
    provider_status = []
    configured = {
        "Adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "Jooble": bool(settings.jooble_api_key),
        "The Muse": bool(settings.themuse_api_key),
        "Remotive": bool(settings.remotive_enabled),
    }
    jooble_location_supported = (
        not settings.jooble_api_key
        or not settings.jooble_country
        or settings.jooble_country.strip().upper() == target.get("country_code", "").strip().upper()
    )
    for name, items, error, latency_ms in results:
        location_supported = jooble_location_supported if name == "Jooble" else True
        provider_status.append({
            "provider": name,
            "configured": configured[name],
            "location_supported": location_supported,
            "available": error is None and location_supported,
            "returned_jobs": len(items),
            "error": error or (
                f"Provider key is configured for {settings.jooble_country.upper()}, "
                f"not {target.get('country_code', '').upper()}."
                if name == "Jooble" and configured[name] and not location_supported
                else None
            ),
        })
        session.add(ObservabilityEvent(
            correlation_id=key[:24], event_type="ProviderSucceeded" if error is None else "ProviderFailed",
            activity_type="JOB_SEARCH", status="SUCCESS" if error is None else "FAILED",
            user_visible_failure=False, provider=name, latency_ms=latency_ms,
            failure_category=("PROVIDER_UNAVAILABLE" if error else None),
            details_json=json.dumps({"returned_jobs": len(items), "configured": configured[name]}, ensure_ascii=False),
        ))
        jobs.extend(items)

    jobs = _filter_jobs_to_location(jobs, target)
    jobs = _filter_jobs_to_query(jobs, query)

    # Provider readiness/credentials are operational telemetry, not end-user
    # content. Keep them in observability/admin surfaces instead of exposing
    # configuration state through the user-facing Jobs response.
    payload = {
        "query": search_query,
        "location": target,
        "jobs": _dedupe(jobs)[:settings.job_search_max_results],
        "cached": False,
    }
    if cached:
        cached.payload_json = json.dumps(payload, ensure_ascii=False)
        cached.expires_at = now + timedelta(seconds=settings.job_search_cache_seconds)
    else:
        session.add(JobSearchCache(cache_key=key, payload_json=json.dumps(payload, ensure_ascii=False),
                                   expires_at=now + timedelta(seconds=settings.job_search_cache_seconds)))
    await session.commit()
    return payload
