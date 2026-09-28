import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.database import engine, Base
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


async def init_database():
    logger.info("Connecting to database: %s", settings.database.masked_url)

    async with engine.begin() as conn:
        dialect_name = conn.dialect.name
        logger.info("Detected database dialect: %s", dialect_name)

        if dialect_name == "postgresql":
            logger.info("Enabling pgvector extension if not present...")
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                logger.info("pgvector extension ready.")
            except Exception as e:
                logger.warning("Could not enable pgvector extension: %s", e)

        logger.info("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created successfully.")


if __name__ == "__main__":
    asyncio.run(init_database())
