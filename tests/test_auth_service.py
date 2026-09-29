import pytest
from app.auth.service import AuthService
from app.auth.session import AuthState
from app.db.repositories import OrganizationRepository, UserRepository, TelegramSessionRepository


@pytest.mark.asyncio
async def test_employee_authentication_flow(db_session):
    auth_srv = AuthService()
    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)

    # 1. Setup sample org and user
    org = await org_repo.create("Test Corp", org_id="org_test_1")
    user = await user_repo.create(
        organization_id="org_test_1",
        employee_id="EMP-100",
        name="John Doe",
        email="john@testcorp.com",
        role="employee"
    )

    tg_id = 999111

    # 2. Step 1: /start
    welcome_msg = await auth_srv.start_employee_auth(db_session, tg_id)
    assert "Organization" in welcome_msg
    sess = await auth_srv.get_session(db_session, tg_id)
    assert sess.auth_state == AuthState.AWAITING_EMP_ORG

    # 2b. Step 2: Enter Organization ID
    org_reply = await auth_srv.process_employee_org(db_session, tg_id, "org_test_1")
    assert "Test Corp" in org_reply
    assert "Employee ID" in org_reply
    sess = await auth_srv.get_session(db_session, tg_id)
    assert sess.auth_state == AuthState.AWAITING_EMP_ID

    # 3. Step 3: Enter employee ID
    found, reply = await auth_srv.process_employee_id(db_session, tg_id, "EMP-100")
    assert found is True
    assert "John Doe" in reply
    assert "EMP-100" in reply
    sess = await auth_srv.get_session(db_session, tg_id)
    assert sess.auth_state == AuthState.AWAITING_EMP_CONFIRM

    # 4. Step 4: One-Tap Confirm & Sign In
    success, ok_reply = await auth_srv.confirm_employee_login(db_session, tg_id)
    assert success is True
    assert "Authentication successful ✅" in ok_reply
    assert "John Doe" in ok_reply

    # 6. Verify session state is authenticated
    final_sess = await auth_srv.get_session(db_session, tg_id)
    assert final_sess.is_authenticated is True
    assert final_sess.organization_id == "org_test_1"
    assert final_sess.role == "employee"


@pytest.mark.asyncio
async def test_admin_authentication_flow(db_session):
    auth_srv = AuthService()
    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)

    org = await org_repo.create("Admin Corp", org_id="org_admin_1")
    admin_user = await user_repo.create(
        organization_id="org_admin_1",
        employee_id="ADM-001",
        name="Sarah Connor",
        email="sarah@admincorp.com",
        role="admin"
    )

    tg_id = 888222

    # Step 1: /admin
    msg1 = await auth_srv.start_admin_auth(db_session, tg_id)
    assert "Organization ID" in msg1

    # Step 2: Enter Org ID
    msg2 = await auth_srv.process_admin_org(db_session, tg_id, "org_admin_1")
    assert "Admin Corp" in msg2

    # Step 3: Enter Admin Email -> Admin Profile Card with Role
    found, card = await auth_srv.process_admin_credential(db_session, tg_id, "sarah@admincorp.com")
    assert found is True
    assert "Sarah Connor" in card
    assert "Administrator" in card
    sess = await auth_srv.get_session(db_session, tg_id)
    assert sess.auth_state == AuthState.AWAITING_ADMIN_CONFIRM

    # Step 4: One-Tap Confirm & Sign In as Admin
    success, ok_msg = await auth_srv.confirm_admin_login(db_session, tg_id)
    assert success is True
    assert "Admin Portal Authenticated" in ok_msg
    assert "Sarah Connor" in ok_msg

    final_sess = await auth_srv.get_session(db_session, tg_id)
    assert final_sess.is_admin is True
    assert final_sess.is_authenticated is True


@pytest.mark.asyncio
async def test_admin_case_insensitive_emp_id_login(db_session):
    auth_srv = AuthService()
    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)

    org = await org_repo.create("Slidio Inc", org_id="slidio_org")
    admin_user = await user_repo.create(
        organization_id="slidio_org",
        employee_id="Sli-001",
        name="Pranav",
        email="pranav@gmail.com",
        role="admin"
    )

    tg_id = 777123

    # Step 1: /admin
    await auth_srv.start_admin_auth(db_session, tg_id)

    # Step 2: Org name in mixed case
    org_reply = await auth_srv.process_admin_org(db_session, tg_id, "slidio inc")
    assert "Slidio Inc" in org_reply

    # Step 3: Enter Employee ID with different casing (e.g. sli-001 or Sli-001 or SLI-001)
    found, card = await auth_srv.process_admin_credential(db_session, tg_id, "Sli-001")
    assert found is True
    assert "Pranav" in card
    assert "Administrator" in card
    assert "Sli-001" in card

    # Step 4: Confirm login
    success, ok_msg = await auth_srv.confirm_admin_login(db_session, tg_id)
    assert success is True
    assert "Admin Portal Authenticated" in ok_msg

    # Verify session is authenticated as admin without email OTP
    sess = await auth_srv.get_session(db_session, tg_id)
    assert sess.is_admin is True
    assert sess.is_authenticated is True
    assert sess.organization_id == "slidio_org"
