import pytest
from app.db.repositories import OrganizationRepository, UserRepository, DocumentRepository
from app.admin.handlers import process_create_org_input, process_add_user_input
from app.services.document_service import document_service


@pytest.mark.asyncio
async def test_bot_admin_create_organization(db_session):
    # Test creating organization via process_create_org_input
    input_str = "wayne_ent, Wayne Enterprises, Bruce Wayne, bruce@wayne.com, EMP-BAT-001"
    response = await process_create_org_input(db_session, input_str)
    
    assert "Organization Successfully Created" in response
    assert "Wayne Enterprises" in response
    assert "bruce@wayne.com" in response

    # Verify in DB
    org_repo = OrganizationRepository(db_session)
    org = await org_repo.get_by_id("wayne_ent")
    assert org is not None
    assert org.name == "Wayne Enterprises"

    user_repo = UserRepository(db_session)
    admin_user = await user_repo.get_by_employee_id("wayne_ent", "EMP-BAT-001")
    assert admin_user is not None
    assert admin_user.role == "admin"
    assert admin_user.email == "bruce@wayne.com"


@pytest.mark.asyncio
async def test_org_admin_add_user(db_session):
    # Setup test org
    org_repo = OrganizationRepository(db_session)
    org = await org_repo.create("Stark Labs", "stark_labs_001")

    # Add employee
    input_str = "EMP-007, Peter Parker, peter@stark.com, employee"
    response = await process_add_user_input(db_session, org.id, input_str)

    assert "User Registered Successfully" in response
    assert "Peter Parker" in response
    assert "EMP-007" in response

    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_employee_id(org.id, "EMP-007")
    assert user is not None
    assert user.role == "employee"

    # Test duplicate prevention
    dup_response = await process_add_user_input(db_session, org.id, input_str)
    assert "already registered" in dup_response


@pytest.mark.asyncio
async def test_org_admin_delete_document(db_session):
    org_repo = OrganizationRepository(db_session)
    org = await org_repo.create("Doc Org", "doc_org_001")

    # Upload document
    res = await document_service.upload_document(
        session=db_session,
        organization_id=org.id,
        filename="confidential.txt",
        content_bytes=b"This is secret company information."
    )
    doc_id = res["document_id"]

    # Verify exists
    docs = await document_service.list_documents(db_session, org.id)
    assert any(d["id"] == doc_id for d in docs)

    # Delete document
    deleted = await document_service.delete_document(db_session, org.id, doc_id)
    assert deleted is True

    # Verify deleted
    docs_after = await document_service.list_documents(db_session, org.id)
    assert not any(d["id"] == doc_id for d in docs_after)
