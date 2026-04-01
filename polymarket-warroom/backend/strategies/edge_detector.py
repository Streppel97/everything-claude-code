"""Expected value calculator — only trade when EV is positive."""

import logging
from typing import Optional

from backend.models.trade import TradeSignal

logger = logging.getLogger(__name__)


class EdgeDetector:
    """Calculate expected value and filter signals by minimum EV threshold.

    EV = (probability_of_win * payout) - (probability_of_loss * stake)
    Only pass signals with EV > configurable threshold.
    """

    def __init__(self, min_ev: float = 0.02):
        self.min_ev = min_ev

    def has_edge(self, signal: TradeSignal) -> bool:
        """Check if a trade signal has positive expected value above threshold."""
        ev = self.calculate_ev(signal)
        return ev >= self.min_ev

    def calculate_ev(self, signal: TradeSignal) -> float:
        """Calculate expected value for a trade signal.

        Uses confidence as win probability, target/stop as payouts.
        """
        win_prob = signal.confidence
        loss_prob = 1 - win_prob

        # Win: entry → target
        win_payout = signal.target_exit_price - signal.entry_price

        # Loss: entry → stop_loss
        loss_amount = signal.entry_price - signal.stop_loss_price

        ev = (win_prob * win_payout) - (loss_prob * loss_amount)
        return ev

    def calculate_risk_reward(self, signal: TradeSignal) -> float:
        """Calculate risk/reward ratio."""
        reward = signal.target_exit_price - signal.entry_price
        risk = signal.entry_price - signal.stop_loss_price
        if risk <= 0:
            return 0.0
        return reward / risk

    def rank_signals(self, signals: list[TradeSignal]) -> list[TradeSignal]:
        """Rank signals by EV, filtering out those below threshold."""
        viable = []
        for s in signals:
            ev = self.calculate_ev(s)
            if ev >= self.min_ev:
                s.expected_value = ev
                viable.append(s)

        return sorted(viable, key=lambda x: x.expected_value, reverse=True)
