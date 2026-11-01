import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.brand_learning import BrandLearningService


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarRows(self._rows)


class TestLearningBatchQueries(unittest.IsolatedAsyncioTestCase):
    async def test_memory_upserts_use_one_lookup_and_coalesce_duplicate_keys(self):
        event = SimpleNamespace(
            id=7,
            profile_id=12,
            event_type="USER_THOUGHT",
            source_type="manual_thought",
            content="A sufficiently long personal thought for the learning processor.",
            metadata_json="{}",
            status="PENDING",
            processed_at=None,
            attempts=0,
            last_error=None,
        )
        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _Result([event]),  # pending events
            _Result([]),       # one batched memory lookup for this profile
        ])
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()

        router = MagicMock()
        router.generate_json = AsyncMock(return_value={
            "memories": [
                {
                    "memory_key": "clear-writing",
                    "memory_type": "writing_preference",
                    "content": "Prefers clear writing.",
                    "confidence": "medium",
                    "importance": 0.5,
                    "evidence_event_ids": [7],
                },
                {
                    "memory_key": "clear-writing",
                    "memory_type": "writing_preference",
                    "content": "Prefers concise and clear writing.",
                    "confidence": "high",
                    "importance": 0.7,
                    "evidence_event_ids": [7],
                },
            ]
        })

        with patch("app.services.brand_learning.ModelRouterService", return_value=router), patch.object(
            BrandLearningService, "_embed_documents", new=AsyncMock(return_value=[])
        ):
            processed = await BrandLearningService(session).process_pending()

        self.assertEqual(processed, 1)
        self.assertEqual(session.execute.await_count, 2)
        session.add.assert_called_once()
        memory = session.add.call_args.args[0]
        self.assertEqual(memory.memory_key, "clear-writing")
        self.assertEqual(memory.source_count, 2)
        self.assertEqual(memory.content, "Prefers concise and clear writing.")
        session.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
