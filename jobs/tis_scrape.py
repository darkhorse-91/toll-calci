import os
from decimal import Decimal
from typing import Any

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/toll_mvp")


def parse_and_load_tis_plaza(
    conn: psycopg.Connection,
    source_doc_id: int,
    plaza_data: dict[str, Any],
) -> dict[str, int]:
    """
    Loads or updates an NHAI TIS plaza and its rates.
    If a rate is new or differs by >10% from existing approved rate,
    it is inserted with status 'PENDING' for admin review.
    """
    stats = {"plazas_processed": 0, "rates_approved": 0, "rates_pending": 0}

    tis_id = plaza_data["tis_plaza_id"]
    name = plaza_data["name"]
    state = plaza_data["state"]
    lat = plaza_data.get("lat")
    lng = plaza_data.get("lng")
    bearing = plaza_data.get("road_bearing_deg")

    with conn.cursor() as cur:
        # 1. Fetch or create charging_point
        cur.execute(
            "SELECT id, status FROM charging_point WHERE tis_plaza_id = %s;",
            (tis_id,),
        )
        row = cur.fetchone()
        if row:
            charging_point_id = row[0]
            # Ensure it is active if it reappeared
            if row[1] == "SUSPENDED":
                cur.execute(
                    "UPDATE charging_point SET status = 'ACTIVE' WHERE id = %s;",
                    (charging_point_id,),
                )
        else:
            cur.execute(
                """
                INSERT INTO charging_point (
                    kind, operator_id, name, state, tis_plaza_id,
                    geom, road_bearing_deg, trip_units, is_mlff, status, source_document_id
                ) VALUES (
                    'PLAZA',
                    (SELECT id FROM operator WHERE code = 'NHAI'),
                    %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, 1, false, 'ACTIVE', %s
                ) RETURNING id;
                """,
                (name, state, tis_id, lng, lat, bearing, source_doc_id),
            )
            charging_point_id = cur.fetchone()[0]

        stats["plazas_processed"] += 1

        # 2. Process Rates
        for r in plaza_data.get("rates", []):
            vehicle_class_code = r["vehicle_class"]
            journey = r["journey"]
            amount = Decimal(str(r["amount"]))
            effective_from = r["effective_from"]
            effective_to = r.get("effective_to")

            # Get vehicle_class_id
            cur.execute(
                "SELECT id FROM vehicle_class WHERE code = %s;",
                (vehicle_class_code,),
            )
            vc_row = cur.fetchone()
            if not vc_row:
                continue
            vc_id = vc_row[0]

            # Check existing approved rate for this point and class
            cur.execute(
                """
                SELECT id, amount_inr
                FROM rate
                WHERE charging_point_id = %s
                  AND vehicle_class_id = %s
                  AND journey = %s::journey_type
                  AND status = 'APPROVED'
                  AND (effective_to IS NULL OR effective_to >= %s::date)
                ORDER BY effective_from DESC
                LIMIT 1;
                """,
                (charging_point_id, vc_id, journey, effective_from),
            )
            existing_approved = cur.fetchone()

            rate_status = "APPROVED"
            if existing_approved:
                prev_amount = existing_approved[1]
                pct_change = abs(amount - prev_amount) / prev_amount
                # If rate change exceeds 10%, flag as PENDING
                if pct_change > Decimal("0.10"):
                    rate_status = "PENDING"
            else:
                # New rate is submitted for review
                rate_status = "PENDING"

            # Check if this exact rate row already exists
            cur.execute(
                """
                SELECT id FROM rate
                WHERE charging_point_id = %s
                  AND vehicle_class_id = %s
                  AND journey = %s::journey_type
                  AND amount_inr = %s
                  AND effective_from = %s::date;
                """,
                (charging_point_id, vc_id, journey, amount, effective_from),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO rate (
                        charging_point_id, vehicle_class_id, journey,
                        amount_inr, effective_from, effective_to, status, source_document_id
                    ) VALUES (
                        %s, %s, %s::journey_type,
                        %s, %s::date, %s, %s::review_status, %s
                    );
                    """,
                    (
                        charging_point_id,
                        vc_id,
                        journey,
                        amount,
                        effective_from,
                        effective_to,
                        rate_status,
                        source_doc_id,
                    ),
                )
                if rate_status == "APPROVED":
                    stats["rates_approved"] += 1
                else:
                    stats["rates_pending"] += 1

    conn.commit()
    return stats


def flag_missing_plazas(conn: psycopg.Connection, found_tis_ids: list[str]) -> int:
    """
    Plazas that disappeared from TIS are flagged for review (never deleted).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE charging_point
            SET status = 'SUSPENDED'
            WHERE kind = 'PLAZA'
              AND tis_plaza_id IS NOT NULL
              AND NOT (tis_plaza_id = ANY(%s))
              AND status = 'ACTIVE'
            RETURNING id;
            """,
            (found_tis_ids,),
        )
        flagged = cur.fetchall()
        conn.commit()
        return len(flagged)
