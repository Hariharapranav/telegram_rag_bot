import logging
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories import QueryLogRepository, DocumentRepository, OrganizationRepository

logger = logging.getLogger(__name__)


class AdminAnalyticsService:
    @staticmethod
    async def get_stats_summary(session: AsyncSession, organization_id: str) -> str:
        """Format /admin/stats output for Telegram display."""
        repo = QueryLogRepository(session)
        stats = await repo.get_org_stats(organization_id)

        msg = (
            f"📊 **Executive AI Analytics: {stats['organization_name']}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **Total Users:** `{stats['total_users']}`\n"
            f"💬 **Total Queries:** `{stats['total_queries']}`\n"
            f"⚡ **Cache Hits:** `{stats['cache_hits']}`\n"
            f"🎯 **Cache Hit Rate:** `{stats['cache_hit_rate']}%`\n"
            f"🧠 **Gemini API Calls:** `{stats['gemini_calls']}`\n"
            f"📥 **Input Tokens:** `{stats['total_input_tokens']:,}`\n"
            f"📤 **Output Tokens:** `{stats['total_output_tokens']:,}`\n"
            f"💰 **Estimated Gemini Cost:** `${stats['estimated_gemini_cost']:.6f}`\n"
            f"⏱️ **Average Latency:** `{stats['average_latency_ms']} ms`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Tip: Higher semantic cache hit rates directly reduce latency and operational cost.*"
        )
        return msg

    @staticmethod
    async def get_users_summary(session: AsyncSession, organization_id: str) -> str:
        """Format /admin/users output for Telegram display."""
        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_id(organization_id)
        org_display = f"{org.name} (`{organization_id}`)" if org else f"`{organization_id}`"

        repo = QueryLogRepository(session)
        users = await repo.get_user_stats(organization_id)

        if not users:
            return f"ℹ️ No user activity has been recorded yet for {org_display}."

        lines = [
            "👥 **User-wise AI Usage Breakdown**\n"
            f"🏢 **Organization:** {org_display}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for u in users:
            lines.append(
                f"👤 **{u['name']}** (`{u['employee_id']}`)\n"
                f"   • Queries: `{u['total_queries']}` (⚡ Hits: `{u['cache_hits']}` | 🧠 LLM: `{u['gemini_calls']}`)\n"
                f"   • Tokens: `{u['tokens_used']:,}` | Cost: `${u['estimated_cost']:.5f}`\n"
                f"   • Avg Latency: `{u['avg_latency']} ms`"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n\n".join(lines)

    @staticmethod
    async def get_usage_feed(session: AsyncSession, organization_id: str) -> str:
        """Format /admin/usage output for Telegram display."""
        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_id(organization_id)
        org_display = f"{org.name} (`{organization_id}`)" if org else f"`{organization_id}`"

        repo = QueryLogRepository(session)
        logs = await repo.get_usage_summary(organization_id, limit=10)

        if not logs:
            return f"ℹ️ No recent query logs found for {org_display}."

        lines = [
            "📈 **Recent Query Activity Stream**\n"
            f"🏢 **Organization:** {org_display}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for log in logs:
            status_icon = "⚡ CACHED" if log["cache_hit"] else f"🧠 {log['model_used']}"
            q_snippet = (log["question"][:45] + "...") if len(log["question"]) > 45 else log["question"]
            lines.append(
                f"🕒 `{log['created_at']}` | {status_icon}\n"
                f"👤 `{log['employee_id']}` ({log['user_name']})\n"
                f"❓ *\"{q_snippet}\"*\n"
                f"⚙️ `{log['tokens']} toks` | `${log['cost']:.5f}` | `{log['latency_ms']}ms`\n"
                f"──────────────────────"
            )

        return "\n".join(lines)

    @staticmethod
    async def get_documents_summary(session: AsyncSession, organization_id: str) -> str:
        """Format /admin/documents output for Telegram display."""
        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_id(organization_id)
        org_display = f"{org.name} (`{organization_id}`)" if org else f"`{organization_id}`"

        repo = DocumentRepository(session)
        docs = await repo.list_by_org(organization_id)

        if not docs:
            return (
                "📁 **Organization Knowledge Base**\n"
                f"🏢 **Organization:** {org_display}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "No documents uploaded for this organization yet.\n\n"
                "📤 **To upload:** Simply attach or drag & drop a file (.pdf, .txt, .docx, .md) into this chat!"
            )

        lines = [
            "📁 **Organization Knowledge Base**\n"
            f"🏢 **Organization:** {org_display}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for doc in docs:
            size_kb = round(doc.file_size / 1024, 1)
            lines.append(
                f"📄 **{doc.filename}**\n"
                f"   • ID: `{doc.id}`\n"
                f"   • Chunks: `{doc.chunk_count}` | Size: `{size_kb} KB`\n"
                f"   • Uploaded: `{doc.uploaded_at.strftime('%Y-%m-%d %H:%M')}`\n"
                f"   • Delete: `/delete_doc {doc.id}`"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            "💡 *Management:*\n"
            "• Delete a document: `/delete_doc <id>`\n"
            "• Add a new document: Drag & drop PDF/TXT file here\n"
            "• Add a user: `/add_user`"
        )
        return "\n\n".join(lines)


admin_analytics = AdminAnalyticsService()
