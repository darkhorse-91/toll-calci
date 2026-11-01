import re
from typing import Optional, Tuple

import psycopg
from rapidfuzz import fuzz


def normalize_plaza_name(name: str) -> str:
    """Normalizes plaza name by removing punctuation, extra spaces, and common terms."""
    s = name.lower()
    s = re.sub(r"\b(toll|fee|plaza|fp|tp|barrier)\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def match_ihmcl_plaza(
    conn: psycopg.Connection,
    reported_name: str,
    state: str,
    auto_accept_threshold: float = 0.90,
) -> Tuple[Optional[int], float]:
    """
    Fuzzy-matches IHMCL reported name against known charging points in the same state.
    Auto-accepts if similarity > auto_accept_threshold (0.90).
    Stores results in stats_plaza_alias.
    """
    norm_rep = normalize_plaza_name(reported_name)

    with conn.cursor() as cur:
        # Check if already matched
        cur.execute(
            """
            SELECT charging_point_id, match_confidence
            FROM stats_plaza_alias
            WHERE source_name = 'IHMCL' AND reported_name = %s AND state = %s;
            """,
            (reported_name, state),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return row[0], float(row[1])

        # Fetch candidate plazas in the same state
        cur.execute(
            "SELECT id, name FROM charging_point WHERE kind = 'PLAZA' AND state = %s;",
            (state,),
        )
        candidates = cur.fetchall()

        best_id: Optional[int] = None
        best_ratio = 0.0

        for cid, cname in candidates:
            norm_c = normalize_plaza_name(cname)
            # Token sort ratio gives high fidelity matching for re-ordered tokens
            ratio = fuzz.token_sort_ratio(norm_rep, norm_c) / 100.0
            if ratio > best_ratio:
                best_ratio = ratio
                best_id = cid

        matched_id = best_id if best_ratio >= auto_accept_threshold else None

        # Upsert into stats_plaza_alias
        cur.execute(
            """
            INSERT INTO stats_plaza_alias (
                source_name, reported_name, state, charging_point_id, match_confidence
            )
            VALUES ('IHMCL', %s, %s, %s, %s)
            ON CONFLICT (source_name, reported_name, state)
            DO UPDATE SET charging_point_id = EXCLUDED.charging_point_id,
                          match_confidence = EXCLUDED.match_confidence;
            """,
            (reported_name, state, matched_id, round(best_ratio, 3)),
        )

        conn.commit()
        return matched_id, best_ratio


def refresh_materialized_stats(conn: psycopg.Connection) -> None:
    """Refreshes the plaza_fy_stats materialized view."""
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW plaza_fy_stats;")
    conn.commit()
