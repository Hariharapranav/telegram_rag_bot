import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db.repositories import DocumentChunkRepository
from app.rag.embeddings import embedding_service

logger = logging.getLogger(__name__)


class RAGRetriever:
    def __init__(self, top_k: int = settings.RAG_TOP_K, threshold: float = settings.RAG_SIMILARITY_THRESHOLD):
        self.top_k = top_k
        self.threshold = threshold
        self.embedding_service = embedding_service

    async def retrieve(
        self,
        session: AsyncSession,
        organization_id: str,
        query: str,
        query_embedding: List[float] = None,
        top_k: int = None,
        threshold: float = None
    ) -> Tuple[List[Dict[str, Any]], List[float]]:
        """
        Retrieve relevant document chunks strictly scoped by organization_id.
        Returns:
            (retrieved_chunks, query_embedding)
        """
        k = top_k or self.top_k
        sim_threshold = threshold if threshold is not None else self.threshold

        # 1. Generate query embedding if not provided
        if query_embedding is None:
            query_embedding = await self.embedding_service.get_embedding(query)

        # 2. Vector search via repository
        chunk_repo = DocumentChunkRepository(session)
        search_results = await chunk_repo.vector_search(
            organization_id=organization_id,
            query_embedding=query_embedding,
            top_k=k,
            similarity_threshold=sim_threshold
        )

        formatted_chunks = []
        for chunk, similarity in search_results:
            formatted_chunks.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "similarity": round(similarity, 4),
                "metadata": chunk.chunk_metadata or {}
            })

        logger.info(
            "Retrieved %d chunks for org %s with query '%s' (top_k=%d, threshold=%.2f)",
            len(formatted_chunks), organization_id, query[:30], k, sim_threshold
        )
        return formatted_chunks, query_embedding


rag_retriever = RAGRetriever()
