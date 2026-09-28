from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_employee_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🔒 Logout", callback_data="logout")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_employee_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard for one-tap employee authentication."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Sign In", callback_data="emp_confirm_login"),
            InlineKeyboardButton("❌ Cancel", callback_data="emp_cancel_login")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("➕ Add User", callback_data="admin_add_user"),
            InlineKeyboardButton("📁 Documents", callback_data="admin_documents"),
        ],
        [
            InlineKeyboardButton("📈 Usage Feed", callback_data="admin_usage"),
            InlineKeyboardButton("🔒 Logout", callback_data="logout")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_bot_admin_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🏢 Create Organization", callback_data="botadmin_create_org"),
            InlineKeyboardButton("📋 List Organizations", callback_data="botadmin_list_orgs"),
        ],
        [
            InlineKeyboardButton("🔒 Logout", callback_data="logout")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_answer_action_keyboard(has_sources: bool = False, query_id: str | None = None) -> InlineKeyboardMarkup:
    """Action keyboard below assistant answers with feedback and optional source viewer."""
    buttons = [
        [
            InlineKeyboardButton("👍 Helpful", callback_data="fb_up"),
            InlineKeyboardButton("👎 Not Helpful", callback_data="fb_down")
        ]
    ]
    if has_sources and query_id:
        buttons.append([
            InlineKeyboardButton("📄 View Sources", callback_data=f"src_{query_id}")
        ])
    return InlineKeyboardMarkup(buttons)

