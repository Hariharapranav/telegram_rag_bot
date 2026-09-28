import pytest
from app.router.model_router import QueryComplexityRouter, model_router
from app.config import settings


def test_simple_factual_query_routes_to_flash_lite():
    simple_queries = [
        "What is the annual leave allowance?",
        "How many sick days do we get?",
        "Where is the cafeteria located?",
        "Who is the department head?",
    ]
    for q in simple_queries:
        decision = model_router.analyze(q)
        assert decision.model_tier == "simple"
        assert decision.selected_model == settings.GEMINI_MODEL_SIMPLE
        assert decision.complexity_score < 0.40
        assert "Flash-Lite" in decision.explanation or "flash-lite" in decision.selected_model


def test_complex_multi_part_query_routes_to_flash():
    complex_query = (
        "Compare the annual leave rollover policy with the sabbatical leave guidelines, "
        "and also explain how sick leave approval works step by step for long absences."
    )
    decision = model_router.analyze(complex_query)
    assert decision.model_tier == "complex"
    assert decision.selected_model == settings.GEMINI_MODEL_COMPLEX
    assert decision.complexity_score >= 0.40
    assert any("comparative" in r or "reasoning" in r or "multi_part" in r for r in decision.reasons)


def test_comparative_query_detection():
    query = "What is the difference between primary caregiver and secondary caregiver parental leave?"
    decision = model_router.analyze(query)
    assert "comparative_analysis_request" in decision.reasons
    assert decision.model_tier == "complex"


def test_deep_reasoning_detection():
    query = "Explain why an employee would be denied a remote work request under the cybersecurity policy."
    decision = model_router.analyze(query)
    assert "deep_reasoning_or_synthesis" in decision.reasons
    assert decision.model_tier == "complex"
