import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.models import ApprovalRequest
from app.services.approval import ApprovalService


class TestPublicationReconciliation(unittest.IsolatedAsyncioTestCase):
    def test_published_at_is_a_persisted_approval_column(self):
        self.assertIn("published_at", ApprovalRequest.__table__.c)
        self.assertTrue(ApprovalRequest.__table__.c.published_at.nullable)

    async def test_uncertain_publish_requires_explicit_confirmation(self):
        session = MagicMock()
        service = ApprovalService(session)
        service._get_owned_approval = AsyncMock(
            return_value=SimpleNamespace(id=7, status="PUBLISHING")
        )

        with self.assertRaisesRegex(ValueError, "Explicit confirmation"):
            await service.resolve_publication(
                7, 3, outcome="not_published", confirmed=False
            )

    async def test_verified_not_published_reopens_approved_state(self):
        session = MagicMock()
        session.commit = AsyncMock()
        approval = SimpleNamespace(
            id=7,
            status="PUBLISHING",
            publish_started_at=object(),
            reason=None,
        )
        service = ApprovalService(session)
        service._get_owned_approval = AsyncMock(return_value=approval)

        result = await service.resolve_publication(
            7, 3, outcome="not_published", confirmed=True
        )

        self.assertIs(result["approval"], approval)
        self.assertEqual(approval.status, "APPROVED")
        self.assertIsNone(approval.publish_started_at)
        session.commit.assert_awaited_once()
        self.assertEqual(session.add.call_args.args[0].event_type, "PUBLICATION_RECONCILED_NOT_PUBLISHED")


if __name__ == "__main__":
    unittest.main()
