from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict


class PlaceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    detail: Optional[str] = None
    lat: float
    lng: float


class PhotonClient:
    def __init__(self, base_url: str = "http://localhost:2322", timeout_sec: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    async def search(self, query: str, limit: int = 5) -> list[PlaceItem]:
        """
        Search places using self-hosted Photon OSM index.
        Restricted to India / bbox or countrycode if supported.
        """
        url = f"{self.base_url}/api"
        params: dict[str, Any] = {
            "q": query,
            "limit": limit,
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[PlaceItem] = []
        features = data.get("features", [])
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [0.0, 0.0])

            place_id = f"osm:{props.get('osm_type', 'N')}{props.get('osm_id', '')}"
            name = props.get("name") or props.get("city") or props.get("country", "")

            # Combine state / district into detail
            detail_parts = [props.get("state"), props.get("country")]
            detail = ", ".join(p for p in detail_parts if p) or None

            results.append(
                PlaceItem(
                    id=place_id,
                    name=name,
                    detail=detail,
                    lng=coords[0],
                    lat=coords[1],
                )
            )

        return results
