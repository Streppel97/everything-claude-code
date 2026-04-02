"""Trade Post-Mortem Analysis — analyzes why trades went wrong and logs failures.

Tracks every closed trade, categorizes exit reasons, identifies patterns
in losses, and provides actionable insights to improve the system.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from backend.db.database import async_session, ActivityLogRow

logger = logging.getLogger(__name__)


class TradePostMortem:
    """Single trade analysis result."""

    def __init__(
        self,
        trade_id: int,
        market_id: str,
        question: str,
        strategy: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
        duration_minutes: float,
        diagnosis: str,
        category: str,
        opened_at: Optional[datetime] = None,
        closed_at: Optional[datetime] = None,
    ):
        self.trade_id = trade_id
        self.market_id = market_id
        self.question = question
        self.strategy = strategy
        self.direction = direction
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.pnl = pnl
        self.pnl_pct = pnl_pct
        self.reason = reason
        self.duration_minutes = duration_minutes
        self.diagnosis = diagnosis
        self.category = category  # "win", "small_loss", "big_loss", "timeout", "stagnation"
        self.opened_at = opened_at
        self.closed_at = closed_at


class PostMortemAnalyzer:
    """Analyzes closed trades and system failures to find improvement areas."""

    def __init__(self):
        self._post_mortems: list[TradePostMortem] = []
        self._system_failures: list[dict] = []
        self._max_history = 500

    @property
    def post_mortems(self) -> list[TradePostMortem]:
        return self._post_mortems.copy()

    @property
    def system_failures(self) -> list[dict]:
        return self._system_failures.copy()

    def analyze_trade(self, closed_trade) -> TradePostMortem:
        """Analyze a single closed trade and produce a post-mortem."""
        pnl_pct = 0.0
        if closed_trade.position_size > 0:
            pnl_pct = closed_trade.pnl / closed_trade.position_size

        duration = 0.0
        if closed_trade.opened_at and closed_trade.closed_at:
            duration = (closed_trade.closed_at - closed_trade.opened_at).total_seconds() / 60

        # Categorize the outcome
        category = self._categorize(closed_trade.pnl, pnl_pct, closed_trade.reason)

        # Diagnose what went wrong (or right)
        diagnosis = self._diagnose(closed_trade, pnl_pct, duration)

        pm = TradePostMortem(
            trade_id=closed_trade.id,
            market_id=closed_trade.market_id,
            question=closed_trade.question,
            strategy=closed_trade.strategy,
            direction=closed_trade.direction,
            entry_price=closed_trade.entry_price,
            exit_price=closed_trade.exit_price,
            pnl=closed_trade.pnl,
            pnl_pct=pnl_pct,
            reason=closed_trade.reason,
            duration_minutes=duration,
            diagnosis=diagnosis,
            category=category,
            opened_at=closed_trade.opened_at,
            closed_at=closed_trade.closed_at,
        )

        self._post_mortems.append(pm)
        if len(self._post_mortems) > self._max_history:
            self._post_mortems = self._post_mortems[-self._max_history:]

        # Log to DB
        self._persist_post_mortem(pm)

        return pm

    def record_system_failure(self, component: str, error: str, context: dict = None):
        """Record a system-level failure for analysis."""
        failure = {
            "timestamp": datetime.utcnow().isoformat(),
            "component": component,
            "error": error,
            "context": context or {},
        }
        self._system_failures.append(failure)
        if len(self._system_failures) > self._max_history:
            self._system_failures = self._system_failures[-self._max_history:]

        logger.error(f"SYSTEM FAILURE [{component}]: {error}")

        # Persist
        self._persist_failure(component, error)

    def get_loss_analysis(self) -> dict:
        """Analyze patterns in losing trades."""
        losses = [pm for pm in self._post_mortems if pm.pnl < 0]
        if not losses:
            return {"total_losses": 0, "patterns": []}

        # Group by strategy
        by_strategy = defaultdict(list)
        for pm in losses:
            by_strategy[pm.strategy].append(pm)

        # Group by exit reason
        by_reason = defaultdict(list)
        for pm in losses:
            by_reason[pm.reason].append(pm)

        # Group by category
        by_category = defaultdict(list)
        for pm in losses:
            by_category[pm.category].append(pm)

        # Identify patterns
        patterns = []

        # Check if a strategy is consistently losing
        for strat, trades in by_strategy.items():
            if len(trades) >= 3:
                total_loss = sum(t.pnl for t in trades)
                avg_loss = total_loss / len(trades)
                patterns.append({
                    "type": "strategy_bleeding",
                    "strategy": strat,
                    "count": len(trades),
                    "total_loss": total_loss,
                    "avg_loss": avg_loss,
                    "recommendation": f"Review {strat} filters — {len(trades)} losses totaling ${total_loss:.2f}",
                })

        # Check if stop losses are too tight (many small losses)
        stop_losses = by_reason.get("stop_loss", [])
        if len(stop_losses) >= 5:
            avg_loss_pct = sum(t.pnl_pct for t in stop_losses) / len(stop_losses)
            avg_duration = sum(t.duration_minutes for t in stop_losses) / len(stop_losses)
            if avg_duration < 10:
                patterns.append({
                    "type": "tight_stops",
                    "count": len(stop_losses),
                    "avg_loss_pct": avg_loss_pct,
                    "avg_duration_min": avg_duration,
                    "recommendation": "Stop losses may be too tight — most hit within 10 minutes",
                })

        # Check timeouts (stagnation = bad market selection)
        stagnated = by_reason.get("stagnation", []) + by_reason.get("scalp_timeout", [])
        if len(stagnated) >= 3:
            patterns.append({
                "type": "stagnation",
                "count": len(stagnated),
                "recommendation": "Too many stagnated trades — tighten volume/momentum filters at entry",
            })

        return {
            "total_losses": len(losses),
            "total_loss_amount": sum(pm.pnl for pm in losses),
            "by_strategy": {
                s: {"count": len(t), "total_pnl": sum(x.pnl for x in t)}
                for s, t in by_strategy.items()
            },
            "by_reason": {
                r: {"count": len(t), "total_pnl": sum(x.pnl for x in t)}
                for r, t in by_reason.items()
            },
            "patterns": patterns,
        }

    def get_full_report(self) -> dict:
        """Generate a full post-mortem report."""
        all_pms = self._post_mortems
        if not all_pms:
            return {
                "total_trades": 0,
                "loss_analysis": {"total_losses": 0, "patterns": []},
                "system_failures": [],
                "recent_post_mortems": [],
            }

        wins = [pm for pm in all_pms if pm.pnl > 0]
        losses = [pm for pm in all_pms if pm.pnl <= 0]

        return {
            "total_trades": len(all_pms),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(all_pms) if all_pms else 0,
            "total_pnl": sum(pm.pnl for pm in all_pms),
            "avg_win": sum(pm.pnl for pm in wins) / len(wins) if wins else 0,
            "avg_loss": sum(pm.pnl for pm in losses) / len(losses) if losses else 0,
            "avg_duration_min": sum(pm.duration_minutes for pm in all_pms) / len(all_pms),
            "loss_analysis": self.get_loss_analysis(),
            "system_failures": self._system_failures[-20:],
            "recent_post_mortems": [
                {
                    "trade_id": pm.trade_id,
                    "question": pm.question,
                    "strategy": pm.strategy,
                    "direction": pm.direction,
                    "pnl": pm.pnl,
                    "pnl_pct": pm.pnl_pct,
                    "reason": pm.reason,
                    "duration_min": pm.duration_minutes,
                    "diagnosis": pm.diagnosis,
                    "category": pm.category,
                    "closed_at": pm.closed_at.isoformat() if pm.closed_at else None,
                }
                for pm in all_pms[-30:]
            ],
        }

    def _categorize(self, pnl: float, pnl_pct: float, reason: str) -> str:
        """Categorize a trade outcome."""
        if pnl > 0:
            return "win"
        if reason in ("stagnation", "scalp_timeout"):
            return "stagnation"
        if reason == "stop_loss":
            return "stop_loss"
        if abs(pnl_pct) < 0.01:
            return "breakeven"
        if abs(pnl_pct) > 0.03:
            return "big_loss"
        return "small_loss"

    def _diagnose(self, trade, pnl_pct: float, duration: float) -> str:
        """Generate a human-readable diagnosis."""
        parts = []

        if trade.pnl > 0:
            parts.append(f"WIN: +{pnl_pct:.1%} in {duration:.0f}min via {trade.reason}")
            if duration < 5:
                parts.append("Quick scalp — ideal execution")
            return "; ".join(parts)

        # Loss diagnosis
        if trade.reason == "stop_loss":
            if duration < 5:
                parts.append("STOP HIT FAST: Price moved against immediately — possible bad entry timing")
            elif duration < 15:
                parts.append("STOP HIT: Moderate duration — entry signal may have been stale")
            else:
                parts.append("STOP HIT: Extended hold before stop — trend reversed")

        elif trade.reason in ("stagnation", "scalp_timeout"):
            parts.append("STAGNATION: No price movement — market was too quiet for this strategy")
            parts.append("Consider: higher min_volume or stronger momentum requirement at entry")

        elif trade.reason == "momentum_reversal":
            parts.append("REVERSAL: Price initially moved favorably then reversed")
            parts.append("Consider: tighter trailing stop or earlier TP1")

        elif trade.reason == "max_duration":
            parts.append("TIMEOUT: Held to max cycle duration without hitting TP or SL")

        elif trade.reason == "manual":
            parts.append(f"MANUAL EXIT: User closed at {pnl_pct:+.1%}")

        else:
            parts.append(f"EXIT ({trade.reason}): {pnl_pct:+.1%} in {duration:.0f}min")

        if abs(pnl_pct) > 0.03:
            parts.append("LARGE LOSS — review position sizing and stop levels")

        return "; ".join(parts)

    def _persist_post_mortem(self, pm: TradePostMortem):
        """Fire-and-forget DB persistence."""
        import asyncio
        try:
            asyncio.get_event_loop().create_task(self._save_pm(pm))
        except RuntimeError:
            pass

    def _persist_failure(self, component: str, error: str):
        """Fire-and-forget DB persistence."""
        import asyncio
        try:
            asyncio.get_event_loop().create_task(self._save_failure(component, error))
        except RuntimeError:
            pass

    async def _save_pm(self, pm: TradePostMortem):
        try:
            async with async_session() as session:
                row = ActivityLogRow(
                    agent="post_mortem",
                    message=f"[{pm.category}] #{pm.trade_id} {pm.strategy} {pm.direction}: "
                            f"pnl=${pm.pnl:+.2f} ({pm.pnl_pct:+.1%}), "
                            f"reason={pm.reason}, {pm.diagnosis}",
                    timestamp=datetime.utcnow(),
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.debug(f"Failed to persist post-mortem: {e}")

    async def _save_failure(self, component: str, error: str):
        try:
            async with async_session() as session:
                row = ActivityLogRow(
                    agent="system_failure",
                    message=f"[{component}] {error}",
                    timestamp=datetime.utcnow(),
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.debug(f"Failed to persist system failure: {e}")
