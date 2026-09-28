import pytest
from app.db.repositories import OrganizationRepository, UserRepository, QueryLogRepository
from app.admin.analytics import admin_analytics


@pytest.mark.asyncio
async def test_admin_analytics_calculations(db_session):
    org_repo = OrganizationRepository(db_session)
    user_repo = UserRepository(db_session)
    log_repo = QueryLogRepository(db_session)

    org = await org_repo.create("Metrics Corp", org_id="org_metrics_1")
    user = await user_repo.create(
        organization_id="org_metrics_1",
        employee_id="EMP-900",
        name="Alex River",
        email="alex@metricscorp.com"
    )

    # Add 2 LLM calls and 2 Cache hits
    await log_repo.create(
        organization_id="org_metrics_1",
        user_id=user.id,
        question="Query 1",
        model_used="gemini-2.0-flash-lite",
        cache_hit=False,
        input_tokens=200,
        output_tokens=50,
        estimated_cost=0.00003,
        latency_ms=350.0
    )
    await log_repo.create(
        organization_id="org_metrics_1",
        user_id=user.id,
        question="Query 2",
        model_used="gemini-2.0-flash",
        cache_hit=False,
        input_tokens=400,
        output_tokens=100,
        estimated_cost=0.00008,
        latency_ms=550.0
    )
    await log_repo.create(
        organization_id="org_metrics_1",
        user_id=user.id,
        question="Query 1 repeated",
        model_used="gemini-2.0-flash-lite (cache)",
        cache_hit=True,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0.0,
        latency_ms=15.0
    )
    await log_repo.create(
        organization_id="org_metrics_1",
        user_id=user.id,
        question="Query 2 repeated",
        model_used="gemini-2.0-flash (cache)",
        cache_hit=True,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0.0,
        latency_ms=12.0
    )

    # Verify org stats
    stats = await log_repo.get_org_stats("org_metrics_1")
    assert stats["total_queries"] == 4
    assert stats["cache_hits"] == 2
    assert stats["cache_hit_rate"] == 50.0
    assert stats["gemini_calls"] == 2
    assert stats["total_input_tokens"] == 600
    assert stats["total_output_tokens"] == 150
    assert stats["estimated_gemini_cost"] == pytest.approx(0.00011, abs=1e-5)
    assert stats["average_latency_ms"] == pytest.approx(231.75, abs=0.5)

    # Verify formatted text reports
    stats_text = await admin_analytics.get_stats_summary(db_session, "org_metrics_1")
    assert "Executive AI Analytics: Metrics Corp" in stats_text
    assert "Cache Hit Rate:" in stats_text
    assert "50.0%" in stats_text

    users_text = await admin_analytics.get_users_summary(db_session, "org_metrics_1")
    assert "Alex River" in users_text
    assert "EMP-900" in users_text
