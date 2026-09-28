import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dynamically locate the .env file relative to the project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = os.getenv("ENV_FILE", str(BASE_DIR / ".env"))


# ==============================================================================
# Domain-Specific Structured Configurations
# ==============================================================================

class TelegramConfig(BaseModel):
    """Structured configuration for Telegram Bot interaction."""
    bot_token: SecretStr = Field(default=SecretStr(""), description="Bot token issued by @BotFather")
    mode: Literal["polling", "webhook"] = Field(default="polling", description="'polling' for dev, 'webhook' for prod")
    webhook_url: Optional[str] = Field(default=None, description="Public HTTPS URL for Telegram webhooks")
    secret_token: Optional[SecretStr] = Field(default=None, description="Secret token validating Telegram webhook requests")

    @property
    def is_configured(self) -> bool:
        val = self.bot_token.get_secret_value().strip()
        return bool(val and val != "dummy_telegram_bot_token")

    @property
    def token_plain(self) -> str:
        return self.bot_token.get_secret_value()

    @property
    def secret_token_plain(self) -> Optional[str]:
        return self.secret_token.get_secret_value() if self.secret_token else None


class DatabaseConfig(BaseModel):
    """Structured configuration for Supabase PostgreSQL database."""
    url: SecretStr = Field(default=SecretStr(""), description="SQLAlchemy async connection URL for Supabase/PostgreSQL")
    echo: bool = Field(default=False, description="Log raw SQL queries")

    @property
    def is_configured(self) -> bool:
        val = self.url.get_secret_value().strip()
        return bool(val)

    @property
    def url_plain(self) -> str:
        return self.url.get_secret_value()

    @property
    def masked_url(self) -> str:
        raw = self.url.get_secret_value().strip()
        if not raw:
            return "sqlite+aiosqlite:///./enterprise_rag.db (Local Fallback)"
        # Mask password in postgresql://user:password@host...
        return re.sub(r":([^:@]+)@", ":****@", raw)


class SupabaseConfig(BaseModel):
    """Structured configuration for Supabase Storage and Client."""
    url: str = Field(default="", description="Supabase project URL")
    service_role_key: SecretStr = Field(default=SecretStr(""), description="Supabase service role secret key")
    bucket: str = Field(default="enterprise-documents", description="Storage bucket name for documents")
    local_fallback_dir: str = Field(default="./storage_fallback", description="Local fallback directory if Supabase is unavailable")

    @property
    def is_configured(self) -> bool:
        url_clean = self.url.strip()
        key_clean = self.service_role_key.get_secret_value().strip()
        return bool(
            url_clean
            and "your-project" not in url_clean
            and key_clean
            and "your-supabase" not in key_clean
        )

    @property
    def service_role_key_plain(self) -> str:
        return self.service_role_key.get_secret_value()


class GeminiConfig(BaseModel):
    """Structured configuration for Google Gemini models and embeddings."""
    api_key: SecretStr = Field(default=SecretStr(""), description="Google Gemini API Key from Google AI Studio")
    model_simple: str = Field(default="gemini-2.0-flash-lite", description="Lightweight model for straightforward queries")
    model_complex: str = Field(default="gemini-2.0-flash", description="High-reasoning model for complex queries")
    embedding_model: str = Field(default="models/text-embedding-004", description="Embedding model for pgvector")
    embedding_dimension: int = Field(default=768, description="Vector dimension of embeddings")

    @property
    def is_configured(self) -> bool:
        val = self.api_key.get_secret_value().strip()
        return bool(val and "your-gemini" not in val)

    @property
    def api_key_plain(self) -> str:
        return self.api_key.get_secret_value()


class RedisConfig(BaseModel):
    """Structured configuration for Redis semantic cache and OTP state."""
    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    use_fakeredis_fallback: bool = Field(default=True, description="Fallback to in-memory fakeredis if Redis is down")


class RAGConfig(BaseModel):
    """Structured hyperparameters for RAG chunking and vector retrieval."""
    top_k: int = Field(default=4, ge=1, le=20, description="Top-K chunks to retrieve")
    similarity_threshold: float = Field(default=0.45, ge=0.0, le=1.0, description="Minimum cosine similarity")
    chunk_size: int = Field(default=600, ge=100, le=5000, description="Max characters per chunk")
    chunk_overlap: int = Field(default=100, ge=0, le=500, description="Character overlap between consecutive chunks")


class SemanticCacheConfig(BaseModel):
    """Structured settings for semantic cache similarity matching."""
    threshold: float = Field(default=0.90, ge=0.0, le=1.0, description="Cosine similarity threshold for cache hit")
    ttl_seconds: int = Field(default=86400, ge=60, description="Cache entry TTL in seconds")


class AuthConfig(BaseModel):
    """Structured settings for OTP and Session authentication."""
    otp_ttl_seconds: int = Field(default=300, ge=30, description="Time-to-live for OTP verification code")
    mock_otp_mode: bool = Field(default=True, description="Prints OTP in console/hints for frictionless testing")


# ==============================================================================
# Central Settings Class (Loads strictly from .env and os.environ)
# ==============================================================================

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General App Config
    APP_NAME: str = "Enterprise AI Telegram Assistant"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 1. Telegram Bot Settings
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_MODE: str = "polling"
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_SECRET_TOKEN: Optional[str] = None

    # 2. Database Settings (Supabase PostgreSQL / pgvector)
    DATABASE_URL: str = ""
    DB_ECHO: bool = False

    # 3. Supabase Storage & REST Client
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_BUCKET: str = "enterprise-documents"
    STORAGE_LOCAL_FALLBACK_DIR: str = "./storage_fallback"

    # 4. Redis Semantic Cache & State
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_FAKEREDIS_FALLBACK: bool = True

    # 5. Google Gemini API
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_SIMPLE: str = "gemini-3.5-flash-lite"
    GEMINI_MODEL_COMPLEX: str = "gemini-3.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768

    # 6. Semantic Cache Settings
    SEMANTIC_CACHE_THRESHOLD: float = 0.90
    SEMANTIC_CACHE_TTL_SECONDS: int = 86400

    # 7. RAG Hyperparameters
    RAG_TOP_K: int = 4
    RAG_SIMILARITY_THRESHOLD: float = 0.45
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100

    # 8. Authentication & OTP
    OTP_TTL_SECONDS: int = 300
    MOCK_OTP_MODE: bool = True

    # 9. Super Bot Admin Config
    BOT_ADMIN_SECRET: str = "superadmin123"
    BOT_ADMIN_TELEGRAM_IDS: str = ""

    # 10. Display / Telemetry Badges
    SHOW_DEBUG_BADGES: bool = False

    @property
    def bot_admin_ids_list(self) -> list[int]:
        if not self.BOT_ADMIN_TELEGRAM_IDS.strip():
            return []
        ids = []
        for x in self.BOT_ADMIN_TELEGRAM_IDS.split(","):
            x_clean = x.strip()
            if x_clean.isdigit():
                ids.append(int(x_clean))
        return ids

    # Structured Domain Accessors
    @property
    def telegram(self) -> TelegramConfig:
        return TelegramConfig(
            bot_token=SecretStr(self.TELEGRAM_BOT_TOKEN),
            mode=self.TELEGRAM_MODE,  # type: ignore
            webhook_url=self.TELEGRAM_WEBHOOK_URL,
            secret_token=SecretStr(self.TELEGRAM_SECRET_TOKEN) if self.TELEGRAM_SECRET_TOKEN else None
        )

    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(
            url=SecretStr(self.DATABASE_URL),
            echo=self.DB_ECHO
        )

    @property
    def supabase(self) -> SupabaseConfig:
        return SupabaseConfig(
            url=self.SUPABASE_URL,
            service_role_key=SecretStr(self.SUPABASE_SERVICE_ROLE_KEY),
            bucket=self.SUPABASE_BUCKET,
            local_fallback_dir=self.STORAGE_LOCAL_FALLBACK_DIR
        )

    @property
    def gemini(self) -> GeminiConfig:
        return GeminiConfig(
            api_key=SecretStr(self.GEMINI_API_KEY),
            model_simple=self.GEMINI_MODEL_SIMPLE,
            model_complex=self.GEMINI_MODEL_COMPLEX,
            embedding_model=self.GEMINI_EMBEDDING_MODEL,
            embedding_dimension=self.EMBEDDING_DIMENSION
        )

    @property
    def redis(self) -> RedisConfig:
        return RedisConfig(
            url=self.REDIS_URL,
            use_fakeredis_fallback=self.USE_FAKEREDIS_FALLBACK
        )

    @property
    def rag(self) -> RAGConfig:
        return RAGConfig(
            top_k=self.RAG_TOP_K,
            similarity_threshold=self.RAG_SIMILARITY_THRESHOLD,
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP
        )

    @property
    def semantic_cache(self) -> SemanticCacheConfig:
        return SemanticCacheConfig(
            threshold=self.SEMANTIC_CACHE_THRESHOLD,
            ttl_seconds=self.SEMANTIC_CACHE_TTL_SECONDS
        )

    @property
    def auth(self) -> AuthConfig:
        return AuthConfig(
            otp_ttl_seconds=self.OTP_TTL_SECONDS,
            mock_otp_mode=self.MOCK_OTP_MODE
        )

    def get_masked_summary(self) -> Dict[str, Any]:
        """Return a safe audit representation without revealing secrets."""
        return {
            "app_name": self.APP_NAME,
            "app_env": self.APP_ENV,
            "debug": self.DEBUG,
            "telegram": {
                "configured": self.telegram.is_configured,
                "mode": self.telegram.mode,
                "webhook_url": self.telegram.webhook_url
            },
            "database": {
                "configured": self.database.is_configured,
                "target": self.database.masked_url,
                "echo": self.database.echo
            },
            "supabase": {
                "configured": self.supabase.is_configured,
                "url": self.supabase.url or "(not configured)",
                "bucket": self.supabase.bucket,
                "has_service_role_key": bool(self.supabase.service_role_key.get_secret_value())
            },
            "gemini": {
                "configured": self.gemini.is_configured,
                "model_simple": self.gemini.model_simple,
                "model_complex": self.gemini.model_complex,
                "embedding_model": self.gemini.embedding_model,
                "embedding_dimension": self.gemini.embedding_dimension
            },
            "redis": {
                "url": self.redis.url,
                "use_fakeredis_fallback": self.redis.use_fakeredis_fallback
            },
            "rag": {
                "top_k": self.rag.top_k,
                "similarity_threshold": self.rag.similarity_threshold,
                "chunk_size": self.rag.chunk_size,
                "chunk_overlap": self.rag.chunk_overlap
            },
            "auth": {
                "otp_ttl_seconds": self.auth.otp_ttl_seconds,
                "mock_otp_mode": self.auth.mock_otp_mode
            }
        }


# Global singleton instance
settings = Settings()
