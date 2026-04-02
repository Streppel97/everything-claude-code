"""Volume Spike strategy — detect unusual volume without proportional price move.

Analytics show 8% WR historically — this strategy has STRICT filters to avoid
false breakouts. It feeds signals to the scalper rather than trading directly.
"""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class VolumeSpikeStrategy:
    """Breakout detection via volume anomalies.

    Unusual volume without proportional price movement signals a pending
    breakout. Historical WR is low (8%), so this strategy uses very strict
    filters and only fires when multiple confirmation signals align.
    """

    def __init__(
        self,
        min_vol_ratio: float = 3.0,  # Volume must be 3x liquidity (strict)
        max_price_change_1h: float = 0.02,  # Price hasn't moved much yet
        min_liquidity: float = 10000,  # Higher liquidity floor
        min_price: float = 0.20,
        max_price: float = 0.80,
        min_spread_quality: float = 0.02,  # Max spread allowed
    ):
        self.min_vol_ratio = min_vol_ratio
        self.max_price_change_1h = max_price_change_1h
        self.min_liquidity = min_liquidity
        self.min_price = min_price
        self.max_price = max_price
        self.min_spread_quality = min_spread_quality

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate a market for volume-based breakout."""
        if signal.liquidity < self.min_liquidity:
            return None

        vol_ratio = signal.volume_24h / signal.liquidity if signal.liquidity > 0 else 0

        # Need very high volume relative to liquidity
        if vol_ratio < self.min_vol_ratio:
            return None

        # Price should NOT have moved proportionally (breakout pending)
        if abs(signal.price_change_1h) > self.max_price_change_1h:
            return None

        # Tight spread required — wide spread with volume spike is noise
        if signal.spread > self.min_spread_quality:
            return None

        # Direction: use 6h trend as breakout direction indicator
        # If 6h is slightly positive, breakout likely continues up
        if signal.price_change_6h >= 0:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes
        else:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no

        if entry_price < self.min_price or entry_price > self.max_price:
            return None

        # Conservative confidence — this strategy has low historical WR
        confidence = 0.35

        # Extreme volume ratio boosts slightly
        if vol_ratio > 5.0:
            confidence += 0.10
        if vol_ratio > 8.0:
            confidence += 0.05

        # 24h trend agreement
        if (signal.price_change_6h >= 0) == (signal.price_change_24h >= 0):
            confidence += 0.10

        # Very tight spread is a strong signal
        if signal.spread < 0.01:
            confidence += 0.10

        confidence = min(confidence, 0.70)

        # Moderate targets — breakouts can be large but unreliable
        target = entry_price + 0.04
        stop_loss = entry_price - 0.015

        target = min(target, 0.95)
        stop_loss = max(stop_loss, 0.05)

        ev = (confidence * (target - entry_price)) - ((1 - confidence) * (entry_price - stop_loss))

        if ev <= 0:
            return None

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="volume_spike",
            entry_price=entry_price,
            target_exit_price=target,
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,
            reasoning=(
                f"VolSpike: vol/liq={vol_ratio:.1f}x, 1h_move={signal.price_change_1h:+.1%}, "
                f"spread={signal.spread:.3f} — pending breakout"
            ),
        )
