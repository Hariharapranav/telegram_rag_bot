import logging
import io
from pathlib import Path
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.repositories import (
    OrganizationRepository,
    UserRepository,
    TelegramSessionRepository
)
from app.auth.service import auth_service
from app.auth.session import AuthState
from app.admin.analytics import admin_analytics
from app.services.document_service import document_service
from app.telegram.keyboards import (
    get_admin_menu_keyboard,
    get_bot_admin_menu_keyboard,
    get_documents_action_keyboard
)

logger = logging.getLogger(__name__)


async def safe_reply(msg, text: str, parse_mode: Optional[str] = "Markdown", reply_markup=None):
    """Safely send reply; fallback to plain text if Markdown entity parsing fails."""
    try:
        return await msg.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("Markdown reply failed (%s). Retrying as plain text.", e)
        try:
            return await msg.reply_text(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as exc:
            logger.error("Failed to send message: %s", exc)
            return None


# ==============================================================================
# 1. Super Bot Admin Handlers (Platform-Level Management)
# ==============================================================================

async def handle_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /botadmin or /superadmin command."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)

        # Check if already authenticated as bot_admin or in configured bot_admin_ids_list
        if user_sess.is_bot_admin or (tg_user_id in settings.bot_admin_ids_list):
            if not user_sess.is_bot_admin:
                repo = TelegramSessionRepository(session)
                await repo.upsert_session(
                    telegram_user_id=tg_user_id,
                    role="bot_admin",
                    auth_state=AuthState.AUTHENTICATED.value,
                    auth_context={}
                )

            reply_text = (
                "👑 **Super Bot Admin Control Panel**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "You have platform-level management privileges:\n\n"
                "• `/create_org` - Register a new enterprise organization & initial admin\n"
                "• `/list_orgs` - View all organizations & tenant stats\n"
                "• `/logout` - Log out of super admin session\n"
            )
            await safe_reply(
                msg,
                reply_text,
                parse_mode="Markdown",
                reply_markup=get_bot_admin_menu_keyboard()
            )
            return

        # Prompt for secret key
        repo = TelegramSessionRepository(session)
        await repo.upsert_session(
            telegram_user_id=tg_user_id,
            auth_state=AuthState.AWAITING_BOT_ADMIN_SECRET.value,
            auth_context={}
        )
        await safe_reply(
            msg,
            "👑 **Super Bot Admin Authentication**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Please enter the Bot Admin secret key to unlock platform administration:",
            parse_mode="Markdown"
        )


async def handle_create_org(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /create_org command or button click to register new tenant organization."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_bot_admin:
            await safe_reply(msg, "⛔ Access denied. Only Super Bot Admins can create organizations. Use /botadmin to authenticate.")
            return

        # Check if args provided on command line
        args_text = " ".join(context.args).strip() if (context and context.args) else ""
        if args_text:
            reply = await process_create_org_input(session, args_text)
            await safe_reply(msg, reply, parse_mode="Markdown")
            return

        # Transition to awaiting input state
        repo = TelegramSessionRepository(session)
        await repo.upsert_session(
            telegram_user_id=tg_user_id,
            auth_state=AuthState.AWAITING_CREATE_ORG_DATA.value,
            auth_context={}
        )
        prompt = (
            "🏢 **Create New Organization**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Please reply with the organization details in this format:\n"
            "`<org_id>, <org_name>, <admin_name>, <admin_email>, <admin_employee_id>`\n\n"
            "**Example:**\n"
            "`stark_corp, Stark Industries, Tony Stark, tony@stark.com, EMP-001`"
        )
        await safe_reply(msg, prompt, parse_mode="Markdown")


async def process_create_org_input(session, input_text: str) -> str:
    """Parse and execute organization + initial admin creation."""
    parts = [p.strip() for p in input_text.split(",") if p.strip()]
    if len(parts) < 2:
        parts = input_text.split()

    if len(parts) < 2:
        return (
            "❌ Invalid format. Please provide at least:\n"
            "`<org_id>, <org_name>`\n"
            "Or full:\n"
            "`<org_id>, <org_name>, <admin_name>, <admin_email>, <admin_employee_id>`"
        )

    org_id = parts[0].lower().replace(" ", "_")
    org_name = parts[1]
    admin_name = parts[2] if len(parts) > 2 else f"{org_name} Admin"
    admin_email = parts[3] if len(parts) > 3 else f"admin@{org_id}.com"
    admin_emp_id = parts[4] if len(parts) > 4 else "EMP-001"

    org_repo = OrganizationRepository(session)
    user_repo = UserRepository(session)

    # Check for duplicate org
    existing_org = await org_repo.get_by_id(org_id)
    if existing_org:
        existing_admin = await user_repo.get_by_employee_id(org_id, admin_emp_id)
        if not existing_admin:
            existing_admin = await user_repo.create(
                organization_id=existing_org.id,
                employee_id=admin_emp_id,
                name=admin_name,
                email=admin_email,
                role="admin"
            )
        return (
            f"✅ **Organization Ready!**\n\n"
            f"🏢 **Organization:** `{existing_org.name}` (`{existing_org.id}`)\n"
            f"👤 **Admin:** `{existing_admin.name}`\n"
            f"🆔 **Employee ID:** `{existing_admin.employee_id}`\n"
            f"📧 **Email:** `{existing_admin.email}`\n"
            f"🛡️ **Role:** `{existing_admin.role}`\n\n"
            f"💡 **Next Steps:**\n"
            f"The Org Admin can now type `/admin` to log in, add users via `/add_user`, and upload policy documents!"
        )

    # 1. Create Organization
    org = await org_repo.create(name=org_name, org_id=org_id)

    # 2. Create Initial Org Admin
    admin_user = await user_repo.create(
        organization_id=org.id,
        employee_id=admin_emp_id,
        name=admin_name,
        email=admin_email,
        role="admin"
    )

    return (
        f"✅ **Organization Successfully Created!**\n\n"
        f"🏢 **Organization:** `{org.name}` (`{org.id}`)\n"
        f"👤 **Initial Admin:** `{admin_user.name}`\n"
        f"🆔 **Employee ID:** `{admin_user.employee_id}`\n"
        f"📧 **Email:** `{admin_user.email}`\n"
        f"🛡️ **Role:** `admin`\n\n"
        f"💡 **Next Steps:**\n"
        f"The Org Admin can now type `/admin` to log in, add users via `/add_user`, and upload policy documents!"
    )


async def handle_list_orgs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list_orgs command or button click for Super Bot Admin."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_bot_admin:
            await safe_reply(msg, "⛔ Access denied. Only Super Bot Admins can list organizations.")
            return

        org_repo = OrganizationRepository(session)
        orgs = await org_repo.list_all_with_counts()

        if not orgs:
            await safe_reply(msg, "🏢 No organizations registered yet. Use `/create_org` to create one.", parse_mode="Markdown")
            return

        lines = [
            f"🏢 **Registered Organizations (Total: {len(orgs)})**\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for org in orgs:
            lines.append(
                f"🏢 `{org['name']}` (`{org['id']}`)\n"
                f"   • 👥 Users: `{org['user_count']}` | 📁 Documents: `{org['document_count']}`\n"
                f"   • Created: `{org['created_at'].strftime('%Y-%m-%d')}`"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 *Use `/create_org` to register a new tenant organization.*")

        await safe_reply(msg, "\n".join(lines), parse_mode="Markdown")


# ==============================================================================
# 2. Organization Admin Handlers (Tenant-Level Management)
# ==============================================================================

async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)

        if user_sess.is_admin and user_sess.organization_id:
            reply_text = (
                f"🛡️ **Admin Control Panel**\n"
                f"🏢 Organization: `{user_sess.organization_id}`\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Available commands:\n"
                "• `➕ Add User` / `/add_user` - Register an employee or admin\n"
                "• `📊 Stats` / `/admin/stats` - Organization AI & latency metrics\n"
                "• `👥 Users` / `/admin/users` - User-level query & cost breakdown\n"
                "• `📈 Usage` / `/admin/usage` - Real-time query activity feed\n"
                "• `📁 Documents` / `/admin/documents` - Ingested catalog & delete\n"
                "• `/delete_doc <id>` - Delete an uploaded document\n"
                "• `/logout` - Log out of admin session\n\n"
                "💡 *You can also drag & drop any PDF or TXT file into this chat to ingest it.*"
            )
            await safe_reply(
                msg,
                reply_text,
                parse_mode="Markdown",
                reply_markup=get_admin_menu_keyboard()
            )
            return

        # Check if already authenticated user has admin role in the database
        if user_sess.user_id and user_sess.organization_id:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_id(user_sess.user_id)
            if db_user and db_user.role == "admin":
                repo = TelegramSessionRepository(session)
                await repo.upsert_session(
                    telegram_user_id=tg_user_id,
                    user_id=db_user.id,
                    organization_id=db_user.organization_id,
                    role="admin",
                    auth_state=AuthState.AUTHENTICATED.value,
                    auth_context={}
                )
                reply_text = (
                    f"🛡️ **Admin Control Panel**\n"
                    f"🏢 Organization: `{db_user.organization_id}`\n"
                    f"👤 Admin: **{db_user.name}** (`{db_user.employee_id}`)\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Available commands:\n"
                    "• `➕ Add User` / `/add_user` - Register an employee or admin\n"
                    "• `📊 Stats` / `/admin/stats` - Organization AI & latency metrics\n"
                    "• `👥 Users` / `/admin/users` - User-level query & cost breakdown\n"
                    "• `📈 Usage` / `/admin/usage` - Real-time query activity feed\n"
                    "• `📁 Documents` / `/admin/documents` - Ingested catalog & delete\n"
                    "• `/delete_doc <id>` - Delete an uploaded document\n"
                    "• `/logout` - Log out of admin session\n\n"
                    "💡 *You can also drag & drop any PDF or TXT file into this chat to ingest it.*"
                )
                await safe_reply(
                    msg,
                    reply_text,
                    parse_mode="Markdown",
                    reply_markup=get_admin_menu_keyboard()
                )
                return

        # Start admin login flow
        reply = await auth_service.start_admin_auth(session, tg_user_id)
        await safe_reply(msg, reply, parse_mode="Markdown")


async def handle_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add_user command or button click for Organization Admin."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate as an Organization Admin via /admin first.")
            return

        # Check if arguments provided
        args_text = " ".join(context.args).strip() if (context and context.args) else ""
        if args_text:
            reply = await process_add_user_input(session, user_sess.organization_id, args_text)
            await safe_reply(msg, reply, parse_mode="Markdown")
            return

        # Set awaiting user data state
        repo = TelegramSessionRepository(session)
        await repo.upsert_session(
            telegram_user_id=tg_user_id,
            auth_state=AuthState.AWAITING_ADD_USER_DATA.value,
            auth_context={"organization_id": user_sess.organization_id}
        )
        prompt = (
            "👥 **Add User to Organization**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Please reply with user details in this format:\n"
            "`<employee_id>, <name>, <email>, <role>`\n\n"
            "**Example:**\n"
            "`EMP-005, John Doe, john@acme.com, employee`\n\n"
            "*(Role can be 'employee' or 'admin')*"
        )
        await safe_reply(msg, prompt, parse_mode="Markdown")


async def process_add_user_input(session, organization_id: str, input_text: str) -> str:
    """Parse and create a new user in the organization."""
    parts = [p.strip() for p in input_text.split(",") if p.strip()]
    if len(parts) < 3:
        parts = input_text.split()

    if len(parts) < 3:
        return (
            "❌ Invalid format. Please enter:\n"
            "`<employee_id>, <name>, <email>, <role>`\n"
            "Example: `EMP-005, John Doe, john@acme.com, employee`"
        )

    emp_id = parts[0].upper()
    name = parts[1]
    email = parts[2].lower()
    role = parts[3].lower() if len(parts) > 3 else "employee"

    if role not in ("employee", "admin"):
        role = "employee"

    user_repo = UserRepository(session)

    # Check if employee ID already exists in this organization
    existing = await user_repo.get_by_employee_id(organization_id, emp_id)
    if existing:
        return f"❌ Employee ID `{emp_id}` is already registered for **{existing.name}** in this organization."

    # Create user
    new_user = await user_repo.create(
        organization_id=organization_id,
        employee_id=emp_id,
        name=name,
        email=email,
        role=role
    )

    return (
        f"✅ **User Registered Successfully!**\n\n"
        f"👤 **Name:** {new_user.name}\n"
        f"🆔 **Employee ID:** `{new_user.employee_id}`\n"
        f"📧 **Email:** `{new_user.email}`\n"
        f"🛡️ **Role:** `{new_user.role}`\n"
        f"🏢 **Organization:** `{organization_id}`\n\n"
        f"The employee can now start chatting with the bot by typing `/start` and entering `{new_user.employee_id}`!"
    )


async def handle_delete_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete_doc <id> command for Organization Admin."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate as an Organization Admin via /admin first.")
            return

        if not context.args:
            await safe_reply(
                msg,
                "❌ Please specify the Document ID to delete.\n"
                "Usage: `/delete_doc <document_id>`\n"
                "Tip: Type `/admin/documents` to view your documents and their IDs.",
                parse_mode="Markdown"
            )
            return

        doc_id = context.args[0].strip()
        deleted = await document_service.delete_document(session, user_sess.organization_id, doc_id)
        if deleted:
            await safe_reply(
                msg,
                f"🗑️ **Document Deleted!**\n\n"
                f"Document `{doc_id}` and all associated vector chunks have been removed from your organization's knowledge base.",
                parse_mode="Markdown"
            )
        else:
            await safe_reply(
                msg,
                f"❌ Document `{doc_id}` was not found in your organization.",
                parse_mode="Markdown"
            )


async def handle_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin/stats."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate via /admin first.")
            return

        report = await admin_analytics.get_stats_summary(session, user_sess.organization_id)
        await safe_reply(msg, report, parse_mode="Markdown")


async def handle_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin/users."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate via /admin first.")
            return

        report = await admin_analytics.get_users_summary(session, user_sess.organization_id)
        await safe_reply(msg, report, parse_mode="Markdown")


async def handle_admin_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin/usage."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate via /admin first.")
            return

        report = await admin_analytics.get_usage_feed(session, user_sess.organization_id)
        await safe_reply(msg, report, parse_mode="Markdown")


async def handle_admin_documents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin/documents."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate via /admin first.")
            return

        report = await admin_analytics.get_documents_summary(session, user_sess.organization_id)
        await safe_reply(msg, report, parse_mode="Markdown", reply_markup=get_documents_action_keyboard())


async def handle_admin_upload_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /upload or 'Upload Document' button click: prompt admin on how to upload documents."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Access denied. Please authenticate as an Organization Admin via /admin first.")
            return

        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_id(user_sess.organization_id)
        org_name = org.name if org else user_sess.organization_id

        prompt = (
            "📤 **Upload Knowledge Base Document**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 **Target Organization:** `{org_name}`\n\n"
            "📎 **How to Upload:**\n"
            "Simply attach or drag & drop your document directly into this chat!\n\n"
            "📋 **Allowed Formats:**\n"
            "• 📄 **PDF** (`.pdf`)\n"
            "• 📝 **Plain Text** (`.txt`)\n"
            "• 📘 **Word Document** (`.docx`)\n"
            "• 📑 **Markdown** (`.md`)\n\n"
            "⚖️ **File Size Limit:** Up to **10 MB**\n"
            "☁️ **Storage Location:** Supabase Storage (`enterprise-documents/{org_id}/`)\n\n"
            "💡 *The document will be automatically chunked, embedded with Gemini, and indexed into pgvector.*"
        )
        await safe_reply(msg, prompt, parse_mode="Markdown")


async def handle_admin_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document file attachments uploaded by Admin."""
    if not update.effective_user or not update.effective_message or not update.effective_message.document:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if not user_sess.is_admin or not user_sess.organization_id:
            await safe_reply(msg, "⛔ Only organization administrators can upload documents. Log in via /admin first.")
            return

        doc = msg.document
        filename = doc.file_name or "uploaded_document.pdf"
        ext = Path(filename).suffix.lower()

        # Enforce allowed formats
        ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md"}
        if ext not in ALLOWED_EXTENSIONS:
            await safe_reply(
                msg,
                f"❌ **Unsupported File Format: `{ext or 'unknown'}`**\n\n"
                "Allowed document formats are:\n"
                "• 📄 **PDF** (`.pdf`)\n"
                "• 📝 **Plain Text** (`.txt`)\n"
                "• 📘 **Word Document** (`.docx`)\n"
                "• 📑 **Markdown** (`.md`)\n\n"
                "Please upload a document with an allowed extension.",
                parse_mode="Markdown"
            )
            return

        # Enforce file size limit (10 MB)
        MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
        if doc.file_size and doc.file_size > MAX_FILE_SIZE_BYTES:
            size_mb = round(doc.file_size / (1024 * 1024), 2)
            await safe_reply(
                msg,
                f"❌ **File Too Large: {size_mb} MB**\n\n"
                "The maximum allowed file size for knowledge documents is **10 MB**.\n"
                "Please reduce your file size and try again.",
                parse_mode="Markdown"
            )
            return

        status_msg = await safe_reply(msg, f"⏳ Ingesting `{filename}` into Supabase Storage & generating vector embeddings...", parse_mode="Markdown")

        try:
            tg_file = await context.bot.get_file(doc.file_id)
            file_bytes_stream = io.BytesIO()
            await tg_file.download_to_memory(file_bytes_stream)
            content_bytes = file_bytes_stream.getvalue()

            res = await document_service.upload_document(
                session=session,
                organization_id=user_sess.organization_id,
                filename=filename,
                content_bytes=content_bytes
            )

            await status_msg.edit_text(
                f"✅ **Document Uploaded & Ingested!**\n\n"
                f"📄 **File:** `{res['filename']}`\n"
                f"🆔 **Document ID:** `{res['document_id']}`\n"
                f"☁️ **Storage:** Supabase Storage (`{res['storage_path']}`)\n"
                f"📦 **Size:** `{round(res['file_size']/1024, 1)} KB`\n"
                f"🧩 **Indexed Chunks:** `{res['chunk_count']}`\n"
                f"🏢 **Organization:** `{user_sess.organization_id}`\n\n"
                f"Employees can now query information from this document in Telegram.\n"
                f"To delete this document later: `/delete_doc {res['document_id']}`",
                parse_mode="Markdown",
                reply_markup=get_documents_action_keyboard()
            )
        except Exception as e:
            logger.error("Failed to ingest document: %s", e)
            await status_msg.edit_text(f"❌ Failed to process document: {str(e)}")
