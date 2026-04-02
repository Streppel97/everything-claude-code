"""Scalping strategy — ultra-short-term trades targeting small, fast profits.

Scalping in prediction markets:
- Hold positions for minutes to hours, not days
- Target 1-3% profit per trade
- Tight stop-losses (0.5-1.5%)
- High trade frequency, small position sizes
- Enter on micro-momentum and exit at first sign of stall
"""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class ScalpingStrategy:
    """Ultra-short-term scalping for prediction markets.

    Entry criteria:
    - Tight spread (< 2%) for low slippage
    - Recent micro-momentum (1h change between 1-5%)
    - High liquidity for easy entry/exit
    - Price not at extremes (0.15-0.85)

    Exit criteria:
    - Target: 1-3% from entry
    - Stop-loss: 0.5-1.5% from entry
    - Time-based exit: close after max hold period even if flat
    """

    def __init__(
        self,
        min_1h_change: float = 0.005,   # Lowered from 0.01 — catch smaller moves
        max_1h_change: float = 0.10,    # Raised from 0.08 — allow bigger momentum
        max_spread: float = 0.03,       # Raised from 0.02 — more markets qualify
        min_liquidity: float = 5000,    # Lowered from 10000 — more markets qualify
        target_profit_pct: float = 0.02,
        stop_loss_pct: float = 0.01,
        min_price: float = 0.12,        # Lowered from 0.15
        max_price: float = 0.88,        # Raised from 0.85
    ):
        self.min_1h_change = min_1h_change
        self.max_1h_change = max_1h_change
        self.max_spread = max_spread
        self.min_liquidity = min_liquidity
        self.target_profit_pct = target_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_price = min_price
        self.max_price = max_price

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Evaluate a market for scalping entry."""
        change_1h = signal.price_change_1h

        # Need some movement but not too much (avoid chasing)
        if abs(change_1h) < self.min_1h_change:
            return None
        if abs(change_1h) > self.max_1h_change:
            return None

        # Tight spread is critical for scalping — slippage kills edge
        if signal.spread > self.max_spread:
            return None

        # Need high liquidity to enter and exit quickly
        if signal.liquidity < self.min_liquidity:
            return None

        # Determine direction: ride the micro-momentum
        if change_1h > 0:
            direction = TradeDirection.BUY_YES
            entry_price = signal.current_price_yes
        else:
            direction = TradeDirection.BUY_NO
            entry_price = signal.current_price_no

        # Avoid price extremes — not enough room to scalp
        if entry_price < self.min_price or entry_price > self.max_price:
            return None

        # Calculate confidence
        confidence = 0.4  # base for scalps

        # Tight spread boost
        if signal.spread < 0.01:
            confidence += 0.15

        # Volume confirms momentum
        if signal.liquidity > 0:
            vol_ratio = signal.volume_24h / signal.liquidity
            if vol_ratio > 0.3:
                confidence += 0.1
            if vol_ratio > 1.0:
                confidence += 0.1

        # Stronger momentum = more confidence
        if abs(change_1h) > self.min_1h_change * 2:
            confidence += 0.1

        # 6h trend agreement
        if (change_1h > 0 and signal.price_change_6h > 0) or \
           (change_1h < 0 and signal.price_change_6h < 0):
            confidence += 0.1

        confidence = min(confidence, 0.85)

        # Scalping targets: small and tight
        target = entry_price + self.target_profit_pct
        stop_loss = entry_price - self.stop_loss_pct

        # Clamp
        target = min(target, 0.95)
        stop_loss = max(stop_loss, 0.05)

        # EV calculation
        win_prob = confidence
        ev = (win_prob * (target - entry_price)) - ((1 - win_prob) * (entry_price - stop_loss))

        # Scalps need positive EV even with tight targets
        if ev <= 0:
            return None

        return TradeSignal(
            market_id=signal.market_id,
            direction=direction,
            confidence=confidence,
            strategy="scalping",
            entry_price=entry_price,
            target_exit_price=target,
            stop_loss_price=stop_loss,
            expected_value=ev,
            position_size_suggestion=0,  # Risk manager sets this
            reasoning=(
                f"Scalp: {change_1h:+.1%} 1h move, "
                f"spread={signal.spread:.3f}, "
                f"target={self.target_profit_pct:.1%}, "
                f"stop={self.stop_loss_pct:.1%}, "
                f"liq=${signal.liquidity:,.0f}"
            ),
        )
