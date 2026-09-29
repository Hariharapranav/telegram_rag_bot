import logging
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db.repositories import DocumentRepository
from app.rag.ingestion import document_ingestion

logger = logging.getLogger(__name__)


class DocumentService:
    @staticmethod
    async def upload_document(
        session: AsyncSession,
        organization_id: str,
        filename: str,
        content_bytes: bytes
    ) -> Dict[str, Any]:
        """Upload, ingest, chunk and embed a document."""
        return await document_ingestion.ingest_document(
            session=session,
            organization_id=organization_id,
            filename=filename,
            content_bytes=content_bytes
        )

    @staticmethod
    async def list_documents(
        session: AsyncSession,
        organization_id: str
    ) -> List[Dict[str, Any]]:
        """List documents for an organization."""
        repo = DocumentRepository(session)
        docs = await repo.list_by_org(organization_id)
        return [
            {
                "id": doc.id,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "chunk_count": doc.chunk_count,
                "uploaded_at": doc.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                "storage_path": doc.storage_path
            }
            for doc in docs
        ]

    @staticmethod
    async def delete_document(
        session: AsyncSession,
        organization_id: str,
        document_id: str
    ) -> bool:
        """Delete document, all associated chunks, and remove from Supabase Storage."""
        repo = DocumentRepository(session)
        doc = await repo.get_by_id(document_id, organization_id)
        if not doc:
            return False

        storage_path = doc.storage_path
        deleted = await repo.delete(document_id, organization_id)

        if deleted and storage_path and settings.supabase.is_configured:
            try:
                url = f"{settings.supabase.url}/storage/v1/object/{settings.supabase.bucket}"
                headers = {
                    "Authorization": f"Bearer {settings.supabase.service_role_key_plain}",
                    "apiKey": settings.supabase.service_role_key_plain,
                    "apikey": settings.supabase.service_role_key_plain,
                    "Content-Type": "application/json"
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.request("DELETE", url, headers=headers, json={"prefixes": [storage_path]})
                    logger.info("Deleted %s from Supabase Storage bucket %s", storage_path, settings.supabase.bucket)
            except Exception as e:
                logger.warning("Failed to delete %s from Supabase Storage: %s", storage_path, e)

        return deleted


document_service = DocumentService()
