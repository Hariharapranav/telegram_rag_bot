import sys
import json
import sqlite3
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.config import settings
from app.db.database import engine, Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sync_to_supabase")

SQLITE_DB = Path(__file__).resolve().parent.parent / "enterprise_rag.db"


def parse_dt(val):
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, str):
        try:
            # Handle standard format: 2026-09-28 04:50:48.501736
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)
    return val


async def sync():
    if not SQLITE_DB.exists():
        logger.error("No local SQLite database found at %s", SQLITE_DB)
        return

    if not settings.database.is_configured or "sqlite" in settings.database.masked_url:
        logger.error(
            "DATABASE_URL in .env is still pointing to SQLite! "
            "Please set DATABASE_URL to your Supabase PostgreSQL connection string before syncing."
        )
        return

    logger.info("Connecting to Supabase PostgreSQL at %s...", settings.database.masked_url)

    # 1. Initialize Supabase schema
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

    # 2. Read local SQLite records
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()

    async with engine.begin() as pg_conn:
        # A. Organizations
        cur.execute("SELECT id, name, created_at FROM organizations")
        org_rows = cur.fetchall()
        logger.info("Migrating %d organizations...", len(org_rows))
        for row in org_rows:
            await pg_conn.execute(
                text("""
                    INSERT INTO organizations (id, name, created_at)
                    VALUES (:id, :name, :created_at)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
                """),
                {"id": row["id"], "name": row["name"], "created_at": parse_dt(row["created_at"])}
            )

        # B. Users
        cur.execute("SELECT id, organization_id, employee_id, name, email, role, status, created_at FROM users")
        user_rows = cur.fetchall()
        logger.info("Migrating %d users...", len(user_rows))
        for row in user_rows:
            await pg_conn.execute(
                text("""
                    INSERT INTO users (id, organization_id, employee_id, name, email, role, status, created_at)
                    VALUES (:id, :organization_id, :employee_id, :name, :email, :role, :status, :created_at)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        email = EXCLUDED.email,
                        role = EXCLUDED.role,
                        status = EXCLUDED.status;
                """),
                {
                    "id": row["id"],
                    "organization_id": row["organization_id"],
                    "employee_id": row["employee_id"],
                    "name": row["name"],
                    "email": row["email"],
                    "role": row["role"],
                    "status": row["status"],
                    "created_at": parse_dt(row["created_at"])
                }
            )

        # C. Documents
        cur.execute("SELECT id, organization_id, filename, storage_path, file_size, chunk_count, uploaded_at FROM documents")
        doc_rows = cur.fetchall()
        logger.info("Migrating %d documents...", len(doc_rows))
        for row in doc_rows:
            await pg_conn.execute(
                text("""
                    INSERT INTO documents (id, organization_id, filename, storage_path, file_size, chunk_count, uploaded_at)
                    VALUES (:id, :organization_id, :filename, :storage_path, :file_size, :chunk_count, :uploaded_at)
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": row["id"],
                    "organization_id": row["organization_id"],
                    "filename": row["filename"],
                    "storage_path": row["storage_path"],
                    "file_size": row["file_size"],
                    "chunk_count": row["chunk_count"],
                    "uploaded_at": parse_dt(row["uploaded_at"])
                }
            )

        # D. Document Chunks
        cur.execute("SELECT id, document_id, organization_id, content, embedding, chunk_metadata FROM document_chunks")
        chunk_rows = cur.fetchall()
        logger.info("Migrating %d document chunks with embeddings...", len(chunk_rows))
        for row in chunk_rows:
            # Parse embedding list
            emb = row["embedding"]
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except Exception:
                    emb = None

            # Parse chunk_metadata
            meta = row["chunk_metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            await pg_conn.execute(
                text("""
                    INSERT INTO document_chunks (id, document_id, organization_id, content, embedding, chunk_metadata)
                    VALUES (:id, :document_id, :organization_id, :content, :embedding, :chunk_metadata)
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "organization_id": row["organization_id"],
                    "content": row["content"],
                    "embedding": str(emb) if emb else None,
                    "chunk_metadata": json.dumps(meta) if meta else "{}"
                }
            )

        # E. Query Logs
        cur.execute("SELECT id, user_id, organization_id, question, model_used, cache_hit, input_tokens, output_tokens, estimated_cost, latency_ms, created_at FROM query_logs")
        log_rows = cur.fetchall()
        logger.info("Migrating %d query logs...", len(log_rows))
        for row in log_rows:
            await pg_conn.execute(
                text("""
                    INSERT INTO query_logs (id, user_id, organization_id, question, model_used, cache_hit, input_tokens, output_tokens, estimated_cost, latency_ms, created_at)
                    VALUES (:id, :user_id, :organization_id, :question, :model_used, :cache_hit, :input_tokens, :output_tokens, :estimated_cost, :latency_ms, :created_at)
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "organization_id": row["organization_id"],
                    "question": row["question"],
                    "model_used": row["model_used"],
                    "cache_hit": bool(row["cache_hit"]),
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "estimated_cost": row["estimated_cost"],
                    "latency_ms": row["latency_ms"],
                    "created_at": parse_dt(row["created_at"])
                }
            )

    sqlite_conn.close()
    logger.info("[SUCCESS] All local SQLite data successfully synchronized into Supabase PostgreSQL!")


if __name__ == "__main__":
    asyncio.run(sync())
