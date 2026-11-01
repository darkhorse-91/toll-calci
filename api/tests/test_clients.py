from unittest.mock import AsyncMock, patch

import httpx
import pytest

from api.app.clients.photon import PhotonClient
from api.app.clients.valhalla import ValhallaClient, decode_polyline6


@pytest.mark.asyncio
async def test_photon_client_search_success():
    mock_payload = {
        "features": [
            {
                "properties": {
                    "osm_id": 12345,
                    "name": "Lucknow",
                    "state": "Uttar Pradesh",
                    "country": "India",
                },
                "geometry": {
                    "coordinates": [80.9462, 26.8467],
                },
            }
        ]
    }

    mock_resp = httpx.Response(
        200, json=mock_payload, request=httpx.Request("GET", "http://test/api")
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        client = PhotonClient(base_url="http://mock-photon")
        results = await client.search("lucknow", limit=5)

    assert len(results) == 1
    assert results[0].name == "Lucknow"
    assert results[0].lat == 26.8467
    assert results[0].lng == 80.9462


@pytest.mark.asyncio
async def test_valhalla_client_get_route_success():
    mock_payload = {
        "trip": {
            "summary": {
                "length": 135.2,
                "time": 8400,
            },
            "legs": [
                {
                    "shape": "o`qmC_~vfM_c@i[",
                }
            ],
        }
    }

    mock_resp = httpx.Response(
        200, json=mock_payload, request=httpx.Request("POST", "http://test/route")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        client = ValhallaClient(base_url="http://mock-valhalla")
        routes = await client.get_route((26.8467, 80.9462), (26.7922, 82.1998))

    assert len(routes) == 1
    assert routes[0].distance_km == 135.2
    assert routes[0].duration_min == 140.0
    assert len(routes[0].coordinates) >= 2


def test_decode_polyline6():
    coords = decode_polyline6("o`qmC_~vfM_c@i[")
    assert len(coords) >= 2
    # Verify coordinate ordering [longitude, latitude]
    assert isinstance(coords[0][0], float)
    assert isinstance(coords[0][1], float)
