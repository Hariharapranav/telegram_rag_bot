import re
from typing import List, Dict, Any
from app.config import settings


class TextChunker:
    """
    Semantic and sentence-aware recursive text chunker.
    Splits text into overlapping windows preserving paragraph and sentence boundaries.
    """

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str, doc_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        doc_meta = doc_metadata or {}
        # Clean text
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Initial split by paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        raw_chunks: List[str] = []
        current_chunk = ""

        for para in paragraphs:
            # If paragraph itself is larger than chunk_size, split by sentences
            if len(para) > self.chunk_size:
                sentences = re.split(r"(?<=[.?!])\s+", para)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    if len(current_chunk) + len(sentence) + 1 <= self.chunk_size:
                        current_chunk = (current_chunk + " " + sentence).strip()
                    else:
                        if current_chunk:
                            raw_chunks.append(current_chunk)
                        # Carry over overlap if possible
                        overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else ""
                        current_chunk = (overlap_text + " " + sentence).strip()
            else:
                if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                    current_chunk = (current_chunk + "\n\n" + para).strip()
                else:
                    if current_chunk:
                        raw_chunks.append(current_chunk)
                    overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else ""
                    current_chunk = (overlap_text + "\n\n" + para).strip()

        if current_chunk:
            raw_chunks.append(current_chunk)

        chunks: List[Dict[str, Any]] = []
        for i, chunk_text in enumerate(raw_chunks):
            chunk_meta = {
                **doc_meta,
                "chunk_index": i,
                "total_chunks": len(raw_chunks),
                "char_length": len(chunk_text)
            }
            chunks.append({
                "content": chunk_text,
                "metadata": chunk_meta
            })

        return chunks


text_chunker = TextChunker()
