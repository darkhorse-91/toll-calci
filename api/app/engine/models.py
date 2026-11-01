from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VehicleClassCode(str, Enum):
    CAR_JEEP_VAN = "CAR_JEEP_VAN"
    LCV = "LCV"
    BUS_TRUCK_2AXLE = "BUS_TRUCK_2AXLE"
    AXLE_3 = "AXLE_3"
    AXLE_4_6 = "AXLE_4_6"
    AXLE_7_PLUS = "AXLE_7_PLUS"


class JourneyType(str, Enum):
    ONE_WAY = "ONE_WAY"
    RETURN_24H = "RETURN_24H"


class PointKind(str, Enum):
    PLAZA = "PLAZA"
    CLOSED_SECTION = "CLOSED_SECTION"


class ReasonCode(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    STATE_ROAD = "STATE_ROAD"
    TRIPS_USED_UP = "TRIPS_USED_UP"
    RATE_MISSING = "RATE_MISSING"


class RouteLabel(str, Enum):
    USUAL = "USUAL"
    LOWEST_TOLL = "LOWEST_TOLL"
    TOLL_FREE = "TOLL_FREE"


class PassProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = "FASTAG_ANNUAL"
    financial_year: str = "FY2026-27"
    price_inr: Decimal = Field(default=Decimal("3075"))
    max_trips: int = 200
    validity_days: int = 365
    requires_non_commercial: bool = True


class PassInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool = False
    trips_left: Optional[int] = None


class VehicleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_class: VehicleClassCode = VehicleClassCode.CAR_JEEP_VAN
    commercial: bool = False


class PointWithRate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    kind: PointKind
    operator: str
    pass_accepted: bool
    position_on_route: float
    trip_units: int = 1
    amount_without_pass: Optional[Decimal] = None
    road: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    entry: Optional[str] = None
    exit: Optional[str] = None
    has_rate: bool = True


class PointResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    kind: PointKind
    operator: str
    road: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    entry: Optional[str] = None
    exit: Optional[str] = None
    amount_without_pass_inr: Optional[Decimal] = None
    amount_inr: Optional[Decimal] = None
    pass_applied: bool = False
    trips_used: int = 0
    reason: Optional[ReasonCode] = None


class PassSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    points_covered: int
    points_total: int
    trips_used: int
    trips_left_after: Optional[int] = None
    break_even_journeys: Optional[int] = None


class RouteTollResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    toll_with_pass_inr: Optional[Decimal] = None
    toll_without_pass_inr: Optional[Decimal] = None
    complete: bool = True
    pass_summary: PassSummary
    points: list[PointResult] = Field(default_factory=list)
