import hashlib
from typing import Optional, Tuple

import psycopg


def compute_sha256(content: bytes) -> str:
    """Computes the SHA-256 hex digest of raw binary content."""
    return hashlib.sha256(content).hexdigest()


def get_or_create_source_document(
    conn: psycopg.Connection,
    doc_type: str,
    url: str,
    content_bytes: bytes,
    reviewed_by: Optional[str] = None,
) -> Tuple[int, bool]:
    """
    Saves or retrieves a source_document by (url, sha256).
    Returns (id, is_new). If already loaded, returns existing ID and False.
    """
    digest = compute_sha256(content_bytes)

    with conn.cursor() as cur:
        # Check if already present
        cur.execute(
            "SELECT id FROM source_document WHERE url = %s AND sha256 = %s;",
            (url, digest),
        )
        row = cur.fetchone()
        if row:
            return row[0], False

        # Insert new record
        cur.execute(
            """
            INSERT INTO source_document (doc_type, url, sha256, reviewed_by, reviewed_at)
            VALUES (%s, %s, %s, %s, CASE WHEN %s IS NOT NULL THEN now() ELSE NULL END)
            RETURNING id;
            """,
            (doc_type, url, digest, reviewed_by, reviewed_by),
        )
        new_id = cur.fetchone()[0]
        return new_id, True
