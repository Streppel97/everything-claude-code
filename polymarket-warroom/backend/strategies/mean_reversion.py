"""Mean reversion strategy — identify overreactions and fade them."""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class MeanReversionStrategy:
    """Identify markets that overreacted and enter expecting reversion.

    Entry when price deviates significantly from rolling average,
    expecting mean reversion.
    """

    def __init__(
        self,
        min_deviation: float = 0.05,
        max_deviation: float = 0.30,
        reversion_target_pct: float = 0.5,
    ):
        self.min_deviation = min_deviation
        self.max_deviation = max_deviation
        self.reversion_target_pct = reversion_target_pct

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate market for mean reversion entry."""
        change_1h = signal.price_change_1h
        change_6h = signal.price_change_6h
        change_24h = signal.price_change_24h

        # Need significant short-term deviation
        if abs(change_1h) < self.min_deviation:
            return None

        # But not so much that it's a regime change
        if abs(change_1h) > self.max_deviation:
            return None

        # Key signal: short-term move opposes longer-term trend
        # (suggesting overreaction rather than new trend)
        short_long_divergence = (
            (change_1h > 0 and change_24h < 0) or
            (change_1h < 0 and change_24h > 0)
        )

        if not short_long_divergence and abs(change_1h) < self.min_deviation * 2:
            return None

        # Fade the move: if price spiked up, buy NO. If dropped, buy YES.
        if change_1h > 0:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no
        else:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes

        # Calculate confidence
        confidence = 0.35
        if short_long_divergence:
            confidence += 0.2
        if signal.spread < 0.03:
            confidence += 0.1
        if signal.liquidity > 20000:
            confidence += 0.1
        # Higher confidence for bigger deviations (more to revert)
        if abs(change_1h) > self.min_deviation * 1.5:
            confidence += 0.1

        confidence = min(confidence, 0.85)

        # Target: partial reversion
        reversion_amount = abs(change_1h) * self.reversion_target_pct
        target = entry_price + reversion_amount
        stop_loss = max(entry_price - abs(change_1h) * 0.5, 0.02)

        # Expected value
        win_prob = confidence
        ev = (win_prob * (target - entry_price)) - ((1 - win_prob) * (entry_price - stop_loss))

        reasons = [
            f"Mean reversion: 1h change {change_1h:+.1%}",
            f"24h change {change_24h:+.1%}" if change_24h else "",
            "Short/long divergence detected" if short_long_divergence else "",
            f"Fade direction: {direction.value}",
        ]

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="mean_reversion",
            entry_price=entry_price,
            target_exit_price=min(target, 0.95),
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,
            reasoning="; ".join(r for r in reasons if r),
        )
