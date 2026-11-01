import base64
import os

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from api.app.main import app

ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "change-me-in-production-toll-admin")
BASIC_AUTH = base64.b64encode(f"admin:{ADMIN_PASS}".encode()).decode()


@pytest.mark.asyncio
async def test_admin_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_dashboard_authenticated():
    headers = {"Authorization": f"Basic {BASIC_AUTH}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin", headers=headers)
        assert resp.status_code == 200
        assert "Toll Engine Data Review" in resp.text


@pytest.mark.asyncio
async def test_admin_approve_closes_previous_rate():
    """
    Test approval workflow:
    1. Insert a PENDING rate for Nawabganj Plaza effective 2026-12-01.
    2. Call approve endpoint.
    3. Assert the pending rate became APPROVED.
    4. Assert the previous approved rate got effective_to = 2026-11-30.
    """
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/toll_mvp")
    pending_rate_id = None

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Pre-cleanup in case of prior interrupted run
            cur.execute("""
                DELETE FROM rate 
                WHERE charging_point_id = 101 
                  AND vehicle_class_id = 1 
                  AND journey = 'ONE_WAY' 
                  AND effective_from = '2026-12-01';
            """)
            cur.execute("""
                UPDATE rate
                SET effective_to = NULL
                WHERE charging_point_id = 101
                  AND vehicle_class_id = 1
                  AND journey = 'ONE_WAY'
                  AND effective_from = '2026-04-01'
                  AND status = 'APPROVED';
            """)
            cur.execute("""
                INSERT INTO rate (
                    charging_point_id, vehicle_class_id, journey,
                    amount_inr, effective_from, effective_to, status, source_document_id
                ) VALUES (

                    101, 1, 'ONE_WAY',
                    105.00, '2026-12-01', NULL, 'PENDING', 1
                ) RETURNING id;
            """)
            pending_rate_id = cur.fetchone()[0]
            conn.commit()

    assert pending_rate_id is not None

    try:
        headers = {"Authorization": f"Basic {BASIC_AUTH}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/admin/rate/{pending_rate_id}/approve", headers=headers)
            assert resp.status_code == 303

        # Verify DB state
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # Check newly approved rate
                cur.execute("SELECT status FROM rate WHERE id = %s;", (pending_rate_id,))
                assert cur.fetchone()[0] == "APPROVED"

                # Check previous rate is properly closed without overlapping
                cur.execute("""
                    SELECT effective_to
                    FROM rate
                    WHERE charging_point_id = 101
                      AND vehicle_class_id = 1
                      AND journey = 'ONE_WAY'
                      AND effective_from = '2026-04-01'
                      AND status = 'APPROVED';
                """)
                prev_eff_to = cur.fetchone()[0]
                assert str(prev_eff_to) == "2026-11-30"
    finally:
        # Teardown: delete test rate and restore the previous rate's open-ended effective_to
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rate WHERE id = %s;", (pending_rate_id,))
                cur.execute("""
                    UPDATE rate
                    SET effective_to = NULL
                    WHERE charging_point_id = 101
                      AND vehicle_class_id = 1
                      AND journey = 'ONE_WAY'
                      AND effective_from = '2026-04-01'
                      AND status = 'APPROVED';
                """)
                conn.commit()
