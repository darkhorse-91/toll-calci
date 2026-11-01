import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field

from .admin import admin_router
from .clients.photon import PhotonClient, PlaceItem
from .clients.valhalla import ValhallaClient
from .engine import (
    JourneyType,
    PassInput,
    PassProduct,
    PointKind,
    PointWithRate,
    RouteLabel,
    VehicleClassCode,
    VehicleInput,
    calculate_route_tolls,
    order_and_merge_points,
)
from .insights import RouteInsight, compute_route_insights

# Environment Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/toll_mvp")
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")
PHOTON_URL = os.getenv("PHOTON_URL", "http://localhost:2322")

# Structured JSON Logger
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
logger = logging.getLogger("quote_api")


class StructuredQuoteLog(BaseModel):
    timestamp: float
    request_id: str
    from_coord: list[float]  # clamped to 2 decimals
    to_coord: list[float]  # clamped to 2 decimals
    vehicle_class: str
    route_count: int
    total_points: int
    valhalla_duration_ms: float
    db_duration_ms: float
    total_duration_ms: float


# Global clients & connection pool
db_pool: Optional[AsyncConnectionPool] = None
photon_client = PhotonClient(base_url=PHOTON_URL)
valhalla_client = ValhallaClient(base_url=VALHALLA_URL)


async def get_db_pool() -> AsyncConnectionPool:
    global db_pool
    if db_pool is None:
        db_pool = AsyncConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10, open=False)
        await db_pool.open()
    return db_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global db_pool
    db_pool = AsyncConnectionPool(conninfo=DATABASE_URL, min_size=2, max_size=10, open=False)
    try:
        await db_pool.open()
    except Exception as e:
        logger.warning(json.dumps({"event": "db_pool_init_warning", "detail": str(e)}))
    yield
    if db_pool:
        await db_pool.close()


app = FastAPI(title="India Toll Price MVP Quote API", lifespan=lifespan)
app.include_router(admin_router)


# Custom Error Envelope Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": {"code": "INVALID_INPUT", "message": str(exc)}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "INTERNAL_ERROR"
    if exc.status_code == 400:
        code = "INVALID_INPUT"
    elif exc.status_code == 422:
        code = "NO_ROUTE"
    elif exc.status_code == 503:
        code = "UPSTREAM_UNAVAILABLE"

    msg = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": msg}},
    )


# Health Endpoints
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    db_ok = False
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1;")
                db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ready" if db_ok else "not_ready",
        "database": db_ok,
    }


# Request & Response Models for /v1/quote
class LatLng(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lng: float


class AnnualPassQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool = False
    trips_left: Optional[int] = None


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_location: LatLng = Field(alias="from")
    to_location: LatLng = Field(alias="to")
    vehicle_class: VehicleClassCode = VehicleClassCode.CAR_JEEP_VAN
    commercial: bool = False
    journey: JourneyType = JourneyType.ONE_WAY
    travel_date: Optional[date] = None
    annual_pass: Optional[AnnualPassQuoteInput] = None


class PassProductResponse(BaseModel):
    financial_year: str
    price_inr: int
    max_trips: int


class PassResultResponse(BaseModel):
    eligible: bool
    points_covered: int
    points_total: int
    trips_used: int
    trips_left_after: Optional[int]
    break_even_journeys: Optional[int]


class PointResponse(BaseModel):
    id: int
    name: str
    kind: PointKind
    operator: str
    road: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    entry: Optional[str] = None
    exit: Optional[str] = None
    amount_without_pass_inr: Optional[int] = None
    amount_inr: Optional[int] = None
    pass_applied: bool
    trips_used: int
    reason: Optional[str] = None


class GeoJSONGeometry(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    label: RouteLabel
    distance_km: float
    est_duration_min: float
    geometry: GeoJSONGeometry
    toll_with_pass_inr: Optional[int]
    toll_without_pass_inr: Optional[int]
    complete: bool
    pass_info: PassResultResponse = Field(alias="pass")
    points: list[PointResponse]
    insights: list[RouteInsight]


class QuoteResponse(BaseModel):
    rates_as_of: str
    pass_product: PassProductResponse
    routes: list[RouteResponse]


# Places Proxy Endpoint
@app.get("/v1/places", response_model=list[PlaceItem])
async def search_places(q: str = Query(..., min_length=2), limit: int = 5) -> list[PlaceItem]:
    try:
        return await photon_client.search(q, limit=limit)
    except Exception as e:
        logger.error(f"Photon search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Place search upstream unavailable",
        ) from e


# Quote Endpoint
@app.post("/v1/quote", response_model=QuoteResponse)
async def get_quote(req: QuoteRequest) -> QuoteResponse:
    start_time = time.perf_counter()
    req_travel_date = req.travel_date or date.today()
    from_pt = (req.from_location.lat, req.from_location.lng)
    to_pt = (req.to_location.lat, req.to_location.lng)

    # 1. Fetch Valhalla Routes
    valhalla_start = time.perf_counter()
    try:
        valhalla_routes = await valhalla_client.get_route(
            from_coord=from_pt,
            to_coord=to_pt,
            use_tolls=1.0,
            alternates=1,
        )
    except Exception as e:
        logger.error(f"Valhalla route error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing upstream unavailable",
        ) from e

    valhalla_duration = (time.perf_counter() - valhalla_start) * 1000

    if not valhalla_routes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No route found between coordinates",
        )

    # 2. Database lookups for each route
    db_start = time.perf_counter()
    try:
        pool = await get_db_pool()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection pool unavailable: {e}",
        ) from e

    response_routes: list[RouteResponse] = []
    total_points_matched = 0

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # Fetch active pass_product
            await cur.execute(
                """
                SELECT financial_year, price_inr, max_trips
                FROM pass_product
                WHERE %s::date BETWEEN on_sale_from AND coalesce(on_sale_to, '9999-12-31'::date)
                LIMIT 1;
            """,
                (req_travel_date,),
            )
            p_row = await cur.fetchone()
            if p_row:
                pass_prod = PassProduct(
                    financial_year=p_row[0],
                    price_inr=p_row[1],
                    max_trips=p_row[2],
                )
            else:
                pass_prod = PassProduct()

            for idx, r in enumerate(valhalla_routes):
                label = RouteLabel.USUAL if idx == 0 else RouteLabel.LOWEST_TOLL
                route_geojson = json.dumps({"type": "LineString", "coordinates": r.coordinates})

                # A. Find open plazas on route
                await cur.execute(
                    """
                    SELECT cp.id, cp.name, cp.road_bearing_deg, o.code, r.ref,
                           ST_Y(cp.geom) as lat, ST_X(cp.geom) as lng, pos.position_on_route
                    FROM plazas_on_route(%s::text, 50) pos
                    JOIN charging_point cp ON cp.id = pos.charging_point_id
                    JOIN operator o ON o.id = cp.operator_id
                    LEFT JOIN road r ON r.id = cp.road_id
                    ORDER BY pos.position_on_route;
                """,
                    (route_geojson,),
                )
                plaza_rows = await cur.fetchall()

                # B. Find closed sections on route
                await cur.execute(
                    """
                    SELECT cp.id, cp.name, o.code, r.ref,
                           cs.entry_interchange_id, cs.exit_interchange_id,
                           i1.name AS entry_name, i2.name AS exit_name,
                           cs.position_on_route
                    FROM closed_sections_on_route(%s::text, 100) cs
                    JOIN charging_point cp ON cp.id = cs.charging_point_id
                    JOIN operator o ON o.id = cp.operator_id
                    LEFT JOIN road r ON r.id = cp.road_id
                    JOIN interchange i1 ON i1.id = cs.entry_interchange_id
                    JOIN interchange i2 ON i2.id = cs.exit_interchange_id
                    ORDER BY cs.position_on_route;
                """,
                    (route_geojson,),
                )
                closed_rows = await cur.fetchall()

                # C. Build PointWithRate items
                raw_points: list[PointWithRate] = []

                # Plazas
                for prow in plaza_rows:
                    pid, pname, _, op_code, road_ref, lat, lng, pos = prow
                    # Get rate
                    await cur.execute(
                        """
                        SELECT amount_inr, pass_accepted, trip_units
                        FROM rate_for(
                            %s::int, NULL::int, NULL::int,
                            (SELECT id FROM vehicle_class WHERE code = %s::text)::smallint,
                            %s::journey_type, %s::date
                        );
                    """,
                        (pid, req.vehicle_class.value, req.journey.value, req_travel_date),
                    )
                    rate_row = await cur.fetchone()

                    if rate_row:
                        amount, pass_acc, trips = rate_row
                        raw_points.append(
                            PointWithRate(
                                id=pid,
                                name=pname,
                                kind=PointKind.PLAZA,
                                operator=op_code,
                                road=road_ref,
                                lat=lat,
                                lng=lng,
                                position_on_route=pos,
                                pass_accepted=pass_acc,
                                trip_units=trips,
                                amount_without_pass=amount,
                                has_rate=True,
                            )
                        )
                    else:
                        # Missing rate
                        raw_points.append(
                            PointWithRate(
                                id=pid,
                                name=pname,
                                kind=PointKind.PLAZA,
                                operator=op_code,
                                road=road_ref,
                                lat=lat,
                                lng=lng,
                                position_on_route=pos,
                                pass_accepted=False,
                                trip_units=1,
                                amount_without_pass=None,
                                has_rate=False,
                            )
                        )

                # Closed sections
                for crow in closed_rows:
                    cid, cname, op_code, road_ref, e_id, x_id, e_name, x_name, pos = crow
                    await cur.execute(
                        """
                        SELECT amount_inr, pass_accepted, trip_units
                        FROM rate_for(
                            %s::int, %s::int, %s::int,
                            (SELECT id FROM vehicle_class WHERE code = %s::text)::smallint,
                            %s::journey_type, %s::date
                        );
                    """,
                        (
                            cid,
                            e_id,
                            x_id,
                            req.vehicle_class.value,
                            req.journey.value,
                            req_travel_date,
                        ),
                    )
                    rate_row = await cur.fetchone()

                    if rate_row:
                        amount, pass_acc, trips = rate_row
                        raw_points.append(
                            PointWithRate(
                                id=cid,
                                name=cname,
                                kind=PointKind.CLOSED_SECTION,
                                operator=op_code,
                                road=road_ref,
                                entry=e_name,
                                exit=x_name,
                                position_on_route=pos,
                                pass_accepted=pass_acc,
                                trip_units=trips,
                                amount_without_pass=amount,
                                has_rate=True,
                            )
                        )
                    else:
                        raw_points.append(
                            PointWithRate(
                                id=cid,
                                name=cname,
                                kind=PointKind.CLOSED_SECTION,
                                operator=op_code,
                                road=road_ref,
                                entry=e_name,
                                exit=x_name,
                                position_on_route=pos,
                                pass_accepted=False,
                                trip_units=1,
                                amount_without_pass=None,
                                has_rate=False,
                            )
                        )

                # Sort along travel order
                ordered_points = order_and_merge_points(
                    [p for p in raw_points if p.kind == PointKind.PLAZA],
                    [p for p in raw_points if p.kind == PointKind.CLOSED_SECTION],
                )
                total_points_matched += len(ordered_points)

                # D. Run Pure Calculation Engine
                pass_in = PassInput(
                    active=req.annual_pass.active if req.annual_pass else False,
                    trips_left=req.annual_pass.trips_left if req.annual_pass else None,
                )
                veh_in = VehicleInput(
                    vehicle_class=req.vehicle_class,
                    commercial=req.commercial,
                )
                calc_result = calculate_route_tolls(
                    points=ordered_points,
                    vehicle=veh_in,
                    journey=req.journey,
                    pass_input=pass_in,
                    pass_product=pass_prod,
                )

                # E. Fetch stats for route insights
                pt_ids = [pt.id for pt in ordered_points]
                stats_rows = []
                if pt_ids:
                    await cur.execute(
                        """
                        SELECT s.charging_point_id, cp.name, s.fastag_txn_count, s.fastag_value_inr,
                               s.car_txn_count, s.annual_pass_txn_count, o.pass_accepted AS is_nh
                        FROM plaza_fy_stats s
                        JOIN charging_point cp ON cp.id = s.charging_point_id
                        JOIN operator o ON o.id = cp.operator_id
                        WHERE s.charging_point_id = ANY(%s);
                    """,
                        (pt_ids,),
                    )
                    stats_records = await cur.fetchall()
                    for srec in stats_records:
                        stats_rows.append(
                            {
                                "charging_point_id": srec[0],
                                "name": srec[1],
                                "fastag_txn_count": srec[2],
                                "fastag_value_inr": srec[3],
                                "car_txn_count": srec[4],
                                "annual_pass_txn_count": srec[5],
                                "is_nh": srec[6],
                            }
                        )

                insights = compute_route_insights(
                    point_count=len(ordered_points),
                    distance_km=r.distance_km,
                    toll_without_pass_inr=calc_result.toll_without_pass_inr,
                    plaza_stats=stats_rows,
                )

                # Format Point responses (whole rupees half-up)
                point_res_list: list[PointResponse] = []
                for pt in calc_result.points:
                    w_pass = round(float(pt.amount_inr)) if pt.amount_inr is not None else None
                    wo_pass = (
                        round(float(pt.amount_without_pass_inr))
                        if pt.amount_without_pass_inr is not None
                        else None
                    )
                    point_res_list.append(
                        PointResponse(
                            id=pt.id,
                            name=pt.name,
                            kind=pt.kind,
                            operator=pt.operator,
                            road=pt.road,
                            lat=pt.lat,
                            lng=pt.lng,
                            entry=pt.entry,
                            exit=pt.exit,
                            amount_without_pass_inr=wo_pass,
                            amount_inr=w_pass,
                            pass_applied=pt.pass_applied,
                            trips_used=pt.trips_used,
                            reason=pt.reason.value if pt.reason else None,
                        )
                    )

                w_total = (
                    round(float(calc_result.toll_with_pass_inr))
                    if calc_result.toll_with_pass_inr is not None
                    else None
                )
                wo_total = (
                    round(float(calc_result.toll_without_pass_inr))
                    if calc_result.toll_without_pass_inr is not None
                    else None
                )

                response_routes.append(
                    RouteResponse(
                        label=label,
                        distance_km=r.distance_km,
                        est_duration_min=r.duration_min,
                        geometry=GeoJSONGeometry(coordinates=r.coordinates),
                        toll_with_pass_inr=w_total,
                        toll_without_pass_inr=wo_total,
                        complete=calc_result.complete,
                        pass_info=PassResultResponse(
                            eligible=calc_result.pass_summary.eligible,
                            points_covered=calc_result.pass_summary.points_covered,
                            points_total=calc_result.pass_summary.points_total,
                            trips_used=calc_result.pass_summary.trips_used,
                            trips_left_after=calc_result.pass_summary.trips_left_after,
                            break_even_journeys=calc_result.pass_summary.break_even_journeys,
                        ),
                        points=point_res_list,
                        insights=insights,
                    )
                )

    db_duration = (time.perf_counter() - db_start) * 1000
    total_duration = (time.perf_counter() - start_time) * 1000

    # Structured single-line JSON log (lat/lng clamped to 2 decimals)
    log_entry = StructuredQuoteLog(
        timestamp=time.time(),
        request_id="req_" + str(int(start_time * 1000)),
        from_coord=[round(from_pt[0], 2), round(from_pt[1], 2)],
        to_coord=[round(to_pt[0], 2), round(to_pt[1], 2)],
        vehicle_class=req.vehicle_class.value,
        route_count=len(response_routes),
        total_points=total_points_matched,
        valhalla_duration_ms=round(valhalla_duration, 1),
        db_duration_ms=round(db_duration, 1),
        total_duration_ms=round(total_duration, 1),
    )
    logger.info(log_entry.model_dump_json())

    return QuoteResponse(
        rates_as_of=req_travel_date.isoformat(),
        pass_product=PassProductResponse(
            financial_year=pass_prod.financial_year,
            price_inr=round(float(pass_prod.price_inr)),
            max_trips=pass_prod.max_trips,
        ),
        routes=response_routes,
    )
