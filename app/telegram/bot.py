import logging
import re
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from app.config import settings
from app.telegram.handlers import (
    handle_start,
    handle_user,
    handle_help,
    handle_logout,
    handle_text_message,
    handle_callback_query
)
from app.admin.handlers import (
    handle_bot_admin,
    handle_create_org,
    handle_list_orgs,
    handle_admin_command,
    handle_add_user,
    handle_delete_doc,
    handle_admin_stats,
    handle_admin_users,
    handle_admin_usage,
    handle_admin_documents,
    handle_admin_upload_prompt,
    handle_admin_document_upload
)

logger = logging.getLogger(__name__)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global unhandled exception handler to protect polling loop."""
    logger.error("Exception while handling Telegram update %s: %s", update, context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            err_str = str(context.error)
            if "can't parse entities" in err_str.lower():
                logger.info("Markdown parse failure suppressed cleanly.")
            else:
                await update.effective_message.reply_text(
                    "⚠️ An unexpected error occurred while processing your request. Please try again."
                )
        except Exception:
            pass


def build_telegram_application() -> Application:
    """Build and configure the Telegram Bot Application."""
    if not settings.telegram.is_configured:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured in .env. Bot polling cannot start until configured.")

    app = ApplicationBuilder().token(settings.telegram.token_plain).build()

    # Register global error handler
    app.add_error_handler(global_error_handler)

    # Core commands
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("user", handle_user))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("logout", handle_logout))

    # Super Bot Admin commands (Platform Owner)
    app.add_handler(CommandHandler("botadmin", handle_bot_admin))
    app.add_handler(CommandHandler("superadmin", handle_bot_admin))
    app.add_handler(CommandHandler("create_org", handle_create_org))
    app.add_handler(CommandHandler("list_orgs", handle_list_orgs))

    # Org Admin commands (Tenant Administrator)
    app.add_handler(CommandHandler("admin", handle_admin_command))
    app.add_handler(CommandHandler("add_user", handle_add_user))
    app.add_handler(CommandHandler("admin_add_user", handle_add_user))
    app.add_handler(CommandHandler("delete_doc", handle_delete_doc))
    app.add_handler(CommandHandler("admin_delete_doc", handle_delete_doc))
    app.add_handler(CommandHandler("admin_stats", handle_admin_stats))
    app.add_handler(CommandHandler("admin_users", handle_admin_users))
    app.add_handler(CommandHandler("admin_usage", handle_admin_usage))
    app.add_handler(CommandHandler("admin_documents", handle_admin_documents))
    app.add_handler(CommandHandler("upload", handle_admin_upload_prompt))
    app.add_handler(CommandHandler("upload_doc", handle_admin_upload_prompt))
    app.add_handler(CommandHandler("admin_upload", handle_admin_upload_prompt))

    # Handle /admin/xyz style commands via regex filter
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/stats\b"), handle_admin_stats))
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/users\b"), handle_admin_users))
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/usage\b"), handle_admin_usage))
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/documents\b"), handle_admin_documents))
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/add_user\b"), handle_add_user))
    app.add_handler(MessageHandler(filters.Regex(r"^/admin/upload\b"), handle_admin_upload_prompt))

    # Document upload handler (PDF, TXT, DOCX files)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_admin_document_upload))

    # Interactive inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Plain text messages (Auth steps, Bot Admin inputs, Org Admin inputs, and RAG queries)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))

    return app
