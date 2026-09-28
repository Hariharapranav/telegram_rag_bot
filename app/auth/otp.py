import logging
import secrets
import time
from typing import Optional, Dict, Any
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class OTPService:
    def __init__(
        self,
        redis_url: str = settings.REDIS_URL,
        ttl_seconds: int = settings.OTP_TTL_SECONDS
    ):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client: Optional[aioredis.Redis] = None
        self._fallback_store: Dict[str, Dict[str, Any]] = {}
        self._use_fallback = False

    async def get_client(self) -> aioredis.Redis:
        if self._client is None and not self._use_fallback:
            try:
                client = aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    decode_responses=True
                )
                await client.ping()
                self._client = client
            except Exception:
                self._use_fallback = True
        return self._client

    async def generate_otp(self, identifier: str) -> str:
        """
        Generate a secure 6-digit OTP code and store it with TTL.
        identifier: e.g. "emp:user_uuid" or "admin:user_uuid"
        """
        code = f"{secrets.randbelow(900000) + 100000}"
        redis_key = f"otp:{identifier}"

        if self._use_fallback or self._client is None:
            await self.get_client()

        if self._use_fallback:
            self._fallback_store[redis_key] = {
                "code": code,
                "expires_at": time.time() + self.ttl_seconds
            }
        else:
            try:
                client = await self.get_client()
                await client.setex(redis_key, self.ttl_seconds, code)
            except Exception as e:
                logger.warning("Redis OTP write failed: %s. Using fallback store.", e)
                self._use_fallback = True
                self._fallback_store[redis_key] = {
                    "code": code,
                    "expires_at": time.time() + self.ttl_seconds
                }

        logger.info("🔑 [SECURITY AUDIT] OTP Generated for %s: %s (expires in %ds)", identifier, code, self.ttl_seconds)
        return code

    async def verify_otp(self, identifier: str, user_provided_code: str) -> bool:
        """Verify the user-entered OTP against the stored code."""
        redis_key = f"otp:{identifier}"
        stored_code = None

        if self._use_fallback or self._client is None:
            await self.get_client()

        if self._use_fallback:
            entry = self._fallback_store.get(redis_key)
            if entry:
                if entry["expires_at"] >= time.time():
                    stored_code = entry["code"]
                self._fallback_store.pop(redis_key, None)
        else:
            try:
                client = await self.get_client()
                stored_code = await client.get(redis_key)
                if stored_code:
                    await client.delete(redis_key)
            except Exception as e:
                logger.warning("Redis OTP read failed: %s. Checking fallback store.", e)
                entry = self._fallback_store.get(redis_key)
                if entry and entry["expires_at"] >= time.time():
                    stored_code = entry["code"]
                    self._fallback_store.pop(redis_key, None)

        if not stored_code:
            logger.warning("OTP verification failed: No active OTP for %s", identifier)
            return False

        is_valid = secrets.compare_digest(stored_code.strip(), user_provided_code.strip())
        logger.info("OTP verification for %s: %s", identifier, "SUCCESS" if is_valid else "INVALID_CODE")
        return is_valid


otp_service = OTPService()
