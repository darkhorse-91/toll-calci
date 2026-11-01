import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Template

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/toll_mvp")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-in-production-toll-admin")

security = HTTPBasic()
admin_router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> bool:
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


ADMIN_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Toll Engine Admin Review</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem;
           background: #EEF0EC; color: #1E2124; }
    .wrap { max-width: 1000px; margin: 0 auto; background: #fff; padding: 2rem;
            border-radius: 8px; border: 1px solid #c9ccc4; }
    h1, h2 { color: #0B6B3A; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; font-size: 0.95rem; }
    th, td { padding: 0.6rem 0.8rem; border-bottom: 1px solid #c9ccc4; text-align: left; }
    th { background: #DDE3DA; }
    .badge-pending { background: #F2C200; padding: 2px 6px; border-radius: 3px; font-weight: bold; }
    button { cursor: pointer; padding: 0.35rem 0.75rem; border-radius: 4px;
             border: none; font-weight: bold; }
    .btn-approve { background: #0B6B3A; color: #fff; }
    .btn-reject { background: #B3261E; color: #fff; margin-left: 0.4rem; }
    .source-link { color: #0B6B3A; text-decoration: underline; font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Toll Engine Data Review</h1>
    <p>Logged in as administrator. Review new scraped rates and unmatched plaza aliases.</p>

    <h2>Pending Rates for Review ({{ pending_rates|length }})</h2>
    {% if pending_rates %}
    <table>
      <thead>
        <tr>
          <th>Plaza / Section</th>
          <th>Class</th>
          <th>Journey</th>
          <th>Effective</th>
          <th>Old Fare</th>
          <th>New Fare</th>
          <th>Source</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        {% for r in pending_rates %}
        <tr>
          <td><b>{{ r.plaza_name }}</b></td>
          <td>{{ r.vehicle_class }}</td>
          <td>{{ r.journey }}</td>
          <td>{{ r.effective_from }}</td>
          <td>{% if r.old_amount %}₹{{ r.old_amount }}{% else %}<i>None (New)</i>{% endif %}</td>
          <td><b style="color: #0B6B3A;">₹{{ r.amount_inr }}</b></td>
          <td><a class="source-link" href="{{ r.source_url }}" target="_blank">Evidence</a></td>
          <td>
            <form style="display:inline;" method="post" action="/admin/rate/{{ r.id }}/approve">
              <button type="submit" class="btn-approve">Approve</button>
            </form>
            <form style="display:inline;" method="post" action="/admin/rate/{{ r.id }}/reject">
              <button type="submit" class="btn-reject">Reject</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p><i>No pending rates waiting for review. All rates are approved.</i></p>
    {% endif %}

    <h2>Unmatched Plaza Aliases ({{ unmatched_aliases|length }})</h2>
    {% if unmatched_aliases %}
    <table>
      <thead>
        <tr>
          <th>Reported Name</th>
          <th>State</th>
          <th>Confidence</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        {% for a in unmatched_aliases %}
        <tr>
          <td><b>{{ a.reported_name }}</b></td>
          <td>{{ a.state }}</td>
          <td>{{ a.match_confidence }}</td>
          <td>
            <small><i>Needs manual ID mapping</i></small>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p><i>All plaza aliases are matched.</i></p>
    {% endif %}
  </div>
</body>
</html>
"""


@admin_router.get("", response_class=HTMLResponse)
async def admin_dashboard(is_authed: bool = Depends(verify_admin)) -> HTMLResponse:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, cp.name AS plaza_name, vc.name AS vehicle_class,
                       r.journey, r.amount_inr, r.effective_from,
                       s.url AS source_url,
                       (
                         SELECT prev.amount_inr
                         FROM rate prev
                         WHERE prev.charging_point_id = r.charging_point_id
                           AND prev.vehicle_class_id = r.vehicle_class_id
                           AND prev.journey = r.journey
                           AND prev.status = 'APPROVED'
                           AND prev.effective_from < r.effective_from
                         ORDER BY prev.effective_from DESC
                         LIMIT 1
                       ) AS old_amount
                FROM rate r
                JOIN charging_point cp ON cp.id = r.charging_point_id
                JOIN vehicle_class vc ON vc.id = r.vehicle_class_id
                JOIN source_document s ON s.id = r.source_document_id
                WHERE r.status = 'PENDING'
                ORDER BY r.id DESC;
            """)
            pending_rates = cur.fetchall()

            cur.execute("""
                SELECT reported_name, state, match_confidence
                FROM stats_plaza_alias
                WHERE charging_point_id IS NULL
                ORDER BY match_confidence DESC;
            """)
            unmatched = cur.fetchall()

    template = Template(ADMIN_PAGE_TEMPLATE)
    html_content = template.render(
        pending_rates=pending_rates,
        unmatched_aliases=unmatched,
    )
    return HTMLResponse(content=html_content)


@admin_router.post("/rate/{rate_id}/approve")
async def approve_rate(
    rate_id: int,
    is_authed: bool = Depends(verify_admin),
) -> RedirectResponse:
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # 1. Fetch the rate
            cur.execute(
                """
                SELECT charging_point_id, entry_interchange_id, exit_interchange_id,
                       vehicle_class_id, journey, effective_from
                FROM rate
                WHERE id = %s AND status = 'PENDING';
                """,
                (rate_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Pending rate not found")

            c_id, entry_id, exit_id, vc_id, journey, eff_from = row

            # 2. Close out the previous approved rate to prevent exclusion constraint violation
            cur.execute(
                """
                UPDATE rate
                SET effective_to = (%s::date - interval '1 day')::date
                WHERE charging_point_id = %s
                  AND coalesce(entry_interchange_id, 0) = coalesce(%s, 0)
                  AND coalesce(exit_interchange_id, 0) = coalesce(%s, 0)
                  AND vehicle_class_id = %s
                  AND journey = %s::journey_type
                  AND status = 'APPROVED'
                  AND effective_from < %s::date
                  AND (effective_to IS NULL OR effective_to >= %s::date);
                """,
                (eff_from, c_id, entry_id, exit_id, vc_id, journey, eff_from, eff_from),
            )

            # 3. Approve the new rate
            cur.execute(
                "UPDATE rate SET status = 'APPROVED' WHERE id = %s;",
                (rate_id,),
            )
            conn.commit()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/rate/{rate_id}/reject")
async def reject_rate(
    rate_id: int,
    is_authed: bool = Depends(verify_admin),
) -> RedirectResponse:
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rate SET status = 'REJECTED' WHERE id = %s;",
                (rate_id,),
            )
            conn.commit()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
