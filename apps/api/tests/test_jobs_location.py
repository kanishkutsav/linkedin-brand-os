from starlette.requests import Request

from app.services.jobs import _cache_key, _location_matches, resolve_job_location


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/jobs/search",
        "headers": raw_headers,
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "https",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_job_location_prefers_vercel_ip_over_linkedin_locale():
    location = resolve_job_location(
        _request({"x-vercel-ip-country": "IN", "x-vercel-ip-city": "Nashik"}),
        "en-US",
        default_country="IN",
    )
    assert location == {
        "country_code": "IN",
        "country": "India",
        "city": "Nashik",
        "source": "ip",
    }


def test_job_location_falls_back_to_linkedin_locale():
    location = resolve_job_location(_request(), "en-US", default_country="IN")
    assert location["country_code"] == "US"
    assert location["country"] == "United States"
    assert location["source"] == "linkedin"


def test_job_location_falls_back_to_configured_country():
    location = resolve_job_location(_request(), None, default_country="IN")
    assert location == {
        "country_code": "IN",
        "country": "India",
        "city": "",
        "source": "configured_default",
    }


def test_india_filter_excludes_us_and_keeps_india_and_worldwide():
    target = {"country_code": "IN", "country": "India", "city": "Nashik"}
    assert _location_matches("New York, USA", "Remote", target) is False
    assert _location_matches("Nashik, Maharashtra, India", None, target) is True
    assert _location_matches("Remote - Worldwide", "Remote", target) is True
    assert _location_matches("Remote - United States", "Remote", target) is False


def test_job_cache_key_is_location_specific():
    india = {"country_code": "IN", "country": "India", "city": "Nashik"}
    us = {"country_code": "US", "country": "United States", "city": "New York"}
    assert _cache_key("product manager", "Product Manager", 5, "Technology", india) != _cache_key(
        "product manager", "Product Manager", 5, "Technology", us
    )
