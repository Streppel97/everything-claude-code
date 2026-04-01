"""Volume spike strategy — detect unusual volume as breakout precursor."""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class VolumeSpikeStrategy:
    """Detect unusual volume without proportional price movement.

    High volume + low price change = accumulation/distribution phase,
    suggesting a pending breakout.
    """

    def __init__(
        self,
        min_volume: float = 10000,
        volume_liquidity_ratio: float = 0.8,
        max_price_change: float = 0.02,
    ):
        self.min_volume = min_volume
        self.volume_liquidity_ratio = volume_liquidity_ratio
        self.max_price_change = max_price_change

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate market for volume spike signal."""
        if signal.volume_24h < self.min_volume:
            return None

        if signal.liquidity <= 0:
            return None

        vol_ratio = signal.volume_24h / signal.liquidity

        # Need high volume relative to liquidity
        if vol_ratio < self.volume_liquidity_ratio:
            return None

        # But price hasn't moved much (accumulation phase)
        if abs(signal.price_change_1h) > self.max_price_change:
            return None

        # Direction: lean toward YES if price is below 0.5, NO if above
        # (assumption: smart money is accumulating the undervalued side)
        if signal.current_price_yes < 0.5:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes
        else:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no

        # Confidence based on volume spike magnitude
        confidence = 0.3
        if vol_ratio > 1.5:
            confidence += 0.2
        if vol_ratio > 3.0:
            confidence += 0.1
        if signal.spread < 0.02:
            confidence += 0.1
        if signal.liquidity > 30000:
            confidence += 0.1

        confidence = min(confidence, 0.80)

        # Targets: expect a 5-15% move on breakout
        breakout_move = 0.05 + (vol_ratio - self.volume_liquidity_ratio) * 0.02
        breakout_move = min(breakout_move, 0.15)

        target = min(entry_price + breakout_move, 0.95)
        stop_loss = max(entry_price - breakout_move * 0.5, 0.02)

        ev = (confidence * (target - entry_price)) - ((1 - confidence) * (entry_price - stop_loss))

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
                f"Volume spike: ${signal.volume_24h:,.0f} volume, "
                f"ratio={vol_ratio:.1f}x, price stable ({signal.price_change_1h:+.1%})"
            ),
        )
