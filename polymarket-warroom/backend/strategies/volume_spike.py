"""Volume Spike strategy — DISABLED for direct trading.

Analytics: 7% WR, -$486.19 over 15 trades. This strategy loses money
when trading directly. It now only produces ADVISORY signals that boost
confidence when other strategies agree, but never trades on its own.
"""

import logging
from typing import Optional

from backend.models.market import MarketSignal
from backend.models.trade import TradeDirection, TradeSignal

logger = logging.getLogger(__name__)


class VolumeSpikeStrategy:
    """Volume anomaly detector — ADVISORY ONLY, does not produce trade signals.

    Detects unusual volume without proportional price movement. Used only as
    a confirmation signal to boost other strategies' confidence. Never trades
    on its own due to 7% historical win rate.
    """

    def __init__(
        self,
        min_vol_ratio: float = 3.0,
        min_liquidity: float = 10000,
    ):
        self.min_vol_ratio = min_vol_ratio
        self.min_liquidity = min_liquidity

    def evaluate(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Always returns None — volume spike does NOT trade directly."""
        return None

    def has_volume_spike(self, signal: MarketSignal) -> bool:
        """Check if a market has a volume anomaly (used by other strategies)."""
        if signal.liquidity < self.min_liquidity:
            return False
        vol_ratio = signal.volume_24h / signal.liquidity if signal.liquidity > 0 else 0
        return vol_ratio >= self.min_vol_ratio
