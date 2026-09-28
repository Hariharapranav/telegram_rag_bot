import sys
import os
import asyncio
import logging
from pathlib import Path
import httpx

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sync_storage")

FALLBACK_DIR = Path(__file__).resolve().parent.parent / "storage_fallback"
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "scripts" / "sample_documents"


async def sync_storage():
    if not settings.supabase.is_configured:
        logger.error(
            "\n" + "=" * 70 + "\n"
            "[ERROR] SUPABASE_SERVICE_ROLE_KEY is not configured in .env!\n\n"
            "To upload files to Supabase Storage:\n"
            "1. Open Supabase Dashboard: https://supabase.com/dashboard/project/yzffmlsvqcxqwrzttdhv\n"
            "2. In the left sidebar, click 'Project Settings' -> 'API Keys'\n"
            "3. Copy the 'service_role' (secret) key.\n"
            "4. Paste it into .env under SUPABASE_SERVICE_ROLE_KEY:\n"
            "   SUPABASE_SERVICE_ROLE_KEY=\"eyJhbGciOi...\"\n"
            "=" * 70 + "\n"
        )
        return False

    url_base = f"{settings.supabase.url}/storage/v1/object/{settings.supabase.bucket}"
    headers = {
        "Authorization": f"Bearer {settings.supabase.service_role_key_plain}",
        "x-upsert": "true"
    }

    uploaded_count = 0

    def get_mime(fname: str) -> str:
        fl = fname.lower()
        if fl.endswith(".txt"):
            return "text/plain"
        elif fl.endswith(".pdf"):
            return "application/pdf"
        elif fl.endswith(".md"):
            return "text/markdown"
        elif fl.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "text/plain"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Sync from storage_fallback/<org_id>/<filename>
        if FALLBACK_DIR.exists():
            for org_dir in FALLBACK_DIR.iterdir():
                if org_dir.is_dir():
                    org_id = org_dir.name
                    for file_path in org_dir.iterdir():
                        if file_path.is_file():
                            filename = file_path.name
                            storage_path = f"documents/{org_id}/{filename}"
                            upload_url = f"{url_base}/{storage_path}"
                            content = file_path.read_bytes()
                            req_headers = {
                                "Authorization": f"Bearer {settings.supabase.service_role_key_plain}",
                                "Content-Type": get_mime(filename),
                                "x-upsert": "true"
                            }

                            resp = await client.post(upload_url, headers=req_headers, content=content)
                            if resp.status_code in [200, 201]:
                                logger.info("[OK] Uploaded %s to Supabase Storage (%s)", storage_path, settings.supabase.bucket)
                                uploaded_count += 1
                            else:
                                logger.warning("[WARN] Failed to upload %s: status %d %s", storage_path, resp.status_code, resp.text)

        # 2. Sync sample documents for Acme and Globex
        sample_mappings = [
            ("acme_corp_001", SAMPLE_DIR / "acme_leave_policy.txt"),
            ("acme_corp_001", SAMPLE_DIR / "acme_wfh_policy.txt"),
            ("globex_corp_002", SAMPLE_DIR / "globex_compensation_policy.txt")
        ]
        for org_id, sample_file in sample_mappings:
            if sample_file.exists():
                filename = sample_file.name
                storage_path = f"documents/{org_id}/{filename}"
                upload_url = f"{url_base}/{storage_path}"
                content = sample_file.read_bytes()
                req_headers = {
                    "Authorization": f"Bearer {settings.supabase.service_role_key_plain}",
                    "Content-Type": get_mime(filename),
                    "x-upsert": "true"
                }

                resp = await client.post(upload_url, headers=req_headers, content=content)
                if resp.status_code in [200, 201]:
                    logger.info("[OK] Uploaded sample %s to Supabase Storage", storage_path)
                    uploaded_count += 1
                else:
                    logger.warning("[WARN] Failed to upload sample %s: status %d %s", storage_path, resp.status_code, resp.text)

    # 3. Update storage_path in Supabase documents table
    from sqlalchemy import text
    from app.db.database import engine

    async with engine.begin() as conn:
        logger.info("Updating storage_path in Supabase documents table...")
        await conn.execute(
            text("""
                UPDATE public.documents
                SET storage_path = 'documents/' || organization_id || '/' || filename
                WHERE storage_path LIKE '%storage_fallback%';
            """)
        )
        logger.info("[OK] Updated storage_path references in public.documents!")

    logger.info("[SUCCESS] Sync complete! Total files uploaded to Supabase Storage: %d", uploaded_count)
    return True


if __name__ == "__main__":
    success = asyncio.run(sync_storage())
    sys.exit(0 if success else 1)
