import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


class TestVercelSecurityMiddleware(unittest.TestCase):
    def test_stripped_api_prefix_is_restored_before_csrf_check(self):
        with patch.dict(os.environ, {"VERCEL": "1"}), \
             patch("app.main.rate_limiter.allow_shared", new=AsyncMock(return_value=True)), \
             patch("app.main.validate_csrf_token", return_value=False):
            client = TestClient(app)
            response = client.post(
                "/auth/linkedin/login",
                cookies={"suvacya_session": "test-session"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CSRF_FAILED")
        self.assertEqual(response.headers.get("X-Request-ID"), response.json()["request_id"])

    def test_stripped_api_prefix_is_rate_limited(self):
        with patch.dict(os.environ, {"VERCEL": "1"}), \
             patch("app.main.rate_limiter.allow_shared", new=AsyncMock(return_value=False)):
            client = TestClient(app)
            response = client.get("/auth/me")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "RATE_LIMITED")
        self.assertEqual(response.headers.get("X-Request-ID"), response.json()["request_id"])


if __name__ == "__main__":
    unittest.main()
