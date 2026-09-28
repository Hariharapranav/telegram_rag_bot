import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
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
        """Delete document and all associated chunks."""
        repo = DocumentRepository(session)
        return await repo.delete(document_id, organization_id)


document_service = DocumentService()
