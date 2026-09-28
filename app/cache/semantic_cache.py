import json
import logging
import math
import struct
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    """
    Multi-tenant Semantic Cache backed by Redis with in-memory fallback.
    Guarantees strict organization-level isolation.
    """

    def __init__(
        self,
        redis_url: str = settings.REDIS_URL,
        threshold: float = settings.SEMANTIC_CACHE_THRESHOLD,
        ttl_seconds: int = settings.SEMANTIC_CACHE_TTL_SECONDS
    ):
        self.redis_url = redis_url
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._client: Optional[aioredis.Redis] = None
        self._fallback_store: Dict[str, Dict[str, Any]] = {}
        self._use_fallback = False

    async def get_client(self) -> aioredis.Redis:
        if self._client is None and not self._use_fallback:
            try:
                client = aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                    decode_responses=False
                )
                await client.ping()
                self._client = client
                logger.info("Connected to Redis semantic cache at %s", self.redis_url)
            except Exception as e:
                logger.warning("Redis connection failed (%s). Falling back to in-memory cache.", str(e))
                self._use_fallback = True
        return self._client

    async def lookup(
        self,
        organization_id: str,
        query_embedding: List[float],
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Check semantic cache strictly within the given organization_id.
        Returns match dict if similarity >= threshold, else cache_hit=False.
        """
        cutoff = threshold if threshold is not None else self.threshold
        best_match: Optional[Dict[str, Any]] = None
        best_sim = -1.0

        if self._use_fallback or self._client is None:
            await self.get_client()

        if self._use_fallback:
            # In-memory fallback
            now = time.time()
            org_items = self._fallback_store.get(organization_id, {})
            expired_keys = []
            for entry_id, item in org_items.items():
                if item["expires_at"] < now:
                    expired_keys.append(entry_id)
                    continue
                sim = cosine_similarity(query_embedding, item["embedding"])
                if sim > best_sim:
                    best_sim = sim
                    best_match = item
            for exp in expired_keys:
                org_items.pop(exp, None)
        else:
            try:
                client = await self.get_client()
                index_key = f"semantic_cache:org:{organization_id}:keys"
                entry_keys = await client.smembers(index_key)
                if not entry_keys:
                    return {"cache_hit": False, "similarity": 0.0}

                pipe = client.pipeline()
                for key_bytes in entry_keys:
                    pipe.get(key_bytes)
                results = await pipe.execute()

                stale_keys = []
                for key_bytes, raw_val in zip(entry_keys, results):
                    if raw_val is None:
                        stale_keys.append(key_bytes)
                        continue
                    try:
                        data = json.loads(raw_val.decode("utf-8"))
                        cached_emb = data["question_embedding"]
                        sim = cosine_similarity(query_embedding, cached_emb)
                        if sim > best_sim:
                            best_sim = sim
                            best_match = data
                    except Exception as parse_err:
                        logger.error("Error parsing cached item: %s", parse_err)

                if stale_keys:
                    await client.srem(index_key, *stale_keys)

            except Exception as e:
                logger.warning("Error reading from Redis cache: %s. Switching to fallback.", e)
                self._use_fallback = True
                return await self.lookup(organization_id, query_embedding, threshold)

        if best_match and best_sim >= cutoff:
            logger.info("Semantic cache HIT for org %s (similarity: %.4f >= %.4f)", organization_id, best_sim, cutoff)
            return {
                "cache_hit": True,
                "similarity": best_sim,
                "answer": best_match["answer"],
                "question": best_match["question"],
                "model_used": best_match.get("model_used", "cached"),
                "created_at": best_match.get("created_at")
            }

        logger.info("Semantic cache MISS for org %s (best similarity: %.4f < %.4f)", organization_id, max(best_sim, 0.0), cutoff)
        return {
            "cache_hit": False,
            "similarity": max(best_sim, 0.0)
        }

    async def store(
        self,
        organization_id: str,
        question: str,
        question_embedding: Optional[List[float]] = None,
        answer: str = "",
        model_used: str = "",
        ttl_seconds: Optional[int] = None,
        embedding: Optional[List[float]] = None
    ) -> None:
        """
        Store a generated question-answer pair isolated by organization_id.
        """
        actual_embedding = question_embedding if question_embedding is not None else embedding
        if actual_embedding is None:
            actual_embedding = []
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        now = time.time()
        created_at_iso = datetime.now(timezone.utc).isoformat()
        entry_id = f"entry:{organization_id}:{int(now * 1000)}"

        entry_data = {
            "organization_id": organization_id,
            "question": question,
            "question_embedding": actual_embedding,
            "answer": answer,
            "model_used": model_used,
            "created_at": created_at_iso,
            "expiration": ttl
        }

        if self._use_fallback or self._client is None:
            await self.get_client()

        if self._use_fallback:
            if organization_id not in self._fallback_store:
                self._fallback_store[organization_id] = {}
            self._fallback_store[organization_id][entry_id] = {
                **entry_data,
                "embedding": question_embedding,
                "expires_at": now + ttl
            }
        else:
            try:
                client = await self.get_client()
                serialized = json.dumps(entry_data)
                redis_key = f"semantic_cache:entry:{organization_id}:{entry_id}"
                index_key = f"semantic_cache:org:{organization_id}:keys"

                pipe = client.pipeline()
                pipe.setex(redis_key, ttl, serialized)
                pipe.sadd(index_key, redis_key)
                pipe.expire(index_key, ttl + 3600)
                await pipe.execute()
            except Exception as e:
                logger.warning("Error writing to Redis cache: %s. Using in-memory fallback.", e)
                self._use_fallback = True
                if organization_id not in self._fallback_store:
                    self._fallback_store[organization_id] = {}
                self._fallback_store[organization_id][entry_id] = {
                    **entry_data,
                    "embedding": question_embedding,
                    "expires_at": now + ttl
                }

    async def clear_org(self, organization_id: str) -> None:
        """Clear cache for a specific organization."""
        if organization_id in self._fallback_store:
            self._fallback_store.pop(organization_id, None)

        if not self._use_fallback and self._client:
            try:
                index_key = f"semantic_cache:org:{organization_id}:keys"
                keys = await self._client.smembers(index_key)
                if keys:
                    await self._client.delete(*keys)
                await self._client.delete(index_key)
            except Exception as e:
                logger.error("Error clearing Redis cache for org %s: %s", organization_id, e)


# Global singleton instance
semantic_cache = SemanticCache()
