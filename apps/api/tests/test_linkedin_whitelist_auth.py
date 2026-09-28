import unittest

from fastapi.testclient import TestClient

from app.main import BrandOnboardingRequest, app


class TestLinkedInWhitelistAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_legacy_linkedin_login_is_disabled(self):
        response = self.client.post(
            "/api/auth/linkedin/login",
            json={
                "email": "kanishka.utsav@gmail.com",
                "linkedin_url": "https://www.linkedin.com/in/kanishkautsav/",
            },
        )
        self.assertEqual(response.status_code, 410)

    def test_manual_profile_write_is_disabled(self):
        response = self.client.post(
            "/api/profile",
            json={
                "display_name": "Spoofed User",
                "professional_title": "Invented title",
                "industry": "Invented industry",
            },
        )
        self.assertEqual(response.status_code, 410)

    def test_brand_onboarding_posts_and_experience_are_optional(self):
        request = BrandOnboardingRequest(
            professional_title="Product Leader",
            industry="SaaS",
            tone="Clear and practical",
        )
        self.assertEqual(request.posts, [])
        self.assertIsNone(request.experience_years)

    def test_unwhitelisted_legacy_login_cannot_create_a_session(self):
        response = self.client.post(
            "/api/auth/linkedin/login",
            json={
                "email": "someone@example.com",
                "linkedin_url": "https://www.linkedin.com/in/any-user/",
            },
        )
        self.assertEqual(response.status_code, 410)


if __name__ == "__main__":
    unittest.main()
