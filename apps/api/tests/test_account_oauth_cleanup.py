import unittest

from fastapi.testclient import TestClient

from app.main import app


class TestAccountAndOAuthCleanup(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_oauth_denial_clears_state_cookie_at_original_path(self):
        response = self.client.get(
            "/api/auth/linkedin/callback?error=access_denied",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("brand_os_oauth_state", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Path=/api", cookie)


if __name__ == "__main__":
    unittest.main()
