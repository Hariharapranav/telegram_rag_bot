from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class AuthState(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AWAITING_EMP_ORG = "AWAITING_EMP_ORG"
    AWAITING_EMP_ID = "AWAITING_EMP_ID"
    AWAITING_EMP_CONFIRM = "AWAITING_EMP_CONFIRM"
    AWAITING_EMP_OTP = "AWAITING_EMP_OTP"
    AWAITING_ADMIN_ORG = "AWAITING_ADMIN_ORG"
    AWAITING_ADMIN_CREDENTIAL = "AWAITING_ADMIN_CREDENTIAL"
    AWAITING_ADMIN_CONFIRM = "AWAITING_ADMIN_CONFIRM"
    AWAITING_ADMIN_OTP = "AWAITING_ADMIN_OTP"
    AWAITING_BOT_ADMIN_SECRET = "AWAITING_BOT_ADMIN_SECRET"
    AWAITING_CREATE_ORG_DATA = "AWAITING_CREATE_ORG_DATA"
    AWAITING_ADD_USER_DATA = "AWAITING_ADD_USER_DATA"
    AUTHENTICATED = "AUTHENTICATED"


@dataclass
class UserSession:
    telegram_user_id: int
    user_id: Optional[str]
    organization_id: Optional[str]
    role: Optional[str]  # "employee" | "admin" | "bot_admin"
    auth_state: AuthState
    auth_context: Dict[str, Any]

    @property
    def is_authenticated(self) -> bool:
        if self.auth_state != AuthState.AUTHENTICATED:
            return False
        # Bot admin doesn't need to be tied to a single organization
        if self.role == "bot_admin":
            return True
        return bool(self.organization_id)

    @property
    def is_admin(self) -> bool:
        return self.is_authenticated and self.role in ("admin", "bot_admin")

    @property
    def is_bot_admin(self) -> bool:
        return self.is_authenticated and self.role == "bot_admin"
