import asyncio
import time
from typing import Optional

import httpx

USER_AGENT = (
    "IndiaTollCalc/1.0 (+https://github.com/darkhorse/toll-calci; contact: info@indiatollcalc.org)"
)


class PoliteHttpClient:
    """
    HTTP client ensuring at least 2.0 seconds between outgoing requests
    to avoid overloading government and public authority websites.
    """

    def __init__(self, delay_sec: float = 2.0, timeout_sec: float = 15.0):
        self.delay_sec = delay_sec
        self.timeout_sec = timeout_sec
        self.last_request_time: float = 0.0

    async def get(self, url: str, params: Optional[dict] = None) -> bytes:
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.delay_sec:
            await asyncio.sleep(self.delay_sec - elapsed)

        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=self.timeout_sec, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            self.last_request_time = time.time()
            return resp.content
