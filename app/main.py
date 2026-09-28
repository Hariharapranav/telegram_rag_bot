import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from app.config import settings
from app.db.database import get_db, engine, Base
from app.db.repositories import OrganizationRepository, QueryLogRepository
from app.services.document_service import document_service
from app.admin.analytics import admin_analytics
from app.cache.semantic_cache import semantic_cache
from app.telegram.bot import build_telegram_application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

telegram_app = None
bot_polling_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, bot_polling_task

    # 1. Initialize DB tables
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            try:
                from sqlalchemy import text
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                logger.info("pgvector extension verified.")
            except Exception as exc:
                logger.warning("Could not create pgvector extension automatically: %s", exc)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")

    # 2. Initialize Telegram Bot
    if settings.telegram.is_configured:
        try:
            telegram_app = build_telegram_application()
            await telegram_app.initialize()
            await telegram_app.start()

            if settings.telegram.mode == "polling":
                logger.info("Starting Telegram bot in POLLING mode...")
                await telegram_app.updater.start_polling(drop_pending_updates=True)
            elif settings.telegram.mode == "webhook" and settings.telegram.webhook_url:
                logger.info("Setting Telegram webhook to: %s", settings.telegram.webhook_url)
                await telegram_app.bot.set_webhook(
                    url=settings.telegram.webhook_url,
                    secret_token=settings.telegram.secret_token_plain
                )
        except Exception as e:
            logger.error("Failed to start Telegram bot: %s", e)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured in .env. Running in API-only mode.")

    yield

    # Shutdown
    if telegram_app:
        logger.info("Shutting down Telegram Bot...")
        if settings.TELEGRAM_MODE == "polling" and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-tenant Enterprise RAG Assistant powered by Telegram, Gemini, and Supabase",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint validating database and cache connectivity."""
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(Base.metadata.tables["organizations"].select().limit(1))
            db_ok = True
    except Exception as e:
        logger.warning("DB health check error: %s", e)

    cache_client = await semantic_cache.get_client()
    redis_ok = not semantic_cache._use_fallback and (cache_client is not None)

    return {
        "status": "healthy" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "database_connected": db_ok,
        "redis_connected": redis_ok,
        "cache_mode": "redis" if redis_ok else "in_memory_fallback",
        "telegram_mode": settings.TELEGRAM_MODE
    }


@app.post("/api/telegram/webhook", tags=["Telegram"])
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    """Webhook listener for incoming Telegram updates."""
    if settings.TELEGRAM_SECRET_TOKEN and x_telegram_bot_api_secret_token != settings.TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret token")

    if not telegram_app:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot not initialized")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}


@app.post("/api/documents/upload", tags=["Documents"])
async def upload_document_api(
    organization_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Direct API endpoint for uploading and ingesting documents into pgvector.
    Guarantees organization data isolation.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {organization_id} not found")

    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        res = await document_service.upload_document(
            session=db,
            organization_id=organization_id,
            filename=file.filename or "uploaded_doc.txt",
            content_bytes=content_bytes
        )
        return {"status": "success", "data": res}
    except Exception as e:
        logger.error("API document upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/{organization_id}", tags=["Documents"])
async def list_documents_api(organization_id: str, db: AsyncSession = Depends(get_db)):
    """List all documents for an organization."""
    docs = await document_service.list_documents(db, organization_id)
    return {"organization_id": organization_id, "documents": docs}


@app.get("/api/admin/stats/{organization_id}", tags=["Analytics"])
async def get_org_stats_api(organization_id: str, db: AsyncSession = Depends(get_db)):
    """Get aggregated AI usage and latency metrics."""
    repo = QueryLogRepository(db)
    stats = await repo.get_org_stats(organization_id)
    return stats


@app.get("/api/admin/users/{organization_id}", tags=["Analytics"])
async def get_user_stats_api(organization_id: str, db: AsyncSession = Depends(get_db)):
    """Get user-wise query and token consumption breakdown."""
    repo = QueryLogRepository(db)
    users = await repo.get_user_stats(organization_id)
    return {"organization_id": organization_id, "users": users}


@app.get("/api/admin/usage/{organization_id}", tags=["Analytics"])
async def get_usage_feed_api(organization_id: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Get recent query telemetry logs."""
    repo = QueryLogRepository(db)
    logs = await repo.get_usage_summary(organization_id, limit=limit)
    return {"organization_id": organization_id, "logs": logs}
