"""Momentum strategy — detect sustained price movement and ride the trend.

Entry when momentum is strong and hasn't exhausted. Analytics show 60% WR
and strong profitability — this is the best-performing sub-strategy.
"""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class MomentumStrategy:
    """Trend-following strategy for prediction markets.

    Looks for sustained directional movement across multiple timeframes
    (1h, 6h, 24h). Enters when all timeframes agree and volume confirms.
    """

    def __init__(
        self,
        min_1h_change: float = 0.02,
        min_6h_change: float = 0.03,
        max_change: float = 0.25,
        min_liquidity: float = 5000,
        min_volume: float = 1000,
        min_price: float = 0.10,
        max_price: float = 0.90,
    ):
        self.min_1h_change = min_1h_change
        self.min_6h_change = min_6h_change
        self.max_change = max_change
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_price = max_price

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate a market for momentum entry."""
        change_1h = signal.price_change_1h
        change_6h = signal.price_change_6h
        change_24h = signal.price_change_24h

        # Need meaningful 1h movement
        if abs(change_1h) < self.min_1h_change:
            return None

        # 6h trend must agree and be significant
        if abs(change_6h) < self.min_6h_change:
            return None

        # 1h and 6h must be same direction (sustained trend)
        if (change_1h > 0) != (change_6h > 0):
            return None

        # Avoid exhausted moves
        if abs(change_1h) > self.max_change or abs(change_6h) > self.max_change:
            return None

        # Liquidity and volume gates
        if signal.liquidity < self.min_liquidity:
            return None
        if signal.volume_24h < self.min_volume:
            return None

        # Direction: follow the momentum
        if change_1h > 0:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes
        else:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no

        # Price bounds
        if entry_price < self.min_price or entry_price > self.max_price:
            return None

        # Confidence scoring
        confidence = 0.45  # base

        # Multi-timeframe alignment boosts confidence significantly
        if (change_1h > 0) == (change_24h > 0):
            confidence += 0.15  # All three timeframes agree

        # Acceleration: 1h change is a bigger proportion of 6h change
        if abs(change_6h) > 0:
            acceleration = abs(change_1h) / abs(change_6h)
            if acceleration > 0.5:
                confidence += 0.10  # Recent acceleration

        # Volume confirms trend
        if signal.liquidity > 0:
            vol_ratio = signal.volume_24h / signal.liquidity
            if vol_ratio > 0.5:
                confidence += 0.10
            if vol_ratio > 1.5:
                confidence += 0.05

        # Tight spread = cleaner entry
        if signal.spread < 0.02:
            confidence += 0.05

        confidence = min(confidence, 0.90)

        # Wider targets than scalping — momentum trades hold longer
        target = entry_price + 0.05
        stop_loss = entry_price - 0.025

        target = min(target, 0.95)
        stop_loss = max(stop_loss, 0.05)

        # EV
        win_prob = confidence
        ev = (win_prob * (target - entry_price)) - ((1 - win_prob) * (entry_price - stop_loss))

        if ev <= 0:
            return None

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="momentum",
            entry_price=entry_price,
            target_exit_price=target,
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,
            reasoning=(
                f"Momentum: 1h={change_1h:+.1%}, 6h={change_6h:+.1%}, "
                f"24h={change_24h:+.1%}, vol_ratio="
                f"{signal.volume_24h / signal.liquidity:.2f}"
                if signal.liquidity > 0 else
                f"Momentum: 1h={change_1h:+.1%}, 6h={change_6h:+.1%}"
            ),
        )
