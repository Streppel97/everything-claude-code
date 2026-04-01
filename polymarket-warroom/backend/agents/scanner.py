"""Market Scanner Agent — polls all Polymarket markets and flags opportunities."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.config import settings
from backend.db.database import PriceHistoryRow, async_session
from backend.models.market import Market, MarketSignal
from backend.services.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


class ScannerAgent:
    """Continuously scans active Polymarket markets for trading opportunities."""

    def __init__(self, client: PolymarketClient):
        self.client = client
        self._running = False
        self._last_scan: Optional[datetime] = None
        self._scan_count = 0
        self._signals: list[MarketSignal] = []
        self._price_history: dict[str, list[tuple[datetime, float]]] = {}
        self._callbacks: list = []

    def on_signals(self, callback):
        """Register callback for new signals."""
        self._callbacks.append(callback)

    @property
    def latest_signals(self) -> list[MarketSignal]:
        return self._signals.copy()

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def last_scan_time(self) -> Optional[datetime]:
        return self._last_scan

    async def scan_once(self) -> list[MarketSignal]:
        """Run a single scan of all markets."""
        logger.info("Starting market scan...")
        try:
            markets = await self.client.get_all_markets(active=True)
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

        self._scan_count += 1
        self._last_scan = datetime.utcnow()

        # Filter and score
        signals = []
        for market in markets:
            if not self._passes_filters(market):
                continue

            signal = self._evaluate_market(market)
            if signal and signal.signal_strength > 0.3:
                signals.append(signal)

            # Track price history
            self._record_price(market)

        # Sort by signal strength descending
        signals.sort(key=lambda s: s.signal_strength, reverse=True)
        self._signals = signals[:50]  # Keep top 50

        logger.info(
            f"Scan #{self._scan_count}: {len(markets)} markets scanned, "
            f"{len(self._signals)} signals generated"
        )

        # Store price history in DB
        await self._persist_price_history(markets)

        # Notify callbacks
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(self._signals)
                else:
                    cb(self._signals)
            except Exception as e:
                logger.error(f"Signal callback error: {e}")

        return self._signals

    async def start(self, interval: Optional[int] = None):
        """Start continuous scanning loop."""
        interval = interval or settings.scan_interval_seconds
        self._running = True
        logger.info(f"Scanner started, interval={interval}s")

        while self._running:
            await self.scan_once()
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the scanner."""
        self._running = False
        logger.info("Scanner stopped")

    def _passes_filters(self, market: Market) -> bool:
        """Check if market passes minimum filter criteria."""
        # Minimum liquidity
        if market.liquidity < settings.min_liquidity:
            return False

        # Minimum volume
        if market.volume_24h < settings.min_volume_24h:
            return False

        # Max spread
        if market.spread > settings.max_spread and market.spread > 0:
            return False

        # Price range (avoid near-certain outcomes)
        if market.outcome_yes_price < settings.min_price or market.outcome_yes_price > settings.max_price:
            return False

        # Time to resolution
        if market.resolution_date:
            now = datetime.now(timezone.utc)
            resolution = market.resolution_date
            if resolution.tzinfo is None:
                resolution = resolution.replace(tzinfo=timezone.utc)
            time_left = resolution - now
            if time_left < timedelta(hours=settings.min_time_to_resolution_hours):
                return False

        return True

    def _evaluate_market(self, market: Market) -> Optional[MarketSignal]:
        """Score a market and produce a signal if it looks interesting."""
        score = 0.0
        direction = "YES"
        reasons = []

        # Price momentum signals
        price_changes = self._get_price_changes(market.id)
        change_1h = price_changes.get("1h", 0.0)
        change_6h = price_changes.get("6h", 0.0)
        change_24h = price_changes.get("24h", 0.0)

        # Strong momentum
        if abs(change_1h) > 0.03:
            score += 0.3
            direction = "YES" if change_1h > 0 else "NO"
            reasons.append(f"Strong 1h momentum: {change_1h:+.1%}")

        # Volume relative to liquidity (high activity)
        if market.liquidity > 0:
            vol_liq_ratio = market.volume_24h / market.liquidity
            if vol_liq_ratio > 0.5:
                score += 0.2
                reasons.append(f"High volume/liquidity ratio: {vol_liq_ratio:.2f}")

        # Tight spread is favorable
        if market.spread < 0.02:
            score += 0.1
            reasons.append(f"Tight spread: {market.spread:.3f}")

        # Mid-range prices have more room to move
        mid_distance = abs(market.outcome_yes_price - 0.5)
        if mid_distance < 0.2:
            score += 0.15
            reasons.append("Price near 50/50 — high uncertainty")

        # High liquidity markets are safer
        if market.liquidity > 50000:
            score += 0.1
            reasons.append(f"Deep liquidity: ${market.liquidity:,.0f}")

        # Time to resolution — more time = more opportunity
        if market.resolution_date:
            now = datetime.now(timezone.utc)
            resolution = market.resolution_date
            if resolution.tzinfo is None:
                resolution = resolution.replace(tzinfo=timezone.utc)
            days_left = (resolution - now).total_seconds() / 86400
            if days_left > 7:
                score += 0.1
                reasons.append(f"{days_left:.0f} days to resolution")
            time_to_res = resolution - now
        else:
            time_to_res = timedelta(days=30)

        score = min(score, 1.0)

        if not reasons:
            return None

        # Determine direction based on momentum
        if market.outcome_yes_price < 0.4 and change_1h > 0:
            direction = "YES"
        elif market.outcome_yes_price > 0.6 and change_1h < 0:
            direction = "NO"

        return MarketSignal(
            market_id=market.id,
            question=market.question,
            category=market.category,
            current_price_yes=market.outcome_yes_price,
            current_price_no=market.outcome_no_price,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            price_change_1h=change_1h,
            price_change_6h=change_6h,
            price_change_24h=change_24h,
            spread=market.spread,
            time_to_resolution=time_to_res,
            signal_strength=score,
            signal_direction=direction,
            reasoning="; ".join(reasons),
        )

    def _record_price(self, market: Market):
        """Record price data point for history tracking."""
        if market.id not in self._price_history:
            self._price_history[market.id] = []

        self._price_history[market.id].append(
            (datetime.utcnow(), market.outcome_yes_price)
        )

        # Keep last 1000 data points per market
        if len(self._price_history[market.id]) > 1000:
            self._price_history[market.id] = self._price_history[market.id][-1000:]

    def _get_price_changes(self, market_id: str) -> dict[str, float]:
        """Calculate price changes over various time windows."""
        history = self._price_history.get(market_id, [])
        if len(history) < 2:
            return {"1h": 0.0, "6h": 0.0, "24h": 0.0}

        now = datetime.utcnow()
        current_price = history[-1][1]
        changes = {}

        for label, delta in [("1h", timedelta(hours=1)), ("6h", timedelta(hours=6)), ("24h", timedelta(hours=24))]:
            target_time = now - delta
            closest = None
            for ts, price in history:
                if ts <= target_time:
                    closest = price
            if closest is not None and closest > 0:
                changes[label] = (current_price - closest) / closest
            else:
                changes[label] = 0.0

        return changes

    async def _persist_price_history(self, markets: list[Market]):
        """Store price snapshots to database."""
        try:
            async with async_session() as session:
                for market in markets[:100]:  # Top 100 to avoid excessive writes
                    row = PriceHistoryRow(
                        market_id=market.id,
                        price_yes=market.outcome_yes_price,
                        price_no=market.outcome_no_price,
                        volume=market.volume_24h,
                        timestamp=datetime.utcnow(),
                    )
                    session.add(row)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist price history: {e}")
