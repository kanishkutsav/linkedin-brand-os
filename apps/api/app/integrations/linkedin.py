import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class PublishResult:
    success: bool
    external_id: str | None
    message: str


class LinkedInAdapter:
    """Official LinkedIn API boundary. No browser automation or private APIs."""

    def publish_post(self, body: str) -> PublishResult:
        raise NotImplementedError


class MockLinkedInAdapter(LinkedInAdapter):
    def publish_post(self, body: str) -> PublishResult:
        if not body or not body.strip():
            return PublishResult(False, None, "Content body is empty.")
        return PublishResult(True, "mock-post-001", "Mock publish succeeded; no external LinkedIn action was made.")


class OfficialLinkedInAdapter(LinkedInAdapter):
    def __init__(self, access_token: str, member_sub: str):
        self.access_token = access_token
        self.member_sub = member_sub

    def publish_post(self, body: str) -> PublishResult:
        if not body or not body.strip():
            return PublishResult(False, None, "Content body is empty.")

        base = (settings.linkedin_api_base_url or "https://api.linkedin.com").rstrip("/")
        url = f"{base}/rest/posts"
        payload = {
            "author": f"urn:li:person:{self.member_sub}",
            "commentary": body.strip(),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "Linkedin-Version": "202603",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                external_id = response.headers.get("x-restli-id")
                return PublishResult(True, external_id, "Published to LinkedIn through the official Posts API.")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return PublishResult(False, None, f"LinkedIn API rejected the post ({exc.code}): {detail[:500]}")
        except Exception as exc:
            return PublishResult(False, None, f"LinkedIn API request failed: {exc}")
