import pytest
from pydantic import SecretStr
from app.config import Settings, TelegramConfig, DatabaseConfig, SupabaseConfig, GeminiConfig


def test_structured_config_properties():
    settings = Settings()
    
    # Check that structured domain objects exist
    assert hasattr(settings, "telegram")
    assert hasattr(settings, "database")
    assert hasattr(settings, "supabase")
    assert hasattr(settings, "gemini")
    assert hasattr(settings, "redis")
    assert hasattr(settings, "rag")
    assert hasattr(settings, "semantic_cache")
    assert hasattr(settings, "auth")


def test_secret_masking():
    telegram_cfg = TelegramConfig(bot_token=SecretStr("super_secret_bot_token_12345"))
    
    # Printing or stringifying should mask the secret
    assert "super_secret_bot_token_12345" not in str(telegram_cfg.bot_token)
    assert "super_secret_bot_token_12345" not in repr(telegram_cfg.bot_token)
    assert telegram_cfg.token_plain == "super_secret_bot_token_12345"
    assert telegram_cfg.is_configured is True


def test_database_url_masking():
    db_cfg = DatabaseConfig(
        url=SecretStr("postgresql+asyncpg://postgres:mysecretpassword@db.xyz.supabase.co:5432/postgres")
    )
    
    assert "mysecretpassword" not in db_cfg.masked_url
    assert "****" in db_cfg.masked_url
    assert db_cfg.is_configured is True


def test_masked_summary_does_not_leak_secrets():
    settings = Settings(
        TELEGRAM_BOT_TOKEN="my_telegram_token",
        GEMINI_API_KEY="my_gemini_key",
        DATABASE_URL="postgresql+asyncpg://postgres:secretpass@db.xyz.supabase.co:5432/postgres",
        SUPABASE_SERVICE_ROLE_KEY="my_service_role_key"
    )
    
    summary = settings.get_masked_summary()
    summary_str = str(summary)
    
    # Confirm no sensitive secret tokens appear in plain text
    assert "my_telegram_token" not in summary_str
    assert "my_gemini_key" not in summary_str
    assert "secretpass" not in summary_str
    assert "my_service_role_key" not in summary_str
