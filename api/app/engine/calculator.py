import math
from decimal import Decimal
from typing import Optional, Sequence

from .models import (
    JourneyType,
    PassInput,
    PassProduct,
    PassSummary,
    PointResult,
    PointWithRate,
    ReasonCode,
    RouteTollResult,
    VehicleClassCode,
    VehicleInput,
)


def is_vehicle_eligible_for_pass(vehicle: VehicleInput) -> bool:
    """Non-commercial CAR_JEEP_VAN is the only eligible class."""
    return vehicle.vehicle_class == VehicleClassCode.CAR_JEEP_VAN and not vehicle.commercial


def order_and_merge_points(
    plazas: Sequence[PointWithRate],
    closed_sections: Sequence[PointWithRate],
) -> list[PointWithRate]:
    """Merges open plazas and closed sections sorted by position_on_route."""
    combined = list(plazas) + list(closed_sections)
    return sorted(combined, key=lambda p: p.position_on_route)


def calculate_route_tolls(
    points: Sequence[PointWithRate],
    vehicle: VehicleInput,
    journey: JourneyType,
    pass_input: PassInput,
    pass_product: Optional[PassProduct] = None,
) -> RouteTollResult:
    """
    Pure deterministic engine calculating exact tolls, pass coverage,
    and break-even trips along the route in travel order.
    No database, clock, or network calls.
    """
    if pass_product is None:
        pass_product = PassProduct()

    eligible = is_vehicle_eligible_for_pass(vehicle)
    trip_multiplier = 2 if journey == JourneyType.RETURN_24H else 1

    current_trips_left: Optional[int] = pass_input.trips_left if pass_input.active else None
    total_trips_used = 0
    points_covered = 0
    points_total = len(points)
    complete = True

    toll_without_pass_total = Decimal("0")
    toll_with_pass_total = Decimal("0")
    has_missing_rate = False

    point_results: list[PointResult] = []

    for pt in points:
        # Check for missing rate
        if not pt.has_rate or pt.amount_without_pass is None:
            has_missing_rate = True
            complete = False
            point_results.append(
                PointResult(
                    id=pt.id,
                    name=pt.name,
                    kind=pt.kind,
                    operator=pt.operator,
                    road=pt.road,
                    lat=pt.lat,
                    lng=pt.lng,
                    entry=pt.entry,
                    exit=pt.exit,
                    amount_without_pass_inr=None,
                    amount_inr=None,
                    pass_applied=False,
                    trips_used=0,
                    reason=ReasonCode.RATE_MISSING,
                )
            )
            continue

        raw_fare = pt.amount_without_pass
        toll_without_pass_total += raw_fare
        trips_needed = pt.trip_units * trip_multiplier

        # Case 1: Pass is active
        if pass_input.active:
            if not eligible:
                point_results.append(
                    PointResult(
                        id=pt.id,
                        name=pt.name,
                        kind=pt.kind,
                        operator=pt.operator,
                        road=pt.road,
                        lat=pt.lat,
                        lng=pt.lng,
                        entry=pt.entry,
                        exit=pt.exit,
                        amount_without_pass_inr=raw_fare,
                        amount_inr=raw_fare,
                        pass_applied=False,
                        trips_used=0,
                        reason=ReasonCode.NOT_ELIGIBLE,
                    )
                )
                toll_with_pass_total += raw_fare
            elif not pt.pass_accepted:
                point_results.append(
                    PointResult(
                        id=pt.id,
                        name=pt.name,
                        kind=pt.kind,
                        operator=pt.operator,
                        road=pt.road,
                        lat=pt.lat,
                        lng=pt.lng,
                        entry=pt.entry,
                        exit=pt.exit,
                        amount_without_pass_inr=raw_fare,
                        amount_inr=raw_fare,
                        pass_applied=False,
                        trips_used=0,
                        reason=ReasonCode.STATE_ROAD,
                    )
                )
                toll_with_pass_total += raw_fare
            elif current_trips_left is not None and current_trips_left < trips_needed:
                point_results.append(
                    PointResult(
                        id=pt.id,
                        name=pt.name,
                        kind=pt.kind,
                        operator=pt.operator,
                        road=pt.road,
                        lat=pt.lat,
                        lng=pt.lng,
                        entry=pt.entry,
                        exit=pt.exit,
                        amount_without_pass_inr=raw_fare,
                        amount_inr=raw_fare,
                        pass_applied=False,
                        trips_used=0,
                        reason=ReasonCode.TRIPS_USED_UP,
                    )
                )
                toll_with_pass_total += raw_fare
            else:
                # Pass accepted and covered
                point_results.append(
                    PointResult(
                        id=pt.id,
                        name=pt.name,
                        kind=pt.kind,
                        operator=pt.operator,
                        road=pt.road,
                        lat=pt.lat,
                        lng=pt.lng,
                        entry=pt.entry,
                        exit=pt.exit,
                        amount_without_pass_inr=raw_fare,
                        amount_inr=Decimal("0"),
                        pass_applied=True,
                        trips_used=trips_needed,
                        reason=None,
                    )
                )
                points_covered += 1
                total_trips_used += trips_needed
                if current_trips_left is not None:
                    current_trips_left -= trips_needed
                # toll_with_pass_total += 0

        # Case 2: Pass is NOT active
        else:
            point_results.append(
                PointResult(
                    id=pt.id,
                    name=pt.name,
                    kind=pt.kind,
                    operator=pt.operator,
                    road=pt.road,
                    lat=pt.lat,
                    lng=pt.lng,
                    entry=pt.entry,
                    exit=pt.exit,
                    amount_without_pass_inr=raw_fare,
                    amount_inr=raw_fare,
                    pass_applied=False,
                    trips_used=0,
                    reason=None,
                )
            )
            toll_with_pass_total += raw_fare

    # Calculate break-even journeys if user has no pass and vehicle is eligible
    break_even_journeys: Optional[int] = None
    if not pass_input.active and eligible and not has_missing_rate:
        # Simulate hypothetical toll with pass assuming unlimited trips
        hypothetical_toll_with_pass = Decimal("0")
        for pt in points:
            if pt.amount_without_pass is not None:
                if not pt.pass_accepted:
                    hypothetical_toll_with_pass += pt.amount_without_pass

        savings = toll_without_pass_total - hypothetical_toll_with_pass
        if savings > Decimal("0"):
            break_even_journeys = math.ceil(pass_product.price_inr / savings)

    pass_summary = PassSummary(
        eligible=eligible,
        points_covered=points_covered,
        points_total=points_total,
        trips_used=total_trips_used,
        trips_left_after=current_trips_left,
        break_even_journeys=break_even_journeys,
    )

    final_toll_with_pass = None if has_missing_rate else toll_with_pass_total
    final_toll_without_pass = None if has_missing_rate else toll_without_pass_total

    return RouteTollResult(
        toll_with_pass_inr=final_toll_with_pass,
        toll_without_pass_inr=final_toll_without_pass,
        complete=complete,
        pass_summary=pass_summary,
        points=point_results,
    )
