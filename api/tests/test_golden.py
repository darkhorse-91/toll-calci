import csv
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.app.clients.valhalla import ValhallaRoute
from api.app.main import app


def load_golden_journeys():
    journeys = []
    with open("golden/journeys.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            journeys.append(row)
    return journeys


@pytest.mark.asyncio
@pytest.mark.parametrize("j", load_golden_journeys())
async def test_golden_journey_matches_to_rupee(j):
    # Determine which mock coordinates correspond to the route
    is_expressway = "Expressway" in j["from_name"] or "Agra" in j["to_name"]
    is_akbarpur = "Akbarpur" in j["to_name"]

    if is_expressway:
        # Route passing through Agra-Lucknow Expressway entry 301, mid 302, exit 303
        if "Kannauj" in j["to_name"]:
            coords = [
                [80.7710, 26.8320],  # Mohan Road (entry 301)
                [79.8800, 27.0500],  # Kannauj (exit 302)
            ]
        elif "Kannauj" in j["from_name"]:
            coords = [
                [79.8800, 27.0500],  # Kannauj (entry 302)
                [78.1000, 27.1500],  # Agra (exit 303)
            ]
        else:
            coords = [
                [80.7710, 26.8320],  # Mohan Road (entry 301)
                [79.8800, 27.0500],  # Kannauj
                [78.1000, 27.1500],  # Agra (exit 303)
            ]
    elif is_akbarpur:
        # Route passing Nawabganj (101) and Barajod (102)
        coords = [
            [80.8000, 26.7500],
            [80.6015, 26.6340],  # Nawabganj (101)
            [80.3000, 26.5000],  # NH-27 highway curvature waypoint
            [79.9500, 26.4150],  # Barajod (102)
            [79.8000, 26.3500],
        ]
    else:
        # Route passing Nawabganj (101) only
        coords = [
            [80.8000, 26.7500],
            [80.6015, 26.6340],  # Nawabganj (101)
            [80.0000, 26.4000],
        ]

    mock_route = ValhallaRoute(
        distance_km=150.0,
        duration_min=120.0,
        coordinates=coords,
    )

    with patch("api.app.main.valhalla_client.get_route", new_callable=AsyncMock) as mock_get_route:
        mock_get_route.return_value = [mock_route]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "from": {"lat": float(j["from_lat"]), "lng": float(j["from_lng"])},
                "to": {"lat": float(j["to_lat"]), "lng": float(j["to_lng"])},
                "vehicle_class": j["vehicle_class"],
                "commercial": j["commercial"].lower() == "true",
                "journey": j["journey"],
                "travel_date": j["travel_date"],
                "annual_pass": {
                    "active": j["has_pass"].lower() == "true",
                    "trips_left": int(j["trips_left"]) if j["trips_left"] else None,
                },
            }

            resp = await client.post("/v1/quote", json=payload)
            assert resp.status_code == 200, f"Error response: {resp.text}"
            data = resp.json()

            assert len(data["routes"]) >= 1
            primary = data["routes"][0]

            expected_wo = int(j["expected_without_pass_inr"])
            expected_w = int(j["expected_with_pass_inr"])

            actual_wo = primary["toll_without_pass_inr"]
            actual_w = primary["toll_with_pass_inr"]

            assert actual_wo == expected_wo, (
                f"[{j['from_name']}] Without pass mismatch: got {actual_wo}, expected {expected_wo}"
            )
            assert actual_w == expected_w, (
                f"[{j['from_name']}] With pass mismatch: got {actual_w}, expected {expected_w}"
            )
