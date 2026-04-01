"""WebSocket price streaming service."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PriceFeed:
    """WebSocket-based price feed from Polymarket CLOB."""

    def __init__(self):
        self._ws = None
        self._subscribed_markets: set[str] = set()
        self._callbacks: list[Callable] = []
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._latest_prices: dict[str, dict] = {}

    def on_price_update(self, callback: Callable):
        """Register a callback for price updates."""
        self._callbacks.append(callback)

    def get_latest_price(self, market_id: str) -> Optional[dict]:
        """Get the last known price for a market."""
        return self._latest_prices.get(market_id)

    async def subscribe(self, market_ids: list[str]):
        """Subscribe to price updates for given markets."""
        self._subscribed_markets.update(market_ids)
        if self._ws:
            for market_id in market_ids:
                msg = json.dumps({
                    "type": "subscribe",
                    "channel": "market",
                    "market": market_id,
                })
                try:
                    await self._ws.send(msg)
                except ConnectionClosed:
                    logger.warning("WebSocket closed during subscribe")

    async def unsubscribe(self, market_ids: list[str]):
        """Unsubscribe from price updates."""
        for market_id in market_ids:
            self._subscribed_markets.discard(market_id)
            if self._ws:
                msg = json.dumps({
                    "type": "unsubscribe",
                    "channel": "market",
                    "market": market_id,
                })
                try:
                    await self._ws.send(msg)
                except ConnectionClosed:
                    pass

    async def start(self):
        """Start the price feed with auto-reconnect."""
        self._running = True
        delay = self._reconnect_delay

        while self._running:
            try:
                async with websockets.connect(POLYMARKET_WS_URL) as ws:
                    self._ws = ws
                    delay = self._reconnect_delay  # Reset on successful connect
                    logger.info("Price feed WebSocket connected")

                    # Resubscribe to all markets
                    for market_id in self._subscribed_markets:
                        msg = json.dumps({
                            "type": "subscribe",
                            "channel": "market",
                            "market": market_id,
                        })
                        await ws.send(msg)

                    # Listen for messages
                    async for raw_msg in ws:
                        try:
                            data = json.loads(raw_msg)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            logger.debug(f"Non-JSON message: {raw_msg[:100]}")

            except ConnectionClosed:
                logger.warning("Price feed disconnected")
            except Exception as e:
                logger.error(f"Price feed error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

        self._ws = None

    async def stop(self):
        """Stop the price feed."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _handle_message(self, data: dict):
        """Process incoming WebSocket message."""
        msg_type = data.get("type", "")

        if msg_type in ("price_change", "book", "trade"):
            market_id = data.get("market", data.get("asset_id", ""))
            if not market_id:
                return

            price_data = {
                "market_id": market_id,
                "type": msg_type,
                "timestamp": datetime.utcnow().isoformat(),
                **data,
            }
            self._latest_prices[market_id] = price_data

            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(price_data)
                    else:
                        callback(price_data)
                except Exception as e:
                    logger.error(f"Price callback error: {e}")
