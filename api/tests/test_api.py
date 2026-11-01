from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.app.clients.valhalla import ValhallaRoute
from api.app.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "database" in data


@pytest.mark.asyncio
async def test_invalid_input_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Unknown field 'foo' must be rejected (extra="forbid")
        bad_payload = {
            "from": {"lat": 26.85, "lng": 80.95},
            "to": {"lat": 28.61, "lng": 77.21},
            "vehicle_class": "CAR_JEEP_VAN",
            "commercial": False,
            "journey": "ONE_WAY",
            "unknown_field": "disallowed",
        }
        resp = await client.post("/v1/quote", json=bad_payload)
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_quote_endpoint_contract():
    """
    Test quote calculation along seeded UP corridor:
    Coordinates passing through Nawabganj Toll Plaza (id 101).
    """
    mock_valhalla_route = ValhallaRoute(
        distance_km=150.0,
        duration_min=120.0,
        coordinates=[
            [80.8000, 26.7500],
            [80.6015, 26.6340],  # Nawabganj Toll Plaza
            [80.0000, 26.4000],
        ],
    )

    with patch("api.app.main.valhalla_client.get_route", new_callable=AsyncMock) as mock_get_route:
        mock_get_route.return_value = [mock_valhalla_route]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "from": {"lat": 26.75, "lng": 80.80},
                "to": {"lat": 26.40, "lng": 80.00},
                "vehicle_class": "CAR_JEEP_VAN",
                "commercial": False,
                "journey": "ONE_WAY",
                "travel_date": "2026-11-02",
                "annual_pass": {"active": True, "trips_left": 50},
            }
            resp = await client.post("/v1/quote", json=payload)
            assert resp.status_code == 200
            data = resp.json()

            assert "rates_as_of" in data
            assert "pass_product" in data
            assert len(data["routes"]) == 1

            route = data["routes"][0]
            assert route["label"] == "USUAL"
            assert route["complete"] is True
            # Covered by pass -> 0 toll with pass, 100 without pass
            assert route["toll_with_pass_inr"] == 0
            assert route["toll_without_pass_inr"] == 100
            assert route["pass"]["points_covered"] == 1
            assert route["pass"]["trips_used"] == 1
            assert route["pass"]["trips_left_after"] == 49

            # Point response verification
            assert len(route["points"]) == 1
            point = route["points"][0]
            assert point["id"] == 101
            assert point["name"] == "Nawabganj Toll Plaza"
            assert point["pass_applied"] is True
            assert point["amount_inr"] == 0
            assert point["amount_without_pass_inr"] == 100
