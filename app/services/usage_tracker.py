import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories import QueryLogRepository
from app.db.models import QueryLog

logger = logging.getLogger(__name__)


class UsageTracker:
    @staticmethod
    async def log_query(
        session: AsyncSession,
        organization_id: str,
        question: str,
        model_used: str,
        cache_hit: bool,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        latency_ms: float,
        user_id: Optional[str] = None
    ) -> QueryLog:
        """
        Record query execution telemetry into database for audit and analytics.
        """
        repo = QueryLogRepository(session)
        log = await repo.create(
            organization_id=organization_id,
            question=question,
            model_used=model_used,
            cache_hit=cache_hit,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
            user_id=user_id
        )
        logger.info(
            "Logged query [org=%s, user=%s, model=%s, cache_hit=%s, tokens=%d, cost=$%.6f, lat=%.1fms]",
            organization_id, user_id or "anon", model_used, cache_hit,
            input_tokens + output_tokens, estimated_cost, latency_ms
        )
        return log


usage_tracker = UsageTracker()
