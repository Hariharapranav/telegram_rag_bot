import io
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db.repositories import DocumentRepository, DocumentChunkRepository
from app.rag.chunking import text_chunker
from app.rag.embeddings import embedding_service

logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    def __init__(self):
        self.chunker = text_chunker
        self.embedding_service = embedding_service

    def extract_text_from_file(self, content_bytes: bytes, filename: str) -> str:
        """Extract plain text from PDF, TXT, MD, etc."""
        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(content_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages_text.append(f"[Page {i+1}]\n{txt.strip()}")
            return "\n\n".join(pages_text)
        elif lower_name.endswith(".docx"):
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    paragraphs = []
                    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                        texts = [node.text for node in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if node.text]
                        if texts:
                            paragraphs.append("".join(texts))
                    return "\n\n".join(paragraphs)
            except Exception as e:
                logger.error("Failed to parse docx file %s: %s", filename, e)
                return ""
        else:
            # Assume UTF-8 text (or fallback latin-1)
            try:
                return content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return content_bytes.decode("latin-1", errors="ignore")

    async def upload_to_storage(self, organization_id: str, filename: str, content_bytes: bytes) -> str:
        """
        Upload file to Supabase Storage bucket under documents/{org_id}/{filename}.
        Falls back to local file storage if Supabase credentials are not active.
        """
        storage_path = f"documents/{organization_id}/{filename}"

        # Check if Supabase credentials are configured via structured settings
        if settings.supabase.is_configured:
            try:
                import mimetypes
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    if filename.lower().endswith(".txt"):
                        content_type = "text/plain"
                    elif filename.lower().endswith(".pdf"):
                        content_type = "application/pdf"
                    elif filename.lower().endswith(".md"):
                        content_type = "text/markdown"
                    elif filename.lower().endswith(".docx"):
                        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    else:
                        content_type = "text/plain"

                # Upload to Supabase Storage REST endpoint
                url = f"{settings.supabase.url}/storage/v1/object/{settings.supabase.bucket}/{storage_path}"
                headers = {
                    "Authorization": f"Bearer {settings.supabase.service_role_key_plain}",
                    "apiKey": settings.supabase.service_role_key_plain,
                    "apikey": settings.supabase.service_role_key_plain,
                    "Content-Type": content_type,
                    "x-upsert": "true"
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, headers=headers, content=content_bytes)
                    if resp.status_code in [200, 201]:
                        logger.info("Successfully uploaded %s to Supabase Storage bucket %s", storage_path, settings.supabase.bucket)
                        return storage_path
                    else:
                        logger.warning("Supabase storage upload returned %d: %s. Falling back to local storage.", resp.status_code, resp.text)
            except Exception as e:
                logger.warning("Failed uploading to Supabase Storage: %s. Using local fallback.", e)

        # Local storage fallback
        fallback_dir = Path(settings.STORAGE_LOCAL_FALLBACK_DIR) / organization_id
        fallback_dir.mkdir(parents=True, exist_ok=True)
        local_file_path = fallback_dir / filename
        with open(local_file_path, "wb") as f:
            f.write(content_bytes)
        logger.info("Saved %s to local storage at %s", filename, local_file_path)
        return str(local_file_path)

    async def ingest_document(
        self,
        session: AsyncSession,
        organization_id: str,
        filename: str,
        content_bytes: bytes
    ) -> Dict[str, Any]:
        """
        End-to-end ingestion:
        1. Extract text
        2. Upload raw file to storage
        3. Create Document DB entry
        4. Split into chunks
        5. Generate vector embeddings
        6. Persist DocumentChunks with organization_id isolation
        """
        logger.info("Starting ingestion for %s (org: %s)", filename, organization_id)
        file_size = len(content_bytes)

        # 1. Extract text
        raw_text = self.extract_text_from_file(content_bytes, filename)
        if not raw_text.strip():
            raise ValueError(f"Could not extract any readable text from {filename}")

        # 2. Upload to storage
        storage_path = await self.upload_to_storage(organization_id, filename, content_bytes)

        # 3. Create Document record
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.create(
            organization_id=organization_id,
            filename=filename,
            storage_path=storage_path,
            file_size=file_size,
            chunk_count=0
        )

        # 4. Chunk text
        chunks_info = self.chunker.split_text(
            raw_text,
            doc_metadata={
                "document_id": doc.id,
                "filename": filename,
                "organization_id": organization_id
            }
        )

        # 5. Embed chunks in batch
        texts_to_embed = [c["content"] for c in chunks_info]
        embeddings = await self.embedding_service.get_embeddings_batch(texts_to_embed)

        # 6. Save chunks in DB
        chunk_data_list = []
        for c_info, emb in zip(chunks_info, embeddings):
            chunk_data_list.append({
                "document_id": doc.id,
                "organization_id": organization_id,
                "content": c_info["content"],
                "embedding": emb,
                "chunk_metadata": c_info["metadata"]
            })

        chunk_repo = DocumentChunkRepository(session)
        await chunk_repo.create_chunks(chunk_data_list)

        # Update doc chunk count
        doc.chunk_count = len(chunk_data_list)
        await session.commit()

        logger.info("Ingestion complete for doc %s: %d chunks indexed", doc.id, len(chunk_data_list))
        return {
            "document_id": doc.id,
            "filename": filename,
            "file_size": file_size,
            "chunk_count": len(chunk_data_list),
            "storage_path": storage_path
        }


document_ingestion = DocumentIngestionPipeline()
