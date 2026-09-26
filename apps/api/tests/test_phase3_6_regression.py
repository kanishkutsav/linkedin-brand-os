import pytest
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.jobs.durable_queue import enqueue_job
from app.jobs.durable_worker import DurableJobWorker
from app.models.base import Base
from app.models.models import DurableJob


@pytest.fixture
async def durable_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / "durable.db"}")
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_durable_queue_is_idempotent(durable_db):
    async with durable_db() as session:
        first = await enqueue_job(session, job_type="manual_content_generation", profile_id=7, payload={"trigger":"test"}, idempotency_key="same-job")
        second = await enqueue_job(session, job_type="manual_content_generation", profile_id=7, payload={"trigger":"test"}, idempotency_key="same-job")
        await session.commit()
        assert first is not None
        assert second is None
        rows = await session.execute(select(DurableJob))
        assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_durable_worker_claims_and_completes_job(durable_db):
    calls = []
    async def handler(session, job, payload):
        calls.append((job.id, payload))
        return {"ok": True}
    async with durable_db() as session:
        await enqueue_job(session, job_type="test", payload={"value":42}, idempotency_key="worker-test")
        await session.commit()
    worker = DurableJobWorker(durable_db, {"test": handler}, allowed_job_types={"test"}, poll_interval_seconds=1, lease_seconds=60, worker_id="qa-worker")
    assert await worker.process_one() is True
    assert calls and calls[0][1] == {"value":42}
    async with durable_db() as session:
        job = (await session.execute(select(DurableJob))).scalar_one()
        assert job.status == "SUCCEEDED"
        assert job.attempts == 1
        assert job.locked_at is None
        assert job.locked_by is None


@pytest.mark.asyncio
async def test_durable_worker_retries_transient_failure(durable_db):
    async def handler(session, job, payload):
        raise RuntimeError("temporary provider failure")
    async with durable_db() as session:
        await enqueue_job(session, job_type="test", payload={}, idempotency_key="retry-test")
        await session.commit()
    worker = DurableJobWorker(durable_db, {"test": handler}, allowed_job_types={"test"}, poll_interval_seconds=1, lease_seconds=60, max_attempts=3, worker_id="qa-worker")
    await worker.process_one()
    async with durable_db() as session:
        job = (await session.execute(select(DurableJob))).scalar_one()
        assert job.status == "QUEUED"
        assert job.attempts == 1
        assert "temporary provider failure" in (job.last_error or "")


def test_phase6_files_and_guards_exist():
    root = Path(__file__).resolve().parents[3]
    assert (root / "apps/api/app/jobs/durable_handlers.py").exists()
    assert (root / "apps/api/app/jobs/durable_queue.py").exists()
    assert (root / "apps/api/app/jobs/durable_worker.py").exists()
    assert (root / "apps/api/app/durable_worker_main.py").exists()
