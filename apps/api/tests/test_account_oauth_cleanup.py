import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import AccountDeletionRequest, app, delete_account
from app.services.auth_service import AppUser


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return self._rows


class _DeletionSession:
    def __init__(self):
        self.statements = []
        self.commit = AsyncMock()

    async def execute(self, statement):
        self.statements.append(str(statement))
        if len(self.statements) == 1:
            return _Result(rows=[(1,)])  # content IDs
        if len(self.statements) == 2:
            return _Result(rows=[(11,)])  # content version IDs
        if len(self.statements) == 3:
            return _Result(rows=[(101,)])  # approval IDs
        return _Result(rowcount=1)


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

    def test_account_deletion_removes_feedback_linked_by_approval_id(self):
        import asyncio

        async def run():
            session = _DeletionSession()
            await delete_account(
                AccountDeletionRequest(confirmation="DELETE"),
                session,
                AppUser(id="42", email="person@example.com", role="user"),
            )
            feedback_deletes = [
                (index, statement)
                for index, statement in enumerate(session.statements)
                if "DELETE FROM feedback_entries" in statement
            ]
            self.assertTrue(any("feedback_entries.approval_id IN" in statement for _, statement in feedback_deletes))
            approval_delete_index = next(
                index for index, statement in enumerate(session.statements)
                if "DELETE FROM approval_requests" in statement
            )
            self.assertTrue(all(index < approval_delete_index for index, _ in feedback_deletes))
            session.commit.assert_awaited_once()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
