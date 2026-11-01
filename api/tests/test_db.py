import json
import os
from decimal import Decimal

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/toll_mvp")


@pytest.fixture(scope="session")
def db_conn():
    """Connect to the seeded test database."""
    try:
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"Database not available at {DATABASE_URL}: {e}")


def test_reference_data_loaded(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM vehicle_class;")
        assert cur.fetchone()[0] == 6

        cur.execute("SELECT count(*) FROM operator WHERE code IN ('NHAI', 'MORTH', 'UPEIDA');")
        assert cur.fetchone()[0] == 3

        cur.execute("SELECT pass_accepted FROM operator WHERE code = 'NHAI';")
        assert cur.fetchone()[0] is True

        cur.execute("SELECT pass_accepted FROM operator WHERE code = 'UPEIDA';")
        assert cur.fetchone()[0] is False


def test_plazas_on_route_travel_order_and_crossing_excluded(db_conn):
    """
    Route from Lucknow to Kanpur westbound along NH-27 passing:
    1. Nawabganj Toll Plaza at (80.6015, 26.6340) ~90 deg bearing.
    2. SH-25 Crossing Plaza at (80.3000, 26.5000) ~0 deg bearing (perpendicular).
    3. Barajod Toll Plaza at (79.9500, 26.4150) ~100 deg bearing.
    The route runs roughly east-to-west (bearing ~250-270 deg).
    The crossing plaza (bearing 0 deg) deviates by ~90 deg and must be excluded!
    """
    route_geojson = json.dumps(
        {
            "type": "LineString",
            "coordinates": [
                [80.8000, 26.7500],
                [80.6015, 26.6340],  # Nawabganj Plaza (id 101)
                [80.3000, 26.5000],  # Crossing Plaza (id 103)
                [79.9500, 26.4150],  # Barajod Plaza (id 102)
                [79.8000, 26.3500],
            ],
        }
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT charging_point_id, position_on_route FROM plazas_on_route(%s, 500);",
            (route_geojson,),
        )
        rows = cur.fetchall()

        # Plazas found must be Nawabganj (101) then Barajod (102) in travel order.
        # Crossing Plaza (103) must be excluded!
        plaza_ids = [r[0] for r in rows]
        assert plaza_ids == [101, 102]
        # Verify travel order (increasing position)
        assert rows[0][1] < rows[1][1]


def test_closed_sections_on_route(db_conn):
    """
    Route entering Agra-Lucknow Expressway at Mohan Road (id 301)
    and exiting at Agra (id 303), passing through Kannauj (id 302).
    """
    route_geojson = json.dumps(
        {
            "type": "LineString",
            "coordinates": [
                [80.7710, 26.8320],  # Mohan Road (entry)
                [79.8800, 27.0500],  # Kannauj
                [78.1000, 27.1500],  # Agra (exit)
            ],
        }
    )

    with db_conn.cursor() as cur:
        query = (
            "SELECT charging_point_id, entry_interchange_id, exit_interchange_id "
            "FROM closed_sections_on_route(%s, 500);"
        )
        cur.execute(query, (route_geojson,))
        rows = cur.fetchall()
        assert len(rows) == 1
        charging_point_id, entry_id, exit_id = rows[0]
        assert charging_point_id == 201
        assert entry_id == 301
        assert exit_id == 303


def test_rates_before_and_after_april_1(db_conn):
    """
    Nawabganj Toll Plaza (id 101) has:
    - 2025-04-01 to 2026-03-31: ₹95
    - 2026-04-01 onwards: ₹100
    """
    with db_conn.cursor() as cur:
        # Before 1 April 2026
        cur.execute("""
            SELECT amount_inr, pass_accepted, trip_units
            FROM rate_for(
                101::int, NULL::int, NULL::int, 1::smallint,
                'ONE_WAY'::journey_type, '2026-03-31'::date
            );
        """)
        row_prev = cur.fetchone()
        assert row_prev is not None
        assert row_prev[0] == Decimal("95.00")
        assert row_prev[1] is True
        assert row_prev[2] == 1

        # On or after 1 April 2026
        cur.execute("""
            SELECT amount_inr, pass_accepted, trip_units
            FROM rate_for(
                101::int, NULL::int, NULL::int, 1::smallint,
                'ONE_WAY'::journey_type, '2026-04-01'::date
            );
        """)
        row_new = cur.fetchone()
        assert row_new is not None
        assert row_new[0] == Decimal("100.00")
        assert row_new[1] is True


def test_overlapping_approved_rate_rejected(db_conn):
    """
    Exclusion constraint `no_overlapping_approved_rates` must reject
    an overlapping approved rate for the same point, class, and journey.
    """
    with pytest.raises(psycopg.Error) as exc_info:
        with db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rate (
                    charging_point_id, vehicle_class_id, journey,
                    amount_inr, effective_from, effective_to, status, source_document_id
                ) VALUES (
                    101, 1, 'ONE_WAY',
                    110.00, '2026-03-01', '2026-05-01', 'APPROVED', 1
                );
            """)
    assert "no_overlapping_approved_rates" in str(exc_info.value)
