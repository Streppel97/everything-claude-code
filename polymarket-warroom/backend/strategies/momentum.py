"""Price momentum / trend detection strategy."""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class MomentumStrategy:
    """Detect sustained price movement and enter in direction of trend.

    Entry when momentum is strong and hasn't exhausted. Uses multiple
    timeframe confirmation.
    """

    def __init__(
        self,
        min_1h_change: float = 0.02,
        min_6h_change: float = 0.03,
        max_price_extreme: float = 0.90,
        min_price_extreme: float = 0.10,
    ):
        self.min_1h_change = min_1h_change
        self.min_6h_change = min_6h_change
        self.max_price_extreme = max_price_extreme
        self.min_price_extreme = min_price_extreme

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate a market signal for momentum entry."""
        change_1h = signal.price_change_1h
        change_6h = signal.price_change_6h

        # Need meaningful 1h movement
        if abs(change_1h) < self.min_1h_change:
            return None

        # Determine direction
        if change_1h > 0:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes
        else:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no

        # Don't chase into extremes (price exhaustion)
        if entry_price > self.max_price_extreme or entry_price < self.min_price_extreme:
            return None

        # Multi-timeframe confirmation: 6h should agree with 1h direction
        timeframe_aligned = (change_1h > 0 and change_6h > 0) or (change_1h < 0 and change_6h < 0)

        # Calculate confidence
        confidence = 0.3  # base
        if timeframe_aligned:
            confidence += 0.2
        if abs(change_1h) > self.min_1h_change * 2:
            confidence += 0.15
        if signal.volume_24h > 10000:
            confidence += 0.1
        if signal.spread < 0.02:
            confidence += 0.1

        confidence = min(confidence, 0.95)

        # Calculate targets
        if direction == TradeDirection.BUY_YES:
            target = min(entry_price + abs(change_1h) * 1.5, 0.95)
            stop_loss = max(entry_price - abs(change_1h) * 0.75, 0.05)
        else:
            target = min(entry_price + abs(change_1h) * 1.5, 0.95)
            stop_loss = max(entry_price - abs(change_1h) * 0.75, 0.05)

        # Expected value
        win_prob = confidence
        win_amount = target - entry_price
        loss_amount = entry_price - stop_loss
        ev = (win_prob * win_amount) - ((1 - win_prob) * loss_amount)

        reasons = []
        reasons.append(f"1h momentum: {change_1h:+.1%}")
        if timeframe_aligned:
            reasons.append(f"6h confirms: {change_6h:+.1%}")
        reasons.append(f"Entry: {entry_price:.3f}, Target: {target:.3f}")

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="momentum",
            entry_price=entry_price,
            target_exit_price=target,
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,  # Risk manager will set this
            reasoning="; ".join(reasons),
        )
