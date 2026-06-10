"""Shared HTTP client base with retry logic."""
import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class BaseClient:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None, rate_limit_rps: float = 2.0):
        self._base_url = base_url
        self._headers = headers or {}
        self._rate_limit_rps = rate_limit_rps
        self._last_request: float = 0.0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseClient":
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=30.0)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Simple token-bucket rate limiter."""
        now = asyncio.get_event_loop().time()
        gap = 1.0 / self._rate_limit_rps
        wait = self._last_request + gap - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _get(self, path: str, params: dict | None = None) -> Any:
        await self._throttle()
        assert self._client is not None, "Use as async context manager"
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()
