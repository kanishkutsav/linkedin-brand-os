from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _serverless_database_config() -> tuple[str, dict]:
    """Use Supabase transaction pooling for short-lived serverless requests."""
    url = settings.database_url
    connect_args: dict = {}
    parsed = urlsplit(url)

    # Supabase's transaction pooler (PgBouncer) does not support asyncpg
    # prepared statements. This must be true for every pooler URL shape:
    # some environments include :5432, some omit the port, and some already
    # provide :6543. A partial check here can make auth intermittently fail
    # with DuplicatePreparedStatementError during cold starts.
    is_postgres = parsed.scheme.startswith("postgresql") or parsed.scheme.startswith("postgres")
    if is_postgres:
        # Vercel + Supabase can inject either a direct PostgreSQL URL or a
        # pooler URL. Disable asyncpg prepared statements for every PostgreSQL
        # serverless connection so neither shape can leak PgBouncer failures.
        # SQLAlchemy's asyncpg dialect prepares every statement itself. The
        # asyncpg-level statement_cache_size alone does not disable that
        # dialect cache, so explicitly disable SQLAlchemy's cache and use
        # globally unique statement names for PgBouncer transaction pooling.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"

    if "pooler.supabase.com" in (parsed.hostname or ""):
        pooler_port = parsed.port or 5432
        if pooler_port == 5432:
            host = parsed.hostname or ""
            authority = parsed.netloc
            userinfo = authority.rsplit("@", 1)[0] if "@" in authority else ""
            netloc = f"{userinfo}@{host}:6543" if userinfo else f"{host}:6543"
            url = urlunsplit((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
            ))

        # PgBouncer transaction pooling and asyncpg prepared statements are
        # incompatible. Disable the statement cache even when the URL already
        # points at :6543 or credentials are encoded in the authority.
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
