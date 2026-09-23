import unittest

from fastapi.testclient import TestClient

from app.main import app


class TestLinkedInWhitelistAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_linkedin_whitelist_login(self):
        response = self.client.post(
            "/api/auth/linkedin/login",
            json={
                "email": "kanishka.utsav@gmail.com",
                "linkedin_url": "https://www.linkedin.com/in/kanishkautsav/",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["role"], "owner")
        self.assertEqual(payload["email"], "kanishka.utsav@gmail.com")

    def test_linkedin_whitelist_rejects_non_member(self):
        response = self.client.post(
            "/api/auth/linkedin/login",
            json={
                "email": "someone@example.com",
                "linkedin_url": "https://www.linkedin.com/in/any-user/",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_dashboard_requires_role_from_whitelist_session(self):
        login = self.client.post(
            "/api/auth/linkedin/login",
            json={
                "email": "pranaybeatking@gmail.com",
                "linkedin_url": "https://www.linkedin.com/in/kumar-pranay-548181309/",
            },
        )
        token = login.json()["token"]

        profile = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["role"], "owner")

        dashboard = self.client.get("/api/dashboard/approvals", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(dashboard.status_code, 200)


if __name__ == "__main__":
    unittest.main()
