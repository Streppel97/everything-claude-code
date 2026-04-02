"""Scanner Agent — continuously scans ALL active Polymarket markets.

Runs on a configurable interval (default: 30 seconds). Applies filtering
criteria to flag markets worth analyzing.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.config import settings
from backend.models.market import MarketSignal
from backend.services.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


class ScannerAgent:
    """Scans Polymarket markets and produces MarketSignal objects."""

    def __init__(self, client: PolymarketClient):
        self.client = client
        self._scan_count = 0
        self._last_scan: Optional[datetime] = None
        self._price_history: dict[str, list[tuple[datetime, float]]] = {}
        # Markets with open positions — skip to avoid duplicate signals
        self._excluded_market_ids: set[str] = set()

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def last_scan(self) -> Optional[datetime]:
        return self._last_scan

    def set_excluded_markets(self, market_ids: set[str]):
        """Update the set of markets to skip (already have open positions)."""
        self._excluded_market_ids = market_ids

    async def scan_once(self) -> list[MarketSignal]:
        """Scan all active markets and return flagged signals."""
        self._scan_count += 1
        self._last_scan = datetime.utcnow()

        raw_markets = await self.client.get_active_markets()
        signals = []

        for market in raw_markets:
            # Skip markets we already have positions in
            mid = market.condition_id
            if mid in self._excluded_market_ids:
                continue
            signal = self._evaluate_market(market)
            if signal:
                signals.append(signal)

        # Sort by signal strength descending
        signals.sort(key=lambda s: s.signal_strength, reverse=True)

        logger.info(
            f"Scan #{self._scan_count}: {len(raw_markets)} markets → "
            f"{len(signals)} flagged"
        )

        return signals

    def _evaluate_market(self, market) -> Optional[MarketSignal]:
        """Apply filtering criteria to a single market."""
        # Liquidity gate
        if market.liquidity < settings.scanner_min_liquidity:
            return None

        # Volume gate
        if market.volume_24h < settings.scanner_min_volume_24h:
            return None

        # Spread gate
        if market.spread > settings.scanner_max_spread:
            return None

        # Price range — avoid near-certain outcomes
        yes_price = market.outcome_yes_price
        if yes_price < settings.scanner_price_min or yes_price > settings.scanner_price_max:
            return None

        # Time to resolution — avoid last-minute chaos
        time_to_resolution = self._get_time_to_resolution(market)
        if time_to_resolution < timedelta(hours=settings.scanner_min_time_hours):
            return None

        # Calculate price changes from history
        market_id = market.condition_id
        price_changes = self._calculate_price_changes(market_id, yes_price)

        # Compute signal strength (composite score)
        signal_strength = self._compute_signal_strength(
            market, price_changes, time_to_resolution
        )

        # Determine signal direction
        change_1h = price_changes.get("1h", 0.0)
        signal_direction = "YES" if change_1h >= 0 else "NO"

        # Track price history
        self._record_price(market_id, yes_price)

        return MarketSignal(
            market_id=market_id,
            question=market.question,
            category=market.category,
            current_price_yes=yes_price,
            current_price_no=market.outcome_no_price,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            price_change_1h=price_changes.get("1h", 0.0),
            price_change_6h=price_changes.get("6h", 0.0),
            price_change_24h=price_changes.get("24h", 0.0),
            spread=market.spread,
            time_to_resolution=time_to_resolution,
            signal_strength=signal_strength,
            signal_direction=signal_direction,
            reasoning=self._build_reasoning(market, price_changes, signal_strength),
        )

    def _get_time_to_resolution(self, market) -> timedelta:
        """Parse end_date and compute time remaining."""
        if not market.end_date:
            return timedelta(days=30)  # Default for undated markets
        try:
            end = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
            remaining = end - datetime.utcnow().replace(
                tzinfo=end.tzinfo if end.tzinfo else None
            )
            return max(remaining, timedelta(0))
        except (ValueError, TypeError):
            return timedelta(days=30)

    def _calculate_price_changes(
        self, market_id: str, current_price: float
    ) -> dict[str, float]:
        """Calculate price changes from stored history."""
        history = self._price_history.get(market_id, [])
        now = datetime.utcnow()
        changes = {}

        for label, delta in [("1h", timedelta(hours=1)),
                             ("6h", timedelta(hours=6)),
                             ("24h", timedelta(hours=24))]:
            target_time = now - delta
            closest = None
            for ts, price in history:
                if ts <= target_time:
                    if closest is None or ts > closest[0]:
                        closest = (ts, price)

            if closest and closest[1] > 0:
                changes[label] = (current_price - closest[1]) / closest[1]
            else:
                changes[label] = 0.0

        return changes

    def _record_price(self, market_id: str, price: float):
        """Store price data point for change calculations."""
        now = datetime.utcnow()
        if market_id not in self._price_history:
            self._price_history[market_id] = []

        self._price_history[market_id].append((now, price))

        # Keep only last 24h of data
        cutoff = now - timedelta(hours=25)
        self._price_history[market_id] = [
            (ts, p) for ts, p in self._price_history[market_id] if ts > cutoff
        ]

    def _compute_signal_strength(
        self, market, price_changes: dict, time_to_resolution: timedelta
    ) -> float:
        """Compute composite signal strength 0.0 - 1.0."""
        score = 0.0

        # Liquidity score (0-0.25)
        liq = market.liquidity
        if liq > 50000:
            score += 0.25
        elif liq > 20000:
            score += 0.20
        elif liq > 10000:
            score += 0.15
        else:
            score += 0.10

        # Volume activity (0-0.25)
        if liq > 0:
            vol_ratio = market.volume_24h / liq
            score += min(vol_ratio * 0.10, 0.25)

        # Price movement (0-0.25)
        change_1h = abs(price_changes.get("1h", 0.0))
        if change_1h > 0.01:
            score += min(change_1h * 2, 0.25)

        # Spread quality (0-0.25)
        if market.spread < 0.01:
            score += 0.25
        elif market.spread < 0.02:
            score += 0.20
        elif market.spread < 0.03:
            score += 0.15
        elif market.spread < 0.05:
            score += 0.10

        return min(score, 1.0)

    def _build_reasoning(
        self, market, price_changes: dict, strength: float
    ) -> str:
        """Build human-readable reasoning for why this market was flagged."""
        parts = [f"strength={strength:.2f}"]
        parts.append(f"liq=${market.liquidity:,.0f}")
        parts.append(f"vol=${market.volume_24h:,.0f}")
        parts.append(f"spread={market.spread:.3f}")

        change_1h = price_changes.get("1h", 0.0)
        if abs(change_1h) > 0.001:
            parts.append(f"1h={change_1h:+.1%}")

        return ", ".join(parts)
