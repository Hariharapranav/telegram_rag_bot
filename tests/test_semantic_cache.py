import pytest
from app.cache.semantic_cache import SemanticCache
from app.rag.embeddings import _generate_deterministic_embedding


@pytest.mark.asyncio
async def test_semantic_cache_hit_and_miss():
    cache = SemanticCache(threshold=0.88)
    org_id = "test_org_alpha"

    q1 = "What is the annual leave allowance?"
    emb1 = _generate_deterministic_embedding(q1)
    ans1 = "Employees are entitled to 24 days of annual leave per year."

    # 1. Initially should be a cache MISS
    res = await cache.lookup(org_id, emb1)
    assert res["cache_hit"] is False

    # 2. Store question and answer
    await cache.store(
        organization_id=org_id,
        question=q1,
        question_embedding=emb1,
        answer=ans1,
        model_used="gemini-2.0-flash-lite"
    )

    # 3. Exact query lookup should HIT
    hit_res = await cache.lookup(org_id, emb1)
    assert hit_res["cache_hit"] is True
    assert hit_res["answer"] == ans1
    assert hit_res["similarity"] >= 0.99

    # 4. Semantically similar query lookup
    q_similar = "What is the annual leave allowance for full time employees?"
    emb_sim = _generate_deterministic_embedding(q_similar)
    sim_res = await cache.lookup(org_id, emb_sim, threshold=0.75)
    assert sim_res["cache_hit"] is True
    assert sim_res["answer"] == ans1


@pytest.mark.asyncio
async def test_multi_tenant_cache_isolation():
    """
    CRITICAL SECURITY TEST:
    A cached answer from Organization A must NEVER be returned to Organization B,
    even if the exact same question is asked.
    """
    cache = SemanticCache(threshold=0.85)

    org_a = "org_acme_111"
    org_b = "org_globex_222"

    secret_q = "What is the executive bonus target?"
    emb = _generate_deterministic_embedding(secret_q)
    acme_ans = "Acme offers 10% bonus."

    # Store in Org A
    await cache.store(
        organization_id=org_a,
        question=secret_q,
        question_embedding=emb,
        answer=acme_ans,
        model_used="gemini-2.0-flash"
    )

    # Org A gets cache HIT
    res_a = await cache.lookup(org_a, emb)
    assert res_a["cache_hit"] is True
    assert res_a["answer"] == acme_ans

    # Org B MUST get cache MISS
    res_b = await cache.lookup(org_b, emb)
    assert res_b["cache_hit"] is False
    assert "answer" not in res_b
