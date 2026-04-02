"""Polymarket API client — fetches market data from Gamma API."""

import logging
from typing import Optional

import httpx

from backend.config import settings
from backend.models.market import PolymarketData

logger = logging.getLogger(__name__)

# Default API base
BASE_URL = settings.polymarket_base_url


class PolymarketClient:
    """Async HTTP client for the Polymarket Gamma API."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self._http: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=15.0,
                headers={"Accept": "application/json"},
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def get_active_markets(self, limit: int = 200) -> list[PolymarketData]:
        """Fetch active markets from Gamma API."""
        client = await self._client()
        markets = []
        offset = 0

        while True:
            try:
                resp = await client.get(
                    "/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": min(limit, 100),
                        "offset": offset,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for item in data:
                    market = self._parse_market(item)
                    if market:
                        markets.append(market)

                if len(data) < 100:
                    break
                offset += 100

                if len(markets) >= limit:
                    break

            except httpx.HTTPError as e:
                logger.error(f"API error fetching markets: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

        logger.info(f"Fetched {len(markets)} active markets")
        return markets

    async def get_market(self, condition_id: str) -> Optional[PolymarketData]:
        """Fetch a single market by condition ID."""
        client = await self._client()
        try:
            resp = await client.get(f"/markets/{condition_id}")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_market(data)
        except httpx.HTTPError as e:
            logger.error(f"API error fetching market {condition_id}: {e}")
            return None

    async def cancel_all_orders(self):
        """Placeholder for live trading — cancel all open orders."""
        logger.warning("cancel_all_orders called (paper mode — no-op)")

    def _parse_market(self, data: dict) -> Optional[PolymarketData]:
        """Parse raw API response into PolymarketData."""
        try:
            # Handle both flat and nested token structures
            tokens = data.get("tokens", [])
            yes_price = 0.5
            no_price = 0.5

            if tokens and len(tokens) >= 2:
                for token in tokens:
                    outcome = token.get("outcome", "").upper()
                    price = float(token.get("price", 0.5))
                    if outcome == "YES":
                        yes_price = price
                    elif outcome == "NO":
                        no_price = price
            else:
                yes_price = float(data.get("outcomePrices", [0.5, 0.5])[0])
                no_price = float(data.get("outcomePrices", [0.5, 0.5])[1])

            volume = float(data.get("volume24hr", 0) or data.get("volume", 0) or 0)
            liquidity = float(data.get("liquidity", 0) or 0)

            # Calculate spread from best bid/ask or estimate
            spread = abs(yes_price + no_price - 1.0)
            if spread < 0.001:
                spread = float(data.get("spread", 0.01) or 0.01)

            return PolymarketData(
                condition_id=data.get("conditionId", data.get("id", "")),
                question=data.get("question", ""),
                slug=data.get("slug", ""),
                category=data.get("category", data.get("groupSlug", "")),
                outcome_yes_price=yes_price,
                outcome_no_price=no_price,
                volume_24h=volume,
                liquidity=liquidity,
                spread=spread,
                end_date=data.get("endDate", data.get("end_date_iso", "")),
                active=data.get("active", True),
            )
        except (KeyError, ValueError, IndexError, TypeError) as e:
            logger.debug(f"Failed to parse market: {e}")
            return None
