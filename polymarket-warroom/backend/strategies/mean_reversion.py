"""Mean Reversion strategy — fade overreactions.

Identifies markets that moved too far too fast and are likely to revert.
Entry when price deviates significantly from rolling average.
"""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class MeanReversionStrategy:
    """Fade overreactions in prediction markets.

    Looks for large short-term moves that diverge from longer-term trend.
    Enters opposite to the short-term move, expecting reversion.
    """

    def __init__(
        self,
        min_1h_overreaction: float = 0.03,  # Lowered from 0.05 — catch smaller overreactions
        max_6h_trend: float = 0.03,
        min_liquidity: float = 3000,         # Lowered from 5000
        min_volume: float = 1000,            # Lowered from 2000
        min_price: float = 0.12,             # Lowered from 0.15
        max_price: float = 0.88,             # Raised from 0.85
    ):
        self.min_1h_overreaction = min_1h_overreaction
        self.max_6h_trend = max_6h_trend
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_price = max_price

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate a market for mean reversion entry."""
        change_1h = signal.price_change_1h
        change_6h = signal.price_change_6h

        # Need a sharp 1h move (overreaction)
        if abs(change_1h) < self.min_1h_overreaction:
            return None

        # 6h trend should be moderate — the 1h spike is the outlier
        if abs(change_6h) > abs(change_1h) * 0.8:
            return None  # Not an overreaction, it's a sustained trend

        # Liquidity gate
        if signal.liquidity < self.min_liquidity:
            return None
        if signal.volume_24h < self.min_volume:
            return None

        # Fade the 1h move: if it spiked up, buy NO (expect reversion down)
        if change_1h > 0:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no
        else:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes

        # Price bounds
        if entry_price < self.min_price or entry_price > self.max_price:
            return None

        # Confidence
        confidence = 0.40

        # Bigger divergence between 1h and 6h = stronger reversion signal
        divergence = abs(change_1h) - abs(change_6h)
        if divergence > 0.05:
            confidence += 0.15
        elif divergence > 0.03:
            confidence += 0.10

        # 24h trend opposing the 1h move confirms overreaction
        if (change_1h > 0) != (signal.price_change_24h > 0):
            confidence += 0.10

        # High volume on the spike suggests institutional activity, less likely to revert
        if signal.liquidity > 0:
            vol_ratio = signal.volume_24h / signal.liquidity
            if vol_ratio > 2.0:
                confidence -= 0.10  # Penalize: high volume spikes may be real
            elif vol_ratio < 0.5:
                confidence += 0.05  # Low volume spike = more likely overreaction

        if signal.spread < 0.03:
            confidence += 0.05

        confidence = max(0.1, min(confidence, 0.80))

        # Tighter targets than momentum — reversion is partial
        target = entry_price + 0.03
        stop_loss = entry_price - 0.02

        target = min(target, 0.95)
        stop_loss = max(stop_loss, 0.05)

        ev = (confidence * (target - entry_price)) - ((1 - confidence) * (entry_price - stop_loss))

        if ev <= 0:
            return None

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="mean_reversion",
            entry_price=entry_price,
            target_exit_price=target,
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,
            reasoning=(
                f"MeanRev: 1h={change_1h:+.1%} vs 6h={change_6h:+.1%} "
                f"(divergence={divergence:.1%}), fading the spike"
            ),
        )
