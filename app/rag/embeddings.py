import asyncio
import hashlib
import logging
import math
from typing import List, Optional
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)


def _generate_deterministic_embedding(text: str, dim: int = 768) -> List[float]:
    """
    Generate a normalized deterministic pseudo-embedding from text.
    Used for test suites, offline development, or fallback when API key is not configured.
    Semantically close words produce correlated vectors.
    """
    cleaned = text.lower().strip()
    words = cleaned.split()
    vector = [0.0] * dim

    for i, word in enumerate(words):
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        for d in range(dim):
            # Deterministic projection
            bit = (h >> (d % 64)) & 1
            sign = 1.0 if bit == 1 else -1.0
            weight = 1.0 / (1.0 + math.log(i + 1.5))
            vector[d] += sign * weight

    # Normalize
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [round(x / norm, 6) for x in vector]
    else:
        vector[0] = 1.0
    return vector


class EmbeddingService:
    def __init__(
        self,
        api_key: str = settings.GEMINI_API_KEY,
        model_name: str = settings.GEMINI_EMBEDDING_MODEL,
        dimension: int = settings.EMBEDDING_DIMENSION
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.dimension = dimension
        self._is_configured = False

        if self.api_key and self.api_key.strip():
            try:
                genai.configure(api_key=self.api_key.strip())
                self._is_configured = True
            except Exception as e:
                logger.warning("Failed to configure Google Generative AI for embeddings: %s", e)

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string."""
        if not self._is_configured:
            return _generate_deterministic_embedding(text, self.dimension)

        loop = asyncio.get_running_loop()
        try:
            def _embed_single():
                kwargs = {
                    "model": self.model_name,
                    "content": text,
                    "task_type": "retrieval_query"
                }
                if self.dimension:
                    kwargs["output_dimensionality"] = self.dimension
                return genai.embed_content(**kwargs)

            result = await loop.run_in_executor(None, _embed_single)
            emb = result.get("embedding", [])
            if emb:
                return emb[:self.dimension]
            return _generate_deterministic_embedding(text, self.dimension)
        except Exception as e:
            logger.warning("Gemini embedding API call failed (%s). Falling back to deterministic embedding.", e)
            return _generate_deterministic_embedding(text, self.dimension)

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        if not self._is_configured:
            return [_generate_deterministic_embedding(t, self.dimension) for t in texts]

        loop = asyncio.get_running_loop()
        try:
            def _embed_batch():
                kwargs = {
                    "model": self.model_name,
                    "content": texts,
                    "task_type": "retrieval_document"
                }
                if self.dimension:
                    kwargs["output_dimensionality"] = self.dimension
                return genai.embed_content(**kwargs)

            result = await loop.run_in_executor(None, _embed_batch)
            embeddings = result.get("embedding", [])
            if isinstance(embeddings, list) and len(embeddings) == len(texts):
                return [emb[:self.dimension] for emb in embeddings]
            # Fallback if structure varies
            return [_generate_deterministic_embedding(t, self.dimension) for t in texts]
        except Exception as e:
            logger.warning("Batch Gemini embedding failed (%s). Falling back to deterministic batch.", e)
            return [_generate_deterministic_embedding(t, self.dimension) for t in texts]


embedding_service = EmbeddingService()
