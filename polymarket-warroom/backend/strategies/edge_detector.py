"""Edge Detector — calculates expected value and filters/ranks signals.

EV = (probability_of_win * payout) - (probability_of_loss * stake)
Only trade when EV > configurable threshold (default: 2%).
"""

import logging

from backend.models.trade import TradeSignal

logger = logging.getLogger(__name__)


class EdgeDetector:
    """Filter and rank trade signals by expected value."""

    def __init__(self, min_ev: float = 0.02):
        self.min_ev = min_ev

    def has_edge(self, signal: TradeSignal) -> bool:
        """Check if a signal has sufficient expected value."""
        return signal.expected_value >= self.min_ev

    def calculate_ev(self, signal: TradeSignal) -> float:
        """Recalculate EV from signal parameters."""
        win_amount = signal.target_exit_price - signal.entry_price
        loss_amount = signal.entry_price - signal.stop_loss_price

        if loss_amount <= 0:
            return 0.0

        ev = (signal.confidence * win_amount) - ((1 - signal.confidence) * loss_amount)
        return ev

    def rank_signals(self, signals: list[TradeSignal]) -> list[TradeSignal]:
        """Filter by minimum EV and rank by expected value descending."""
        filtered = [s for s in signals if self.has_edge(s)]
        return sorted(filtered, key=lambda s: s.expected_value, reverse=True)
