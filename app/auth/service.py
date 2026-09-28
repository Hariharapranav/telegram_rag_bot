import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.auth.session import AuthState, UserSession
from app.auth.otp import otp_service
from app.db.repositories import (
    UserRepository,
    OrganizationRepository,
    TelegramSessionRepository
)
from app.db.models import TelegramSession

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    user_part, domain = email.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "***"
    else:
        masked_user = user_part[0] + "***" + user_part[-1]
    return f"{masked_user}@{domain}"


class AuthService:
    def __init__(self):
        self.otp_service = otp_service

    async def get_session(self, db: AsyncSession, telegram_user_id: int) -> UserSession:
        repo = TelegramSessionRepository(db)
        session_db = await repo.get_session(telegram_user_id)
        if not session_db:
            session_db = await repo.upsert_session(
                telegram_user_id=telegram_user_id,
                auth_state=AuthState.UNAUTHENTICATED.value,
                auth_context={}
            )

        try:
            state = AuthState(session_db.auth_state)
        except ValueError:
            state = AuthState.UNAUTHENTICATED

        return UserSession(
            telegram_user_id=session_db.telegram_user_id,
            user_id=session_db.user_id,
            organization_id=session_db.organization_id,
            role=session_db.role,
            auth_state=state,
            auth_context=session_db.auth_context or {}
        )

    async def start_employee_auth(self, db: AsyncSession, telegram_user_id: int) -> str:
        """Step 1: /start -> Initiate Employee Authentication by requesting Organization."""
        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_EMP_ORG.value,
            auth_context={}
        )
        return (
            "🏢 *Welcome to Enterprise Assistant*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "To access your company's documents, please enter your **Organization ID** or **Organization Name**:\n"
            "_(e.g. `acme_corp_001` or `Acme Corporation`)_"
        )

    async def process_employee_org(self, db: AsyncSession, telegram_user_id: int, org_input: str) -> str:
        """Step 2: Verify organization exists for employee."""
        clean_input = org_input.strip()
        org_repo = OrganizationRepository(db)
        org = await org_repo.get_by_id(clean_input)
        if not org:
            org = await org_repo.get_by_name(clean_input)

        if not org:
            return (
                f"❌ Organization `{clean_input}` was not found.\n"
                "Please verify your Organization ID or name and try again:"
            )

        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_EMP_ID.value,
            auth_context={"organization_id": org.id, "organization_name": org.name}
        )

        return (
            f"🏢 Organization: *{org.name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Please enter your **Employee ID** _(e.g. `EMP-001`)_:"
        )

    async def process_employee_id(self, db: AsyncSession, telegram_user_id: int, employee_id: str) -> Tuple[bool, str]:
        """Step 3: Lookup employee strictly within the verified organization, prepare one-tap sign in."""
        emp_id_clean = employee_id.strip()
        session = await self.get_session(db, telegram_user_id)
        org_id = session.auth_context.get("organization_id")
        org_name = session.auth_context.get("organization_name", "your organization")

        user_repo = UserRepository(db)
        user = None
        if org_id:
            user = await user_repo.get_by_employee_id(org_id, emp_id_clean)
            if not user:
                user = await user_repo.get_by_employee_id(org_id, emp_id_clean.upper())
        else:
            candidates = await user_repo.find_by_employee_id(emp_id_clean)
            user = candidates[0] if candidates else None

        if not user:
            return False, (
                f"❌ Employee ID `{emp_id_clean}` was not found in *{org_name}*.\n"
                "Please check the ID and try again, or contact your administrator."
            )

        repo = TelegramSessionRepository(db)
        ctx = session.auth_context
        ctx.update({
            "user_id": user.id,
            "organization_id": user.organization_id,
            "organization_name": org_name,
            "role": user.role,
            "employee_id": user.employee_id,
            "email": user.email,
            "name": user.name
        })
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_EMP_CONFIRM.value,
            auth_context=ctx
        )

        card = (
            f"👤 *Employee Profile Identified*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Name:** {user.name}\n"
            f"• **Employee ID:** `{user.employee_id}`\n"
            f"• **Organization:** {org_name}\n\n"
            f"Tap **Confirm & Sign In** below to authenticate:"
        )
        return True, card

    async def confirm_employee_login(self, db: AsyncSession, telegram_user_id: int) -> Tuple[bool, str]:
        """Step 4: Establish authenticated employee session upon one-tap confirmation."""
        session = await self.get_session(db, telegram_user_id)
        context = session.auth_context
        user_id = context.get("user_id")

        if not user_id:
            return False, "⚠️ Session expired. Please type /start to restart authentication."

        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            user_id=user_id,
            organization_id=context["organization_id"],
            role=context.get("role", "employee"),
            auth_state=AuthState.AUTHENTICATED.value,
            auth_context={}
        )

        org_name = context.get("organization_name")
        org_header = f"🏢 *{org_name} Knowledge Base*\n━━━━━━━━━━━━━━━━━━━━━━━\n" if org_name else ""
        emp_name = context.get("name", "Employee")
        return True, (
            f"{org_header}"
            f"👋 Welcome, **{emp_name}**!\n"
            f"Authentication successful ✅\n\n"
            "You can now ask questions about your organization's documents."
        )

    async def verify_employee_otp(self, db: AsyncSession, telegram_user_id: int, otp_input: str) -> Tuple[bool, str]:
        """Step 4: Verify OTP and establish authenticated session."""
        session = await self.get_session(db, telegram_user_id)
        context = session.auth_context
        user_id = context.get("user_id")

        if not user_id:
            return False, "⚠️ Session expired. Please type /start to restart authentication."

        otp_key = f"emp:{user_id}"
        is_valid = await self.otp_service.verify_otp(otp_key, otp_input.strip())

        if not is_valid:
            return False, "❌ Invalid or expired OTP code. Please enter the correct 6-digit code or type /start to request a new one."

        # Establish authenticated session
        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            user_id=user_id,
            organization_id=context["organization_id"],
            role=context.get("role", "employee"),
            auth_state=AuthState.AUTHENTICATED.value,
            auth_context={}
        )

        org_name = context.get("organization_name")
        org_header = f"🏢 *{org_name} Knowledge Base*\n━━━━━━━━━━━━━━━━━━━━━━━\n" if org_name else ""
        return True, (
            f"{org_header}"
            "Authentication successful ✅\n\n"
            "You can now ask questions about your organization's documents."
        )

    async def start_admin_auth(self, db: AsyncSession, telegram_user_id: int) -> str:
        """Step 1 & 2: /admin -> Request organization identifier."""
        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_ADMIN_ORG.value,
            auth_context={}
        )
        return (
            "🛡️ **Admin Portal Authentication**\n\n"
            "Please enter your **Organization ID** or **Organization Name** "
            "(e.g. `acme_corp_001` or `Acme Corp`):"
        )

    async def process_admin_org(self, db: AsyncSession, telegram_user_id: int, org_input: str) -> str:
        """Step 3: Verify organization exists."""
        clean_input = org_input.strip()
        org_repo = OrganizationRepository(db)
        org = await org_repo.get_by_id(clean_input)
        if not org:
            org = await org_repo.get_by_name(clean_input)

        if not org:
            return (
                f"❌ Organization `{clean_input}` was not found.\n"
                "Please verify your organization ID or name and try again:"
            )

        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_ADMIN_CREDENTIAL.value,
            auth_context={"organization_id": org.id, "organization_name": org.name}
        )

        return (
            f"🏢 Organization verified: `{org.name}`\n\n"
            "Please enter your **Admin Email** or **Employee ID**:"
        )

    async def process_admin_credential(self, db: AsyncSession, telegram_user_id: int, cred_input: str) -> str:
        """Step 4: Verify user exists, has admin role in this organization, send OTP."""
        session = await self.get_session(db, telegram_user_id)
        org_id = session.auth_context.get("organization_id")
        if not org_id:
            return "⚠️ Session lost. Please type /admin to restart."

        cred = cred_input.strip().lower()
        user_repo = UserRepository(db)

        # Lookup by email or employee ID
        user = await user_repo.get_by_email(cred, org_id)
        if not user:
            user = await user_repo.get_by_employee_id(org_id, cred.upper())

        if not user or user.role != "admin":
            return (
                "❌ Access Denied: We could not find an Administrator account matching "
                f"`{cred_input}` in this organization.\n"
                "Only authorized administrators can access this portal."
            )

        # Generate OTP
        otp_key = f"admin:{user.id}"
        otp_code = await self.otp_service.generate_otp(otp_key)

        repo = TelegramSessionRepository(db)
        ctx = session.auth_context
        ctx.update({
            "user_id": user.id,
            "role": "admin",
            "name": user.name,
            "email": user.email,
            "employee_id": user.employee_id
        })
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            auth_state=AuthState.AWAITING_ADMIN_OTP.value,
            auth_context=ctx
        )

        masked = mask_email(user.email)
        mock_hint = f"\n\n🔐 [Demo Verification Channel: OTP is `{otp_code}`]" if settings.MOCK_OTP_MODE else ""

        return (
            f"👤 Admin identified: `{user.name}`\n"
            f"A one-time verification code has been dispatched to `{masked}`.\n\n"
            f"Please enter the 6-digit OTP code to unlock Admin Commands:{mock_hint}"
        )

    async def verify_admin_otp(self, db: AsyncSession, telegram_user_id: int, otp_input: str) -> Tuple[bool, str]:
        """Step 5 & 6: Verify Admin OTP and grant admin session."""
        session = await self.get_session(db, telegram_user_id)
        ctx = session.auth_context
        user_id = ctx.get("user_id")
        org_id = ctx.get("organization_id")

        if not user_id or not org_id:
            return False, "⚠️ Session expired. Please type /admin to restart."

        otp_key = f"admin:{user_id}"
        is_valid = await self.otp_service.verify_otp(otp_key, otp_input.strip())

        if not is_valid:
            return False, "❌ Invalid or expired Admin OTP code. Please enter the correct code:"

        repo = TelegramSessionRepository(db)
        await repo.upsert_session(
            telegram_user_id=telegram_user_id,
            user_id=user_id,
            organization_id=org_id,
            role="admin",
            auth_state=AuthState.AUTHENTICATED.value,
            auth_context={}
        )

        return True, (
            "Admin authentication successful! 🛡️✅\n\n"
            "You have unlocked executive admin controls:\n"
            "• `/admin/stats` - Organization-wide AI & latency analytics\n"
            "• `/admin/users` - User-level query & cost breakdown\n"
            "• `/admin/usage` - Recent query logs & trends\n"
            "• `/admin/documents` - Ingested documents list & upload"
        )

    async def logout(self, db: AsyncSession, telegram_user_id: int) -> str:
        """Log out the current Telegram user session."""
        repo = TelegramSessionRepository(db)
        await repo.delete_session(telegram_user_id)
        return (
            "🔒 You have been securely logged out.\n\n"
            "Use /start to log in as an employee or /admin to log in as an administrator."
        )


auth_service = AuthService()
