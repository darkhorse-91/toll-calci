from decimal import Decimal

import pytest

from api.app.engine import (
    JourneyType,
    PassInput,
    PassProduct,
    PointKind,
    PointWithRate,
    ReasonCode,
    VehicleClassCode,
    VehicleInput,
    calculate_route_tolls,
    is_vehicle_eligible_for_pass,
    order_and_merge_points,
)


@pytest.fixture
def sample_pass_product() -> PassProduct:
    return PassProduct(
        code="FASTAG_ANNUAL",
        financial_year="FY2026-27",
        price_inr=Decimal("3075"),
        max_trips=200,
        validity_days=365,
    )


def test_vehicle_eligibility():
    # Non-commercial car is eligible
    car_private = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    assert is_vehicle_eligible_for_pass(car_private) is True

    # Commercial car is not eligible
    car_commercial = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=True)
    assert is_vehicle_eligible_for_pass(car_commercial) is False

    # Other classes are not eligible
    lcv = VehicleInput(vehicle_class=VehicleClassCode.LCV, commercial=False)
    assert is_vehicle_eligible_for_pass(lcv) is False

    truck = VehicleInput(vehicle_class=VehicleClassCode.BUS_TRUCK_2AXLE, commercial=False)
    assert is_vehicle_eligible_for_pass(truck) is False


def test_order_and_merge_points():
    p1 = PointWithRate(
        id=1,
        name="Plaza 1",
        kind=PointKind.PLAZA,
        operator="NHAI",
        pass_accepted=True,
        position_on_route=0.8,
        amount_without_pass=Decimal("100"),
    )
    p2 = PointWithRate(
        id=2,
        name="Expressway",
        kind=PointKind.CLOSED_SECTION,
        operator="UPEIDA",
        pass_accepted=False,
        position_on_route=0.3,
        amount_without_pass=Decimal("500"),
    )
    p3 = PointWithRate(
        id=3,
        name="Plaza 0",
        kind=PointKind.PLAZA,
        operator="NHAI",
        pass_accepted=True,
        position_on_route=0.1,
        amount_without_pass=Decimal("50"),
    )

    ordered = order_and_merge_points([p1, p3], [p2])
    assert [p.id for p in ordered] == [3, 2, 1]


def test_no_pass_eligible_vehicle_break_even(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.2,
            amount_without_pass=Decimal("150"),
        ),
        PointWithRate(
            id=102,
            name="NH Plaza 2",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.6,
            amount_without_pass=Decimal("200"),
        ),
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    journey = JourneyType.ONE_WAY
    pass_input = PassInput(active=False)

    res = calculate_route_tolls(points, vehicle, journey, pass_input, sample_pass_product)

    assert res.complete is True
    assert res.toll_without_pass_inr == Decimal("350")
    assert res.toll_with_pass_inr == Decimal("350")
    assert res.pass_summary.eligible is True
    assert res.pass_summary.points_covered == 0
    assert res.pass_summary.trips_used == 0

    # Break-even: savings per trip = 350. ₹3,075 / 350 = 8.78 -> 9 journeys
    assert res.pass_summary.break_even_journeys == 9
    for pt in res.points:
        assert pt.pass_applied is False
        assert pt.reason is None


def test_no_pass_zero_savings_gives_no_break_even(sample_pass_product):
    # Route only on State Expressway where pass is not accepted
    points = [
        PointWithRate(
            id=201,
            name="Agra-Lucknow Expressway",
            kind=PointKind.CLOSED_SECTION,
            operator="UPEIDA",
            pass_accepted=False,
            position_on_route=0.5,
            amount_without_pass=Decimal("655"),
        )
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=False)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.toll_without_pass_inr == Decimal("655")
    assert res.toll_with_pass_inr == Decimal("655")
    assert res.pass_summary.break_even_journeys is None  # Saving is 0


def test_commercial_car_not_eligible(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.5,
            amount_without_pass=Decimal("150"),
        )
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=True)
    pass_input = PassInput(active=True, trips_left=50)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.pass_summary.eligible is False
    assert res.pass_summary.points_covered == 0
    assert res.toll_with_pass_inr == Decimal("150")
    assert res.points[0].pass_applied is False
    assert res.points[0].reason == ReasonCode.NOT_ELIGIBLE
    assert res.points[0].amount_inr == Decimal("150")


def test_pass_all_nh_route(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.3,
            amount_without_pass=Decimal("120"),
        ),
        PointWithRate(
            id=102,
            name="Plaza 2",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.7,
            amount_without_pass=Decimal("180"),
        ),
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=100)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.toll_without_pass_inr == Decimal("300")
    assert res.toll_with_pass_inr == Decimal("0")
    assert res.pass_summary.points_covered == 2
    assert res.pass_summary.trips_used == 2
    assert res.pass_summary.trips_left_after == 98
    for pt in res.points:
        assert pt.pass_applied is True
        assert pt.amount_inr == Decimal("0")
        assert pt.reason is None


def test_mixed_nh_and_state_route(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.2,
            amount_without_pass=Decimal("100"),
        ),
        PointWithRate(
            id=201,
            name="UP Expressway",
            kind=PointKind.CLOSED_SECTION,
            operator="UPEIDA",
            pass_accepted=False,
            position_on_route=0.5,
            amount_without_pass=Decimal("640"),
        ),
        PointWithRate(
            id=102,
            name="NH Plaza 2",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.8,
            amount_without_pass=Decimal("150"),
        ),
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=50)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.toll_without_pass_inr == Decimal("890")
    assert res.toll_with_pass_inr == Decimal("640")
    assert res.pass_summary.points_covered == 2
    assert res.pass_summary.trips_used == 2
    assert res.pass_summary.trips_left_after == 48

    assert res.points[0].pass_applied is True
    assert res.points[0].amount_inr == Decimal("0")

    assert res.points[1].pass_applied is False
    assert res.points[1].reason == ReasonCode.STATE_ROAD
    assert res.points[1].amount_inr == Decimal("640")

    assert res.points[2].pass_applied is True
    assert res.points[2].amount_inr == Decimal("0")


def test_trips_run_out_midway(sample_pass_product):
    # User has 1 trip left, but route has 2 NH plazas
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.2,
            amount_without_pass=Decimal("100"),
        ),
        PointWithRate(
            id=102,
            name="NH Plaza 2",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.8,
            amount_without_pass=Decimal("150"),
        ),
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=1)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.toll_without_pass_inr == Decimal("250")
    assert res.toll_with_pass_inr == Decimal("150")
    assert res.pass_summary.points_covered == 1
    assert res.pass_summary.trips_used == 1
    assert res.pass_summary.trips_left_after == 0

    # Plaza 1 covered
    assert res.points[0].pass_applied is True
    assert res.points[0].amount_inr == Decimal("0")
    assert res.points[0].reason is None

    # Plaza 2 exhausted
    assert res.points[1].pass_applied is False
    assert res.points[1].amount_inr == Decimal("150")
    assert res.points[1].reason == ReasonCode.TRIPS_USED_UP


def test_return_journey_doubles_trips(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.5,
            amount_without_pass=Decimal("150"),
            trip_units=1,
        )
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=10)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.RETURN_24H, pass_input, sample_pass_product
    )

    # 1 passage * 2 for return = 2 trips used
    assert res.pass_summary.trips_used == 2
    assert res.pass_summary.trips_left_after == 8
    assert res.points[0].trips_used == 2
    assert res.points[0].amount_inr == Decimal("0")


def test_closed_section_trip_counting(sample_pass_product):
    # A closed section on NH/NE (e.g. Vadodara-Mumbai expressway NHAI) counts as 1 trip
    points = [
        PointWithRate(
            id=202,
            name="NE Expressway",
            kind=PointKind.CLOSED_SECTION,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.5,
            amount_without_pass=Decimal("300"),
            trip_units=1,
        )
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=10)

    # One way
    res_one_way = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )
    assert res_one_way.pass_summary.trips_used == 1
    assert res_one_way.pass_summary.trips_left_after == 9

    # Return
    res_return = calculate_route_tolls(
        points, vehicle, JourneyType.RETURN_24H, pass_input, sample_pass_product
    )
    assert res_return.pass_summary.trips_used == 2
    assert res_return.pass_summary.trips_left_after == 8


def test_pass_with_no_trips_left_specified(sample_pass_product):
    # User checked active pass but did not provide trips_left
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.5,
            amount_without_pass=Decimal("100"),
            trip_units=1,
        )
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=None)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )
    assert res.pass_summary.points_covered == 1
    assert res.pass_summary.trips_used == 1
    assert res.pass_summary.trips_left_after is None  # Still None (assumed plenty)
    assert res.toll_with_pass_inr == Decimal("0")


def test_rate_missing_sets_incomplete(sample_pass_product):
    points = [
        PointWithRate(
            id=101,
            name="NH Plaza 1",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.2,
            amount_without_pass=Decimal("100"),
        ),
        PointWithRate(
            id=102,
            name="Unrated Plaza",
            kind=PointKind.PLAZA,
            operator="NHAI",
            pass_accepted=True,
            position_on_route=0.5,
            amount_without_pass=None,
            has_rate=False,
        ),
    ]
    vehicle = VehicleInput(vehicle_class=VehicleClassCode.CAR_JEEP_VAN, commercial=False)
    pass_input = PassInput(active=True, trips_left=50)

    res = calculate_route_tolls(
        points, vehicle, JourneyType.ONE_WAY, pass_input, sample_pass_product
    )

    assert res.complete is False
    assert res.toll_with_pass_inr is None
    assert res.toll_without_pass_inr is None

    assert res.points[1].amount_inr is None
    assert res.points[1].amount_without_pass_inr is None
    assert res.points[1].pass_applied is False
    assert res.points[1].reason == ReasonCode.RATE_MISSING
