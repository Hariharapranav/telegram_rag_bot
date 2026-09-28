import os
import re
import logging
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


def normalize_database_url(raw_url: str) -> tuple[str, Dict[str, Any]]:
    """
    Format and sanitize database URL for SQLAlchemy asyncpg,
    specifically configuring Supabase PostgreSQL and connection poolers.
    """
    if not raw_url or not raw_url.strip():
        # Fallback to local sqlite if no DATABASE_URL provided yet (/tmp on Vercel)
        db_path = "/tmp/enterprise_rag.db" if os.getenv("VERCEL") else "./enterprise_rag.db"
        logger.warning(f"DATABASE_URL is not set in .env. Falling back to local sqlite+aiosqlite:///{db_path}")
        return f"sqlite+aiosqlite:///{db_path}", {}

    url = raw_url.strip()
    connect_args: Dict[str, Any] = {}

    # Check if host is Supabase
    is_supabase = "supabase.co" in url or "pooler.supabase" in url

    # Remove query params like ?sslmode=require that asyncpg rejects in URL
    if "?" in url:
        base_url, query_str = url.split("?", 1)
        params = dict(param.split("=", 1) for param in query_str.split("&") if "=" in param)
        if "sslmode" in params or is_supabase:
            connect_args["ssl"] = "require"
        url = base_url

    # Ensure asyncpg dialect
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Supabase Transaction/Session Pooler and Direct connection configurations
    if is_supabase:
        connect_args["ssl"] = "require"
        # Disable prepared statement caching when connecting through Supabase pooler or direct
        connect_args["statement_cache_size"] = 0

    return url, connect_args


db_url, connect_args = normalize_database_url(settings.DATABASE_URL)

engine = create_async_engine(
    db_url,
    echo=settings.DB_ECHO,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
