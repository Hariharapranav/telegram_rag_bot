import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.config import settings
from app.db.database import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("supabase_check")


async def check_connection():
    masked = settings.database.masked_url
    logger.info("Testing connection to configured database: %s", masked)

    if "sqlite" in settings.database.masked_url or not settings.database.is_configured:
        print("\n" + "=" * 70)
        print("[WARNING] DATABASE_URL in .env is currently empty or using SQLite fallback!")
        print("          Your app is storing data in local file ./enterprise_rag.db, NOT in Supabase.\n")
        print("To store all organizations, users, and documents in Supabase:")
        print("1. Open Supabase Dashboard: https://supabase.com/dashboard/project/yzffmlsvqcxqwrzttdhv")
        print("2. Go to Project Settings -> Database -> Connection String")
        print("3. Select 'URI' -> 'Transaction Pooler' (port 6543) or 'Session Pooler'")
        print("4. Copy the connection string and paste it into .env under DATABASE_URL:")
        print('   DATABASE_URL="postgresql+asyncpg://postgres.yzffmlsvqcxqwrzttdhv:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"')
        print("=" * 70 + "\n")
        return False

    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version();"))
            row = res.fetchone()
            logger.info("[OK] Successfully connected to Supabase PostgreSQL!")
            logger.info("   PostgreSQL version: %s", row[0])

            # Check pgvector
            vec_res = await conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"))
            vec_row = vec_res.fetchone()
            if vec_row:
                logger.info("[OK] pgvector extension is installed (version: %s)", vec_row[1])
            else:
                logger.warning("[WARN] pgvector extension is not enabled yet. Attempting to enable...")
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                logger.info("[OK] pgvector extension created successfully!")

            # Check tables
            tables_res = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
            ))
            tables = [t[0] for t in tables_res.fetchall()]
            logger.info("   Found public tables in Supabase: %s", tables)

            return True

    except Exception as e:
        logger.error("[ERROR] Failed to connect to Supabase database: %s", e)
        logger.info(
            "\nTroubleshooting tips:\n"
            "1. Did you replace [YOUR-PASSWORD] with your real Supabase database password?\n"
            "2. If your password has special characters (like @, #, $, %), URL-encode them.\n"
            "3. On networks with IPv4 only, use Supabase's Transaction Pooler URI (port 6543) instead of direct port 5432."
        )
        return False


if __name__ == "__main__":
    success = asyncio.run(check_connection())
    sys.exit(0 if success else 1)
