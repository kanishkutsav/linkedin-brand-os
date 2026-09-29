from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _serverless_database_config() -> tuple[str, dict]:
    """Use Supabase transaction pooling for short-lived serverless requests."""
    url = settings.database_url
    connect_args: dict = {}
    parsed = urlsplit(url)

    # Supabase session-mode poolers have a small per-session client limit.
    # Vercel functions should use transaction mode instead. asyncpg prepared
    # statement caching must be disabled for transaction pooling.
    if "pooler.supabase.com" in (parsed.hostname or "") and parsed.port == 5432:
        url = urlunsplit((
            parsed.scheme,
            parsed.netloc.rsplit(":5432", 1)[0] + ":6543",
            parsed.path,
            parsed.query,
            parsed.fragment,
        ))
        connect_args["statement_cache_size"] = 0

    # Never retain a second client pool inside a serverless process.
    return url, connect_args


database_url, database_connect_args = _serverless_database_config()
engine = create_async_engine(
    database_url,
    future=True,
    poolclass=NullPool,
    connect_args=database_connect_args,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session():
    async with SessionLocal() as session:
        yield session
