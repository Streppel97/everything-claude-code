"""Analyst Agent — evaluates markets for entry signals using multiple strategies.

Scalping-first approach: prioritizes short-term scalping signals, then
falls back to swing strategies (momentum, mean reversion, volume spike).
"""

import logging
from collections import Counter
from typing import Optional

from backend.config import settings
from backend.models.market import MarketSignal
from backend.models.trade import TradeSignal
from backend.strategies.edge_detector import EdgeDetector
from backend.strategies.mean_reversion import MeanReversionStrategy
from backend.strategies.momentum import MomentumStrategy
from backend.strategies.scalping import ScalpingStrategy
from backend.strategies.volume_spike import VolumeSpikeStrategy

logger = logging.getLogger(__name__)


class AnalystAgent:
    """Evaluates flagged markets using multiple strategies and ranks by EV.

    Strategy priority:
    1. Scalping (primary) — short-term, tight targets, high frequency
    2. Momentum — trend following for stronger moves
    3. Mean Reversion — fade overreactions
    4. Volume Spike — breakout detection
    """

    def __init__(self):
        # Scalping is the primary strategy
        self.scalping = ScalpingStrategy()
        self.momentum = MomentumStrategy()
        self.mean_reversion = MeanReversionStrategy()
        self.volume_spike = VolumeSpikeStrategy()
        self.edge_detector = EdgeDetector(min_ev=settings.min_ev_threshold)
        self._last_signals: list[TradeSignal] = []
        self._analysis_count = 0

    @property
    def latest_signals(self) -> list[TradeSignal]:
        return self._last_signals.copy()

    @property
    def analysis_count(self) -> int:
        return self._analysis_count

    async def analyze(self, market_signals: list[MarketSignal]) -> list[TradeSignal]:
        """Run all strategies on flagged markets and return ranked trade signals."""
        self._analysis_count += 1
        all_trade_signals: list[TradeSignal] = []

        for ms in market_signals:
            signals = self._evaluate_with_all_strategies(ms)
            all_trade_signals.extend(signals)

        # Filter by EV and rank
        ranked = self.edge_detector.rank_signals(all_trade_signals)

        # Prioritize scalping signals — they should execute first
        scalp_signals = [s for s in ranked if s.strategy == "scalping"]
        other_signals = [s for s in ranked if s.strategy != "scalping"]
        ranked = scalp_signals + other_signals

        self._last_signals = ranked

        logger.info(
            f"Analysis #{self._analysis_count}: {len(market_signals)} markets → "
            f"{len(all_trade_signals)} raw signals → {len(ranked)} with positive EV "
            f"({len(scalp_signals)} scalps, {len(other_signals)} swing)"
        )

        return ranked

    def _evaluate_with_all_strategies(self, signal: MarketSignal) -> list[TradeSignal]:
        """Run a single market through all strategies.

        Volume spike is advisory only — it boosts confidence of other
        strategies but never produces its own trade signals (7% WR historically).
        """
        results = []

        # Active strategies that produce trade signals
        strategies = [
            ("scalping", self.scalping),
            ("momentum", self.momentum),
            ("mean_reversion", self.mean_reversion),
        ]

        for name, strategy in strategies:
            try:
                trade_signal = strategy.evaluate(signal)
                if trade_signal:
                    results.append(trade_signal)
            except Exception as e:
                logger.error(f"Strategy {name} error on {signal.market_id}: {e}")

        # Volume spike as advisory: boost confidence if volume anomaly detected
        try:
            has_vol_spike = self.volume_spike.has_volume_spike(signal)
            if has_vol_spike and results:
                for ts in results:
                    ts.confidence = min(ts.confidence + 0.08, 0.95)
                    ts.reasoning += "; VOL_SPIKE_BOOST"
        except Exception as e:
            logger.error(f"Volume spike check error on {signal.market_id}: {e}")

        # If multiple strategies agree on direction, boost the best one's confidence
        if len(results) > 1:
            directions = [s.direction for s in results]
            most_common = Counter(directions).most_common(1)[0]
            if most_common[1] > 1:
                agreeing = [s for s in results if s.direction == most_common[0]]
                best = max(agreeing, key=lambda s: s.expected_value)
                best.confidence = min(best.confidence + 0.1, 0.95)
                best.reasoning += "; MULTI-STRATEGY CONFIRMATION"

        return results

    async def analyze_single(self, signal: MarketSignal) -> Optional[TradeSignal]:
        """Analyze a single market and return best signal if any."""
        results = self._evaluate_with_all_strategies(signal)
        ranked = self.edge_detector.rank_signals(results)
        return ranked[0] if ranked else None
