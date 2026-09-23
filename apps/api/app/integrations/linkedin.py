from dataclasses import dataclass

from app.core.config import settings


@dataclass
class PublishResult:
    success: bool
    external_id: str | None
    message: str


class LinkedInAdapter:
    """Interface boundary. Real implementation must use officially supported APIs."""
    def publish_post(self, body: str) -> PublishResult:
        raise NotImplementedError


class MockLinkedInAdapter(LinkedInAdapter):
    def publish_post(self, body: str) -> PublishResult:
        if settings.environment.lower() == "production" and not settings.linkedin_client_id:
            return PublishResult(False, None, "Live LinkedIn execution is disabled in production without an approved client configuration.")
        if not body or not body.strip():
            return PublishResult(False, None, "Content body is empty.")
        return PublishResult(True, "mock-post-001", "Mock publish succeeded; no external LinkedIn action was made.")
