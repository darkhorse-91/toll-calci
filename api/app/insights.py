import math
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class RouteInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    text: str
    period: str
    source: str


def format_indian_number(n: float) -> str:
    """
    Format numbers using Indian numbering system (crore, lakh)
    rounded to two significant figures.
    1 crore = 10,000,000 (1e7)
    1 lakh = 100,000 (1e5)
    """
    if n <= 0:
        return "0"

    def round_sigfigs(val: float, sigfigs: int = 2) -> float:
        if val == 0:
            return 0
        return round(val, sigfigs - int(math.floor(math.log10(abs(val)))) - 1)

    if n >= 1e7:
        crores = round_sigfigs(n / 1e7, 2)
        crore_str = f"{crores:g}"
        return f"{crore_str} crore"
    elif n >= 1e5:
        lakhs = round_sigfigs(n / 1e5, 2)
        lakh_str = f"{lakhs:g}"
        return f"{lakh_str} lakh"
    else:
        return f"{round_sigfigs(n, 2):g}"


def compute_route_insights(
    point_count: int,
    distance_km: float,
    toll_without_pass_inr: Optional[Decimal],
    plaza_stats: list[dict[str, Any]],  # from plaza_fy_stats
    financial_year: str = "FY 2025-26",
) -> list[RouteInsight]:
    """
    Compute up to 4 route insights following the strict prompt rules:
    - At least half of points must have data for a fact to be included.
    - Format using Indian numbering (crore/lakh).
    - Source: IHMCL.
    """
    insights: list[RouteInsight] = []
    source_tag = "IHMCL"

    # Fact 1: Toll points count & toll per km
    if point_count > 0 and distance_km > 0 and toll_without_pass_inr is not None:
        rate_per_km = round(float(toll_without_pass_inr) / distance_km, 1)
        text = (
            f"{point_count} toll points over {round(distance_km)} km, about ₹{rate_per_km} per km."
        )
        insights.append(
            RouteInsight(
                key="toll_points",
                text=text,
                period=financial_year,
                source="Quote Calculation",
            )
        )

    if not plaza_stats or point_count == 0:
        return insights

    # Check if at least half of the points have data
    reported_points = len(plaza_stats)
    if reported_points < math.ceil(point_count / 2):
        return insights

    # Fact 2: Busiest plaza on the route
    stats_with_txns = [s for s in plaza_stats if s.get("fastag_txn_count") is not None]
    if stats_with_txns:
        busiest = max(stats_with_txns, key=lambda s: s["fastag_txn_count"])
        txn_str = format_indian_number(float(busiest["fastag_txn_count"]))
        name = busiest["name"]
        text = (
            f"Busiest plaza on this route: {name}, "
            f"about {txn_str} FASTag crossings in {financial_year}."
        )
        insights.append(
            RouteInsight(
                key="busiest_plaza",
                text=text,
                period=financial_year,
                source=source_tag,
            )
        )

    # Fact 3: FASTag toll collection
    total_val = sum(float(s.get("fastag_value_inr") or 0) for s in plaza_stats)
    if total_val > 0:
        val_str = format_indian_number(total_val)
        text = (
            f"Plazas on this route collected about ₹{val_str} through FASTag in {financial_year}."
        )
        insights.append(
            RouteInsight(
                key="collection",
                text=text,
                period=financial_year,
                source=source_tag,
            )
        )

    # Fact 4: Annual pass share (NH/NE points only)
    nh_stats = [s for s in plaza_stats if s.get("is_nh", True)]
    total_pass_txns = sum(int(s.get("annual_pass_txn_count") or 0) for s in nh_stats)
    total_car_txns = sum(int(s.get("car_txn_count") or 0) for s in nh_stats)

    if total_car_txns > 0 and total_pass_txns > 0:
        share = total_pass_txns / total_car_txns
        # Represent as "1 in N" or percentage
        ratio = round(1 / share) if share > 0 else 0
        if ratio > 1:
            share_text = (
                f"About 1 in {ratio} car crossings at these NH plazas used the annual pass."
            )
        else:
            pct = round(share * 100)
            share_text = f"About {pct}% of car crossings at these NH plazas used the annual pass."

        insights.append(
            RouteInsight(
                key="pass_share",
                text=share_text,
                period=financial_year,
                source=source_tag,
            )
        )

    return insights
