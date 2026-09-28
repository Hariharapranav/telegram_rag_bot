import pytest
from app.rag.chunking import TextChunker
from app.rag.generation import GroundedGenerator, NOT_FOUND_MESSAGE


def test_chunking_preserves_sentences_and_paragraphs():
    chunker = TextChunker(chunk_size=120, chunk_overlap=20)
    sample_text = (
        "Employees receive 24 days of annual leave. "
        "Leave accrues at 2 days per month worked.\n\n"
        "Sick leave allowance is 10 days per year. "
        "A medical certificate is mandatory after two continuous days."
    )
    chunks = chunker.split_text(sample_text)
    assert len(chunks) >= 2
    assert all("content" in c for c in chunks)
    assert all("chunk_index" in c["metadata"] for c in chunks)


@pytest.mark.asyncio
async def test_grounded_generation_with_matching_context():
    generator = GroundedGenerator()
    chunks = [
        {
            "content": "All employees are entitled to 24 days of annual leave per year.",
            "metadata": {"filename": "leave_policy.pdf", "page_number": 1},
            "similarity": 0.89
        }
    ]
    res = await generator.generate_answer(
        question="How many days of annual leave do employees get?",
        retrieved_chunks=chunks,
        model_name="gemini-2.0-flash-lite"
    )
    assert "24 days" in res["answer"]
    assert res["answer"] != NOT_FOUND_MESSAGE
    assert len(res["citations"]) == 1
    assert res["citations"][0]["source"] == "leave_policy.pdf"


@pytest.mark.asyncio
async def test_grounded_generation_anti_hallucination_when_empty():
    generator = GroundedGenerator()
    res = await generator.generate_answer(
        question="What is the stock price of Apple?",
        retrieved_chunks=[],
        model_name="gemini-2.0-flash-lite"
    )
    assert res["answer"] == NOT_FOUND_MESSAGE
    assert res["answer"] == "I couldn't find this information in your organization's documents."
