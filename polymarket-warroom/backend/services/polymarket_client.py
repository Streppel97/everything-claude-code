"""Polymarket API client wrapping Gamma Markets API and CLOB API."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from backend.models.market import Market, OrderBook, OrderBookLevel

logger = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Rate limiting: 100 requests/minute
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds


class RateLimiter:
    """Token-bucket rate limiter."""

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window: float = RATE_LIMIT_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self.timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            # Remove timestamps outside window
            self.timestamps = [t for t in self.timestamps if now - t < self.window]
            if len(self.timestamps) >= self.max_requests:
                wait_time = self.window - (now - self.timestamps[0])
                logger.debug(f"Rate limit hit, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            self.timestamps.append(time.monotonic())


class PolymarketClient:
    """Unified client for Polymarket Gamma and CLOB APIs."""

    def __init__(self, api_key: str = "", timeout: float = 30.0):
        self.api_key = api_key
        self.rate_limiter = RateLimiter()
        self._market_cache: dict[str, Market] = {}
        self._cache_timestamp: float = 0
        self._cache_ttl = 60.0  # seconds
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    async def close(self):
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        retries: int = 3,
        backoff: float = 1.0,
        **kwargs,
    ) -> dict | list:
        """Make an API request with rate limiting and retry logic."""
        await self.rate_limiter.acquire()

        for attempt in range(retries):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = backoff * (2 ** attempt)
                    logger.warning(f"Rate limited, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                if e.response.status_code >= 500 and attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    logger.warning(f"Server error {e.response.status_code}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    logger.warning(f"Connection error: {e}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise

        return {}

    # ---- Gamma Markets API ----

    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
    ) -> list[Market]:
        """Fetch markets from Gamma API with pagination."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": "false",
        }
        data = await self._request("GET", f"{GAMMA_API_BASE}/markets", params=params)

        markets = []
        for item in data if isinstance(data, list) else data.get("data", data.get("markets", [])):
            market = self._parse_gamma_market(item)
            if market:
                markets.append(market)
                self._market_cache[market.id] = market

        self._cache_timestamp = time.monotonic()
        return markets

    async def get_all_markets(self, active: bool = True) -> list[Market]:
        """Fetch ALL active markets with automatic pagination."""
        all_markets = []
        offset = 0
        limit = 100

        while True:
            batch = await self.get_markets(limit=limit, offset=offset, active=active)
            if not batch:
                break
            all_markets.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        logger.info(f"Fetched {len(all_markets)} total markets")
        return all_markets

    async def get_market(self, market_id: str) -> Optional[Market]:
        """Fetch a single market by ID."""
        # Check cache first
        now = time.monotonic()
        if market_id in self._market_cache and (now - self._cache_timestamp) < self._cache_ttl:
            return self._market_cache[market_id]

        data = await self._request("GET", f"{GAMMA_API_BASE}/markets/{market_id}")
        if not data:
            return None

        market = self._parse_gamma_market(data)
        if market:
            self._market_cache[market.id] = market
        return market

    async def get_events(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Fetch events (market groups) from Gamma API."""
        params = {"limit": limit, "offset": offset, "active": "true", "closed": "false"}
        data = await self._request("GET", f"{GAMMA_API_BASE}/events", params=params)
        return data if isinstance(data, list) else data.get("data", [])

    # ---- CLOB API ----

    async def get_price(self, token_id: str) -> Optional[float]:
        """Get current price for a condition token."""
        data = await self._request("GET", f"{CLOB_API_BASE}/price", params={"token_id": token_id})
        if data and "price" in data:
            return float(data["price"])
        return None

    async def get_prices(self, market_id: str) -> dict[str, float]:
        """Get YES/NO prices for a market from CLOB."""
        data = await self._request("GET", f"{CLOB_API_BASE}/prices", params={"market_id": market_id})
        if isinstance(data, dict):
            return data
        return {}

    async def get_order_book(self, token_id: str) -> OrderBook:
        """Get order book for a token."""
        data = await self._request("GET", f"{CLOB_API_BASE}/book", params={"token_id": token_id})

        bids = [OrderBookLevel(price=float(b["price"]), size=float(b["size"]))
                for b in data.get("bids", [])]
        asks = [OrderBookLevel(price=float(a["price"]), size=float(a["size"]))
                for a in data.get("asks", [])]

        return OrderBook(
            market_id=token_id,
            bids=sorted(bids, key=lambda x: x.price, reverse=True),
            asks=sorted(asks, key=lambda x: x.price),
        )

    async def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get midpoint price from order book."""
        data = await self._request("GET", f"{CLOB_API_BASE}/midpoint", params={"token_id": token_id})
        if data and "mid" in data:
            return float(data["mid"])
        return None

    # ---- Live Trading (interface only, requires wallet auth) ----

    async def place_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
    ) -> dict:
        """Place a limit order on the CLOB. Requires API key and wallet."""
        if not self.api_key:
            raise ValueError("API key required for live trading")

        order_payload = {
            "tokenID": token_id,
            "side": side,
            "price": str(price),
            "size": str(size),
            "type": "LIMIT",
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return await self._request(
            "POST", f"{CLOB_API_BASE}/order", json=order_payload, headers=headers
        )

    async def cancel_order(self, order_id: str) -> dict:
        """Cancel an open order."""
        if not self.api_key:
            raise ValueError("API key required for live trading")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return await self._request(
            "DELETE", f"{CLOB_API_BASE}/order/{order_id}", headers=headers
        )

    async def cancel_all_orders(self) -> dict:
        """Cancel all open orders (kill switch)."""
        if not self.api_key:
            raise ValueError("API key required for live trading")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return await self._request(
            "DELETE", f"{CLOB_API_BASE}/orders", headers=headers
        )

    # ---- Helpers ----

    def _parse_gamma_market(self, data: dict) -> Optional[Market]:
        """Parse a Gamma API market response into a Market model."""
        try:
            market_id = str(data.get("id", data.get("condition_id", "")))
            if not market_id:
                return None

            # Parse prices from outcomes or top-level fields
            yes_price = 0.5
            no_price = 0.5
            if "outcomePrices" in data:
                try:
                    prices = data["outcomePrices"]
                    if isinstance(prices, str):
                        import json
                        prices = json.loads(prices)
                    if isinstance(prices, list) and len(prices) >= 2:
                        yes_price = float(prices[0])
                        no_price = float(prices[1])
                except (ValueError, IndexError, TypeError):
                    pass

            # Parse best bid/ask for spread
            spread = 0.0
            best_bid = data.get("bestBid")
            best_ask = data.get("bestAsk")
            if best_bid is not None and best_ask is not None:
                try:
                    spread = float(best_ask) - float(best_bid)
                except (ValueError, TypeError):
                    pass

            # Parse resolution date
            resolution_date = None
            end_date = data.get("endDate") or data.get("end_date_iso") or data.get("resolutionDate")
            if end_date:
                try:
                    if isinstance(end_date, str):
                        resolution_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            return Market(
                id=market_id,
                question=data.get("question", data.get("title", "Unknown")),
                category=data.get("category", data.get("groupItemTitle", "")),
                outcome_yes_price=yes_price,
                outcome_no_price=no_price,
                volume_24h=float(data.get("volume24hr", data.get("volume", 0)) or 0),
                liquidity=float(data.get("liquidity", data.get("liquidityNum", 0)) or 0),
                spread=spread,
                resolution_date=resolution_date,
                condition_id=data.get("conditionId", data.get("condition_id", "")),
                slug=data.get("slug", ""),
                active=data.get("active", True),
                last_updated=datetime.utcnow(),
            )
        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    def invalidate_cache(self):
        """Clear the market cache."""
        self._market_cache.clear()
        self._cache_timestamp = 0
