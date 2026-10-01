import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.agents.orchestrator import AgentOrchestrator
from app.jobs.scheduled_jobs import ScheduledJobs
from app.services.agent_scheduler import AgentScheduler


class TestScheduledJobBoundary(unittest.IsolatedAsyncioTestCase):
    def test_scheduler_delegates_to_job_boundary(self):
        scheduler = AgentScheduler(Mock())
        self.assertIsInstance(scheduler.jobs, ScheduledJobs)
        self.assertIsNone(scheduler._task)

    async def test_learning_and_retention_are_delegated(self):
        jobs = ScheduledJobs(Mock())
        session = Mock()

        with patch("app.jobs.scheduled_jobs.BrandLearningService") as learning_cls:
            learning_cls.return_value.process_pending = AsyncMock()
            await jobs.process_learning(session, limit=7)
            learning_cls.return_value.process_pending.assert_awaited_once_with(limit=7)

        with patch("app.jobs.scheduled_jobs.RetentionService") as retention_cls:
            retention_cls.return_value.compact = AsyncMock(return_value={"trimmed": 0})
            result = await jobs.process_retention(session)
            self.assertEqual(result, {"trimmed": 0})
            retention_cls.return_value.compact.assert_awaited_once_with(session)

    async def test_rejects_unknown_scheduled_job(self):
        jobs = ScheduledJobs(Mock())
        with self.assertRaises(ValueError):
            await jobs.run("unknown")

    async def test_daily_post_creates_at_most_one_candidate(self):
        orchestrator = AgentOrchestrator(Mock(), 1)
        orchestrator._profile = AsyncMock(return_value=Mock(id=1))
        orchestrator._create_candidate = AsyncMock(side_effect=[101, 102])
        opportunities = [
            {"title": "First", "topic": "first", "pillar": "Insights", "objective": "Learn",
             "evidence": {"summary": "s1", "why_now": "n1"}, "sources": []},
            {"title": "Second", "topic": "second", "pillar": "Insights", "objective": "Learn",
             "evidence": {"summary": "s2", "why_now": "n2"}, "sources": []},
        ]

        with patch("app.agents.orchestrator.ResearchService") as research_cls:
            research_cls.return_value.research_and_rank = AsyncMock(return_value=opportunities)
            result = await orchestrator.run_daily_post()

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["created_content_ids"], [101])
        orchestrator._create_candidate.assert_awaited_once()

    async def test_research_refresh_never_creates_content(self):
        orchestrator = AgentOrchestrator(Mock(), 1)
        orchestrator._profile = AsyncMock(return_value=Mock(id=1))
        orchestrator._create_candidate = AsyncMock()
        opportunities = [{"title": "Research", "topic": "research", "pillar": "Insights", "objective": "Learn"}]

        with patch("app.agents.orchestrator.ResearchService") as research_cls:
            research_cls.return_value.research_and_rank = AsyncMock(return_value=opportunities)
            result = await orchestrator.run_research_refresh()

        self.assertTrue(result["research_updated"])
        self.assertEqual(result["created_count"], 0)
        orchestrator._create_candidate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
