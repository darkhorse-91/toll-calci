from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict


def decode_polyline6(encoded: str) -> list[list[float]]:
    """
    Decodes a Valhalla encoded polyline with precision 6 into [[lng, lat], ...] coordinates.
    """
    coordinates: list[list[float]] = []
    index, lat, lng, length = 0, 0, 0, len(encoded)

    while index < length:
        # Decode latitude
        shift, result = 0, 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        delta_lat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += delta_lat

        # Decode longitude
        shift, result = 0, 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        delta_lng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += delta_lng

        # GeoJSON is [longitude, latitude]
        coordinates.append([round(lng * 1e-6, 6), round(lat * 1e-6, 6)])

    return coordinates


class ValhallaRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distance_km: float
    duration_min: float
    coordinates: list[list[float]]
    summary: dict[str, Any] = {}


class ValhallaClient:
    def __init__(self, base_url: str = "http://localhost:8002", timeout_sec: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    async def get_route(
        self,
        from_coord: tuple[float, float],  # (lat, lng)
        to_coord: tuple[float, float],  # (lat, lng)
        use_tolls: float = 1.0,
        alternates: int = 0,
    ) -> list[ValhallaRoute]:
        """
        Request route from Valhalla with auto costing and 1 retry on connection error.
        """
        url = f"{self.base_url}/route"
        payload: dict[str, Any] = {
            "locations": [
                {"lat": from_coord[0], "lon": from_coord[1]},
                {"lat": to_coord[0], "lon": to_coord[1]},
            ],
            "costing": "auto",
            "costing_options": {
                "auto": {
                    "use_tolls": use_tolls,
                }
            },
            "directions_options": {
                "units": "kilometers",
            },
        }
        if alternates > 0:
            payload["alternates"] = alternates

        last_err: Optional[Exception] = None
        # 1 retry on connection error
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                routes: list[ValhallaRoute] = []
                # Check for primary route
                trip = data.get("trip", {})
                legs = trip.get("legs", [])
                if legs:
                    summary = trip.get("summary", {})
                    shape = legs[0].get("shape", "")
                    coords = decode_polyline6(shape) if shape else []
                    routes.append(
                        ValhallaRoute(
                            distance_km=round(summary.get("length", 0.0), 1),
                            duration_min=round(summary.get("time", 0.0) / 60.0, 1),
                            coordinates=coords,
                            summary=summary,
                        )
                    )

                # Check for alternates
                for alt in data.get("alternates", []):
                    alt_trip = alt.get("trip", {})
                    alt_legs = alt_trip.get("legs", [])
                    if alt_legs:
                        alt_summary = alt_trip.get("summary", {})
                        alt_shape = alt_legs[0].get("shape", "")
                        alt_coords = decode_polyline6(alt_shape) if alt_shape else []
                        routes.append(
                            ValhallaRoute(
                                distance_km=round(alt_summary.get("length", 0.0), 1),
                                duration_min=round(alt_summary.get("time", 0.0) / 60.0, 1),
                                coordinates=alt_coords,
                                summary=alt_summary,
                            )
                        )

                return routes

            except (httpx.ConnectError, httpx.TimeoutException) as err:
                last_err = err
                if attempt == 1:
                    raise last_err from err
            except Exception:
                raise

        if last_err:
            raise last_err
        return []
