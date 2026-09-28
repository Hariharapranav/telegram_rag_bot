import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal, engine, Base
from app.db.repositories import OrganizationRepository, UserRepository, QueryLogRepository
from app.services.document_service import document_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_data")

SAMPLE_DOCS_DIR = Path(__file__).parent / "sample_documents"


async def seed():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        org_repo = OrganizationRepository(session)
        user_repo = UserRepository(session)
        log_repo = QueryLogRepository(session)

        # 1. Create Organizations
        logger.info("Creating organizations...")
        acme_org = await org_repo.get_by_id("acme_corp_001")
        if not acme_org:
            acme_org = await org_repo.create("Acme Corporation", org_id="acme_corp_001")
            logger.info("Created %s (ID: %s)", acme_org.name, acme_org.id)

        globex_org = await org_repo.get_by_id("globex_corp_002")
        if not globex_org:
            globex_org = await org_repo.create("Globex Corporation", org_id="globex_corp_002")
            logger.info("Created %s (ID: %s)", globex_org.name, globex_org.id)

        # 2. Create Users for Acme Corp
        logger.info("Creating users...")
        alice = await user_repo.get_by_employee_id("acme_corp_001", "EMP-001")
        if not alice:
            alice = await user_repo.create(
                organization_id="acme_corp_001",
                employee_id="EMP-001",
                name="Alice Smith",
                email="alice@acme.com",
                role="admin"
            )
            logger.info("Created Admin: %s (%s)", alice.name, alice.employee_id)

        bob = await user_repo.get_by_employee_id("acme_corp_001", "EMP-002")
        if not bob:
            bob = await user_repo.create(
                organization_id="acme_corp_001",
                employee_id="EMP-002",
                name="Bob Jones",
                email="bob@acme.com",
                role="employee"
            )
            logger.info("Created Employee: %s (%s)", bob.name, bob.employee_id)

        charlie = await user_repo.get_by_employee_id("acme_corp_001", "EMP-003")
        if not charlie:
            charlie = await user_repo.create(
                organization_id="acme_corp_001",
                employee_id="EMP-003",
                name="Charlie Brown",
                email="charlie@acme.com",
                role="employee"
            )
            logger.info("Created Employee: %s (%s)", charlie.name, charlie.employee_id)

        # 3. Create User for Globex Corp
        diana = await user_repo.get_by_employee_id("globex_corp_002", "EMP-999")
        if not diana:
            diana = await user_repo.create(
                organization_id="globex_corp_002",
                employee_id="EMP-999",
                name="Diana Prince",
                email="diana@globex.com",
                role="employee"
            )
            logger.info("Created Globex Employee: %s (%s)", diana.name, diana.employee_id)

        # 4. Ingest Documents
        logger.info("Ingesting sample documents...")
        acme_leave_file = SAMPLE_DOCS_DIR / "acme_leave_policy.txt"
        if acme_leave_file.exists():
            with open(acme_leave_file, "rb") as f:
                res1 = await document_service.upload_document(
                    session=session,
                    organization_id="acme_corp_001",
                    filename="acme_leave_policy.txt",
                    content_bytes=f.read()
                )
                logger.info("Ingested %s (%d chunks)", res1["filename"], res1["chunk_count"])

        acme_wfh_file = SAMPLE_DOCS_DIR / "acme_wfh_policy.txt"
        if acme_wfh_file.exists():
            with open(acme_wfh_file, "rb") as f:
                res2 = await document_service.upload_document(
                    session=session,
                    organization_id="acme_corp_001",
                    filename="acme_wfh_policy.txt",
                    content_bytes=f.read()
                )
                logger.info("Ingested %s (%d chunks)", res2["filename"], res2["chunk_count"])

        globex_comp_file = SAMPLE_DOCS_DIR / "globex_compensation_policy.txt"
        if globex_comp_file.exists():
            with open(globex_comp_file, "rb") as f:
                res3 = await document_service.upload_document(
                    session=session,
                    organization_id="globex_corp_002",
                    filename="globex_compensation_policy.txt",
                    content_bytes=f.read()
                )
                logger.info("Ingested %s (%d chunks)", res3["filename"], res3["chunk_count"])

        # 5. Populate Seed Query Logs for Analytics Showcase
        logger.info("Seeding initial query analytics logs...")
        sample_logs = [
            {
                "user_id": bob.id,
                "question": "What is the company's annual leave policy?",
                "model_used": "gemini-2.0-flash-lite",
                "cache_hit": False,
                "input_tokens": 312,
                "output_tokens": 58,
                "cost": 0.000041,
                "latency_ms": 420.5
            },
            {
                "user_id": bob.id,
                "question": "What is the annual leave allowance for employees?",
                "model_used": "gemini-2.0-flash-lite (cache)",
                "cache_hit": True,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "latency_ms": 12.3
            },
            {
                "user_id": charlie.id,
                "question": "Compare the leave rollover rules with sabbatical eligibility step by step.",
                "model_used": "gemini-2.0-flash",
                "cache_hit": False,
                "input_tokens": 480,
                "output_tokens": 124,
                "cost": 0.000098,
                "latency_ms": 680.2
            },
            {
                "user_id": charlie.id,
                "question": "How much is the home office equipment stipend?",
                "model_used": "gemini-2.0-flash-lite",
                "cache_hit": False,
                "input_tokens": 290,
                "output_tokens": 42,
                "cost": 0.000034,
                "latency_ms": 380.1
            },
            {
                "user_id": bob.id,
                "question": "How much is the equipment reimbursement for remote work?",
                "model_used": "gemini-2.0-flash-lite (cache)",
                "cache_hit": True,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "latency_ms": 10.8
            }
        ]

        for s in sample_logs:
            await log_repo.create(
                organization_id="acme_corp_001",
                question=s["question"],
                model_used=s["model_used"],
                cache_hit=s["cache_hit"],
                input_tokens=s["input_tokens"],
                output_tokens=s["output_tokens"],
                estimated_cost=s["cost"],
                latency_ms=s["latency_ms"],
                user_id=s["user_id"]
            )

        logger.info("Seed completed successfully! Acme Corp and Globex Corp are fully initialized.")


if __name__ == "__main__":
    asyncio.run(seed())
