"""Regression tests for account-data boundaries and recently fixed service defects."""

import pytest


def test_account_export_endpoint_is_not_registered():
    from app.main import app

    assert not any(getattr(route, "path", None) == "/api/account/export" for route in app.routes)


def test_linkedin_analytics_declares_all_trend_metrics():
    from app.services.linkedin_analytics import LinkedInAnalyticsService

    assert LinkedInAnalyticsService.METRICS == (
        "IMPRESSION",
        "REACTION",
        "COMMENT",
        "RESHARE",
        "MEMBERS_REACHED",
    )


@pytest.mark.asyncio
async def test_research_url_guard_rejects_private_and_non_http_targets():
    from app.agents.research import _is_public_http_url

    assert await _is_public_http_url("http://127.0.0.1:8000/internal") is False
    assert await _is_public_http_url("http://localhost/admin") is False
    assert await _is_public_http_url("file:///etc/passwd") is False
