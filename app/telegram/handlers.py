import uuid
import logging
import time
from typing import Optional, List, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.repositories import TelegramSessionRepository, OrganizationRepository
from app.auth.service import auth_service
from app.auth.session import AuthState
from app.cache.semantic_cache import semantic_cache
from app.router.model_router import model_router
from app.rag.embeddings import embedding_service
from app.rag.retrieval import rag_retriever
from app.rag.generation import grounded_generator, NOT_FOUND_MESSAGE
from app.services.usage_tracker import usage_tracker
from app.telegram.keyboards import (
    get_employee_menu_keyboard,
    get_employee_confirm_keyboard,
    get_admin_confirm_keyboard,
    get_admin_menu_keyboard,
    get_bot_admin_menu_keyboard,
    get_answer_action_keyboard,
    get_documents_action_keyboard
)

# In-memory store for recent query sources (query_id -> list of source filenames)
_query_sources_cache: Dict[str, List[str]] = {}
from app.admin.handlers import (
    process_create_org_input,
    process_add_user_input,
    handle_create_org,
    handle_list_orgs,
    handle_add_user,
    handle_admin_upload_prompt
)

logger = logging.getLogger(__name__)


async def safe_reply(msg, text: str, parse_mode: Optional[str] = "Markdown", reply_markup=None):
    """Safely send reply, falling back to plain text if Markdown entity parsing fails."""
    try:
        return await msg.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("Markdown reply failed (%s). Retrying as plain text.", e)
        try:
            return await msg.reply_text(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as exc:
            logger.error("Failed to send message: %s", exc)
            return None


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        if user_sess.is_authenticated:
            if user_sess.is_bot_admin:
                role_badge = "Super Bot Admin 👑"
                kb = get_bot_admin_menu_keyboard()
            elif user_sess.is_admin:
                role_badge = "Administrator 🛡️"
                kb = get_admin_menu_keyboard()
            else:
                role_badge = "Employee 👤"
                kb = get_employee_menu_keyboard()

            org_repo = OrganizationRepository(session)
            org = await org_repo.get_by_id(user_sess.organization_id) if user_sess.organization_id else None
            org_display = f" • *{org.name}*" if org else ""

            welcome_card = (
                f"🏢 *Enterprise Assistant Portal*{org_display}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👋 Welcome back! Authenticated as **{role_badge}**.\n\n"
                f"💬 Send any question about company policies, benefits, or documentation to get instant answers."
            )

            await safe_reply(
                msg,
                welcome_card,
                parse_mode="Markdown",
                reply_markup=kb
            )
            return

        reply = await auth_service.start_employee_auth(session, tg_user_id)
        await safe_reply(msg, reply, parse_mode="Markdown")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not update.effective_message:
        return

    msg = update.effective_message
    help_text = (
        "🤖 **Enterprise AI Telegram Assistant — Help Guide**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👑 **Platform Bot Admin:**\n"
        "• `/botadmin` - Super Admin Portal (Create orgs & manage platform)\n"
        "• `/create_org` - Register new organization & initial admin\n"
        "• `/list_orgs` - View all tenant organizations & user counts\n\n"
        "🛡️ **Organization Admin Commands:**\n"
        "• `/admin` - Access Organization Admin controls\n"
        "• `/add_user` - Register a new employee or admin into your organization\n"
        "• `/delete_doc <id>` - Remove an uploaded document from knowledge base\n"
        "• `/admin/stats` - Total queries, cache hits, cost & latency metrics\n"
        "• `/admin/users` - User-by-user AI usage breakdown\n"
        "• `/admin/usage` - Real-time query activity stream\n"
        "• `/admin/documents` - Ingested documents catalog & upload\n\n"
        "👤 **Employee Authentication & Queries:**\n"
        "• `/start` - Authenticate via Employee ID + OTP\n"
        "• `/logout` - Securely log out and invalidate your session\n"
        "• Simply ask natural questions about company policies, benefits, and procedures!\n\n"
        "🔒 **Enterprise Multi-Tenancy Guarantee:**\n"
        "Every organization's data, embeddings, and semantic cache are strictly partitioned. "
        "No data leaks across tenants."
    )
    await safe_reply(msg, help_text, parse_mode="Markdown")


async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /logout command."""
    if not update.effective_user or not update.effective_message:
        return

    msg = update.effective_message
    tg_user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        reply = await auth_service.logout(session, tg_user_id)
        await safe_reply(msg, reply, parse_mode="Markdown")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main message dispatcher:
    - If in auth/input workflow: handles OTP, Credential, Org creation, or User creation.
    - If authenticated employee: runs RAG pipeline with Semantic Cache & Model Router.
    """
    if not update.effective_user or not update.effective_message or not update.effective_message.text:
        return

    msg = update.effective_message
    text = msg.text.strip()
    tg_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)
        state = user_sess.auth_state

        # ========================================================
        # 1. SUPER BOT ADMIN AUTH & WORKFLOW
        # ========================================================
        if state == AuthState.AWAITING_BOT_ADMIN_SECRET:
            expected_secret = settings.BOT_ADMIN_SECRET.strip()
            if text == expected_secret:
                repo = TelegramSessionRepository(session)
                await repo.upsert_session(
                    telegram_user_id=tg_user_id,
                    role="bot_admin",
                    auth_state=AuthState.AUTHENTICATED.value,
                    auth_context={}
                )
                reply_msg = (
                    "👑 **Super Bot Admin Authentication Successful!**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "You have platform-level management privileges:\n\n"
                    "• `/create_org` - Register a new enterprise organization & initial admin\n"
                    "• `/list_orgs` - View all organizations & tenant stats\n"
                    "• `/logout` - Log out of super admin session"
                )
                await safe_reply(
                    msg,
                    reply_msg,
                    parse_mode="Markdown",
                    reply_markup=get_bot_admin_menu_keyboard()
                )
            else:
                await safe_reply(msg, "❌ Invalid secret key. Access denied. Try /botadmin again.")
            return

        elif state == AuthState.AWAITING_CREATE_ORG_DATA:
            reply = await process_create_org_input(session, text)
            # Reset state back to authenticated bot_admin
            repo = TelegramSessionRepository(session)
            await repo.upsert_session(
                telegram_user_id=tg_user_id,
                role="bot_admin",
                auth_state=AuthState.AUTHENTICATED.value,
                auth_context={}
            )
            await safe_reply(
                msg,
                reply,
                parse_mode="Markdown",
                reply_markup=get_bot_admin_menu_keyboard()
            )
            return

        # ========================================================
        # 2. ORG ADMIN WORKFLOW (ADD USER)
        # ========================================================
        elif state == AuthState.AWAITING_ADD_USER_DATA:
            org_id = user_sess.auth_context.get("organization_id") or user_sess.organization_id
            if not org_id:
                await safe_reply(msg, "⚠️ Session expired. Please type /admin to log in again.")
                return

            reply = await process_add_user_input(session, org_id, text)
            repo = TelegramSessionRepository(session)
            await repo.upsert_session(
                telegram_user_id=tg_user_id,
                role="admin",
                organization_id=org_id,
                auth_state=AuthState.AUTHENTICATED.value,
                auth_context={}
            )
            await safe_reply(
                msg,
                reply,
                parse_mode="Markdown",
                reply_markup=get_admin_menu_keyboard()
            )
            return

        # ========================================================
        # 3. STANDARD AUTH WORKFLOW (EMPLOYEE & ADMIN LOGIN)
        # ========================================================
        elif state == AuthState.AWAITING_EMP_ORG:
            reply = await auth_service.process_employee_org(session, tg_user_id, text)
            await safe_reply(msg, reply, parse_mode="Markdown")
            return

        elif state == AuthState.AWAITING_EMP_ID:
            found, reply = await auth_service.process_employee_id(session, tg_user_id, text)
            kb = get_employee_confirm_keyboard() if found else None
            await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            return

        elif state == AuthState.AWAITING_EMP_CONFIRM:
            if text.strip().lower() in ("yes", "y", "confirm", "ok", "login"):
                success, reply = await auth_service.confirm_employee_login(session, tg_user_id)
                kb = get_employee_menu_keyboard() if success else None
                await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            else:
                kb = get_employee_confirm_keyboard()
                await safe_reply(msg, "Please tap **✅ Confirm & Sign In** below to authenticate:", parse_mode="Markdown", reply_markup=kb)
            return

        elif state == AuthState.AWAITING_EMP_OTP:
            success, reply = await auth_service.verify_employee_otp(session, tg_user_id, text)
            kb = get_employee_menu_keyboard() if success else None
            await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            return

        elif state == AuthState.AWAITING_ADMIN_ORG:
            reply = await auth_service.process_admin_org(session, tg_user_id, text)
            await safe_reply(msg, reply, parse_mode="Markdown")
            return

        elif state == AuthState.AWAITING_ADMIN_CREDENTIAL:
            found, reply = await auth_service.process_admin_credential(session, tg_user_id, text)
            kb = get_admin_confirm_keyboard() if found else None
            await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            return

        elif state == AuthState.AWAITING_ADMIN_CONFIRM:
            if text.strip().lower() in ("yes", "y", "confirm", "ok", "login"):
                success, reply = await auth_service.confirm_admin_login(session, tg_user_id)
                kb = get_admin_menu_keyboard() if success else None
                await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            else:
                kb = get_admin_confirm_keyboard()
                await safe_reply(msg, "Please tap **✅ Confirm & Sign In** below to authenticate as Administrator:", parse_mode="Markdown", reply_markup=kb)
            return

        elif state == AuthState.AWAITING_ADMIN_OTP:
            success, reply = await auth_service.verify_admin_otp(session, tg_user_id, text)
            kb = get_admin_menu_keyboard() if success else None
            await safe_reply(msg, reply, parse_mode="Markdown", reply_markup=kb)
            return

        elif not user_sess.is_authenticated:
            await safe_reply(
                msg,
                "🔒 You are not currently authenticated.\n\n"
                "• Type `/start` to log in with your Employee ID\n"
                "• Type `/admin` for Organization Administrator access\n"
                "• Type `/botadmin` for Super Bot Admin access",
                parse_mode="Markdown"
            )
            return

        # Bot Admin message handling
        if user_sess.is_bot_admin:
            await safe_reply(
                msg,
                "👑 **Super Bot Admin Session Active**\n\n"
                "Available commands:\n"
                "• `/create_org` - Register new organization & admin\n"
                "• `/list_orgs` - View all registered tenant organizations\n"
                "• `/logout` - Log out",
                parse_mode="Markdown",
                reply_markup=get_bot_admin_menu_keyboard()
            )
            return

        # ========================================================
        # 4. AUTHENTICATED RAG QUERY PIPELINE
        # ========================================================
        start_time = time.perf_counter()
        org_id = user_sess.organization_id
        user_id = user_sess.user_id

        # Send typing indicator
        if update.effective_chat:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        # Step A: Generate query embedding
        query_embedding = await embedding_service.get_embedding(text)

        # Step B: Semantic Cache Lookup (Redis)
        cache_result = await semantic_cache.lookup(org_id, query_embedding)

        if cache_result.get("cache_hit"):
            # Cache HIT!
            cached_answer = cache_result["answer"]
            sim = cache_result["similarity"]
            model_tag = cache_result.get("model_used", "cached")
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Log metrics (0 tokens, $0.00 cost)
            await usage_tracker.log_query(
                session=session,
                organization_id=org_id,
                user_id=user_id,
                question=text,
                model_used=f"{model_tag} (cache)",
                cache_hit=True,
                input_tokens=0,
                output_tokens=0,
                estimated_cost=0.0,
                latency_ms=round(latency_ms, 2)
            )

            org_repo = OrganizationRepository(session)
            org = await org_repo.get_by_id(org_id) if org_id else None
            org_name = org.name if org else "Enterprise"

            card_lines = [
                f"🏢 *{org_name} Knowledge Base*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                cached_answer,
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "_⚡ Instant Response • Verified from official documents_"
            ]
            if settings.SHOW_DEBUG_BADGES:
                card_lines.append(f"\n⚡ *[Cached Response | Similarity: {sim:.2f} | 0 tokens | {latency_ms:.0f}ms]*")

            response_msg = "\n".join(card_lines)
            kb = get_answer_action_keyboard(has_sources=False)
            await safe_reply(msg, response_msg, parse_mode="Markdown", reply_markup=kb)
            return

        # Step C: Cache MISS -> Query Complexity Router
        routing = model_router.analyze(text)
        selected_model = routing.selected_model
        model_tier = routing.model_tier
        complexity_score = routing.complexity_score

        # Step D: Vector Search in pgvector (multi-tenant filtered by org_id)
        retrieved_chunks, _ = await rag_retriever.retrieve(
            session=session,
            organization_id=org_id,
            query=text,
            query_embedding=query_embedding
        )

        # Step E: Grounded Answer Generation with Gemini
        gen_result = await grounded_generator.generate_answer(
            question=text,
            retrieved_chunks=retrieved_chunks,
            model_name=selected_model
        )

        answer = gen_result["answer"]
        in_tokens = gen_result["input_tokens"]
        out_tokens = gen_result["output_tokens"]
        cost = gen_result["estimated_cost"]
        citations = gen_result["citations"]

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Step F: Store in Semantic Cache
        if answer != NOT_FOUND_MESSAGE:
            await semantic_cache.store(
                organization_id=org_id,
                question=text,
                answer=answer,
                question_embedding=query_embedding,
                model_used=selected_model
            )

        # Step G: Log Query Telemetry
        total_latency_ms = latency_ms
        await usage_tracker.log_query(
            session=session,
            organization_id=org_id,
            user_id=user_id,
            question=text,
            model_used=selected_model,
            cache_hit=False,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            estimated_cost=cost,
            latency_ms=round(total_latency_ms, 2)
        )

        # Step H: Format & Return Response (Modern Executive Card)
        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_id(org_id) if org_id else None
        org_name = org.name if org else "Enterprise"

        if answer == NOT_FOUND_MESSAGE:
            card_lines = [
                "🔍 *Information Not Found*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                f"I couldn't locate this information in *{org_name}*'s official documents.",
                "",
                "💡 *Helpful Suggestions:*",
                "• Try using different keywords or broader terms",
                "• Ensure the relevant document is uploaded to the system",
                "• Contact your organization administrator for guidance",
                "━━━━━━━━━━━━━━━━━━━━━━━"
            ]
            kb = get_answer_action_keyboard(has_sources=False)
        else:
            card_lines = [
                f"🏢 *{org_name} Knowledge Base*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                answer,
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "_✨ Verified from official company documents_"
            ]
            qid = None
            source_names = list(dict.fromkeys(c["source"] for c in citations if c.get("source"))) if citations else []
            if source_names:
                qid = uuid.uuid4().hex[:8]
                _query_sources_cache[qid] = source_names
                if len(_query_sources_cache) > 500:
                    del _query_sources_cache[next(iter(_query_sources_cache))]
            kb = get_answer_action_keyboard(has_sources=bool(source_names), query_id=qid)

        if settings.SHOW_DEBUG_BADGES:
            badge = (
                f"🧠 *[{selected_model} ({model_tier.upper()}) | "
                f"Score: {complexity_score:.2f} | "
                f"Toks: {in_tokens+out_tokens} | "
                f"${cost:.5f} | "
                f"{total_latency_ms:.0f}ms]*"
            )
            card_lines.append(f"\n{badge}")

        formatted_reply = "\n".join(card_lines)
        await safe_reply(msg, formatted_reply, parse_mode="Markdown", reply_markup=kb)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline buttons."""
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    data = query.data
    tg_user_id = update.effective_user.id

    # Interactive Feedback & Source View handling
    if data == "fb_up":
        await query.answer("Thank you for your feedback! 👍", show_alert=False)
        return
    elif data == "fb_down":
        await query.answer("Thank you for the feedback. We'll work to improve! 👎", show_alert=False)
        return
    elif data.startswith("src_"):
        qid = data[4:]
        sources = _query_sources_cache.get(qid, [])
        if sources:
            src_list = "\n".join(f"• {s}" for s in sources)
            modal_text = f"📚 Verified Document Sources:\n\n{src_list}"
            if len(modal_text) > 195:
                modal_text = modal_text[:192] + "..."
            await query.answer(modal_text, show_alert=True)
        else:
            await query.answer("Source documents are no longer in active cache.", show_alert=True)
    elif data == "emp_confirm_login":
        async with AsyncSessionLocal() as session:
            success, reply = await auth_service.confirm_employee_login(session, tg_user_id)
            kb = get_employee_menu_keyboard() if success else None
            await query.edit_message_text(reply, parse_mode="Markdown")
            if success:
                await safe_reply(query.message, "💡 You are now ready to chat! Ask any question about your organization's documents.", reply_markup=kb)
        return
    elif data == "emp_cancel_login":
        async with AsyncSessionLocal() as session:
            repo = TelegramSessionRepository(session)
            await repo.upsert_session(
                telegram_user_id=tg_user_id,
                auth_state=AuthState.UNAUTHENTICATED.value,
                auth_context={}
            )
            await query.edit_message_text("Authentication cancelled. Type `/start` to begin again.", parse_mode="Markdown")
        return
    elif data == "admin_confirm_login":
        async with AsyncSessionLocal() as session:
            success, reply = await auth_service.confirm_admin_login(session, tg_user_id)
            kb = get_admin_menu_keyboard() if success else None
            await query.edit_message_text(reply, parse_mode="Markdown")
            if success:
                await safe_reply(query.message, "🛡️ Admin session unlocked. Use the menu buttons below to manage your organization:", reply_markup=kb)
        return
    elif data == "admin_cancel_login":
        async with AsyncSessionLocal() as session:
            repo = TelegramSessionRepository(session)
            await repo.upsert_session(
                telegram_user_id=tg_user_id,
                auth_state=AuthState.UNAUTHENTICATED.value,
                auth_context={}
            )
            await query.edit_message_text("Admin authentication cancelled. Type `/admin` to begin again.", parse_mode="Markdown")
        return

    await query.answer()

    async with AsyncSessionLocal() as session:
        user_sess = await auth_service.get_session(session, tg_user_id)

        if data == "logout":
            reply = await auth_service.logout(session, tg_user_id)
            await query.edit_message_text(reply, parse_mode="Markdown")
        elif data == "help":
            await handle_help(update, context)
        elif data == "admin_stats":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            from app.admin.analytics import admin_analytics
            report = await admin_analytics.get_stats_summary(session, user_sess.organization_id)
            await safe_reply(query.message, report, parse_mode="Markdown")
        elif data == "admin_users":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            from app.admin.analytics import admin_analytics
            report = await admin_analytics.get_users_summary(session, user_sess.organization_id)
            await safe_reply(query.message, report, parse_mode="Markdown")
        elif data == "admin_usage":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            from app.admin.analytics import admin_analytics
            report = await admin_analytics.get_usage_feed(session, user_sess.organization_id)
            await safe_reply(query.message, report, parse_mode="Markdown")
        elif data == "admin_documents":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            from app.admin.analytics import admin_analytics
            report = await admin_analytics.get_documents_summary(session, user_sess.organization_id)
            await safe_reply(query.message, report, parse_mode="Markdown", reply_markup=get_documents_action_keyboard())
        elif data == "admin_upload_doc":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            await handle_admin_upload_prompt(update, context)
        elif data == "admin_add_user":
            if not user_sess.is_admin or not user_sess.organization_id:
                await safe_reply(query.message, "⛔ Admin credentials required.")
                return
            await handle_add_user(update, context)
        elif data == "botadmin_create_org":
            if not user_sess.is_bot_admin:
                await safe_reply(query.message, "⛔ Super Bot Admin credentials required.")
                return
            await handle_create_org(update, context)
        elif data == "botadmin_list_orgs":
            if not user_sess.is_bot_admin:
                await safe_reply(query.message, "⛔ Super Bot Admin credentials required.")
                return
            await handle_list_orgs(update, context)
