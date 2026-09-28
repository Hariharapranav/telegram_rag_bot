import pytest
from app.db.repositories import OrganizationRepository
from app.services.document_service import document_service
from app.rag.retrieval import rag_retriever


@pytest.mark.asyncio
async def test_multi_tenant_document_isolation(db_session):
    """
    CRITICAL SECURITY & COMPLIANCE TEST:
    Employees in Organization A must NEVER be able to retrieve or view documents
    belonging to Organization B.
    """
    org_repo = OrganizationRepository(db_session)

    # 1. Setup two separate organizations
    org_a = await org_repo.create("Alpha Corp", org_id="org_alpha_001")
    org_b = await org_repo.create("Beta Corp", org_id="org_beta_002")

    # 2. Ingest confidential document for Org A
    doc_a_content = (
        "Project Apollo Financial Roadmap.\n"
        "Confidential: Alpha Corp approved a budget of $5,000,000 for Project Apollo.\n"
        "The project lead is Dr. Robert Oppenheimer."
    ).encode("utf-8")

    await document_service.upload_document(
        session=db_session,
        organization_id="org_alpha_001",
        filename="alpha_confidential.txt",
        content_bytes=doc_a_content
    )

    # 3. Ingest confidential document for Org B
    doc_b_content = (
        "Project Titan Financial Roadmap.\n"
        "Confidential: Beta Corp approved a budget of $9,000,000 for Project Titan.\n"
        "The project lead is Elena Rostova."
    ).encode("utf-8")

    await document_service.upload_document(
        session=db_session,
        organization_id="org_beta_002",
        filename="beta_confidential.txt",
        content_bytes=doc_b_content
    )

    # 4. Org A user queries for "Project Financial Roadmap budget"
    query = "Project Financial Roadmap budget"
    chunks_a, _ = await rag_retriever.retrieve(
        session=db_session,
        organization_id="org_alpha_001",
        query=query,
        threshold=0.20
    )

    # Assert Org A ONLY retrieved Alpha Corp content
    assert len(chunks_a) > 0
    for chunk in chunks_a:
        assert "Alpha Corp" in chunk["content"] or "Apollo" in chunk["content"]
        assert "Beta Corp" not in chunk["content"]
        assert "Titan" not in chunk["content"]
        assert chunk["metadata"]["organization_id"] == "org_alpha_001"

    # 5. Org B user queries the exact same prompt
    chunks_b, _ = await rag_retriever.retrieve(
        session=db_session,
        organization_id="org_beta_002",
        query=query,
        threshold=0.20
    )

    # Assert Org B ONLY retrieved Beta Corp content
    assert len(chunks_b) > 0
    for chunk in chunks_b:
        assert "Beta Corp" in chunk["content"] or "Titan" in chunk["content"]
        assert "Alpha Corp" not in chunk["content"]
        assert "Apollo" not in chunk["content"]
        assert chunk["metadata"]["organization_id"] == "org_beta_002"
