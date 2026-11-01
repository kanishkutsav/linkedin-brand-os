import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services.approval import ApprovalService


class _MissingResult:
    def scalar_one_or_none(self):
        return None


class TestApprovalOwnership(unittest.IsolatedAsyncioTestCase):
    async def test_approval_lookup_is_scoped_to_the_callers_profile(self):
        session = MagicMock()
        session.execute = AsyncMock(return_value=_MissingResult())

        with self.assertRaisesRegex(ValueError, "Approval not found"):
            await ApprovalService(session)._get_owned_approval(approval_id=91, profile_id=42)

        statement = str(session.execute.await_args.args[0])
        self.assertIn("approval_requests.id", statement)
        self.assertIn("content_items.profile_id", statement)
        self.assertIn("profile_id_1", statement)


if __name__ == "__main__":
    unittest.main()
