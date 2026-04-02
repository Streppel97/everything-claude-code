"""Scalp Cycle Engine — manages the full lifecycle of scalp trades.

This is the core money-making engine. Sub-strategies (momentum, mean reversion,
volume spike, edge detector) feed signals INTO the scalper. The scalper handles
all timing, entry, exit, TP, SL, and cycle management.

State machine:
SCANNING → ENTRY_PENDING → FILLING → ACTIVE → SCALING_OUT → TRAILING → CLOSED
"""

import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from backend.config import (
    CIRCUIT_BREAKERS,
    settings,
)
from backend.models.trade import CycleResult, ScalpCycle, ScalpCycleState, TradeDirection

logger = logging.getLogger(__name__)


class TrailingStopAction(str, Enum):
    HOLD = "hold"
    EXIT = "exit"


class TrailingStopEngine:
    """Tracks peak price and exits when price drops below trailing distance."""

    def __init__(self, trailing_pct: float = 0.015):
        self.trailing_pct = max(0.01, min(trailing_pct, 0.03))
        self.peak_price: float = 0.0
        self.stop_level: float = 0.0

    def activate(self, current_price: float):
        """Activate trailing stop at current price level."""
        self.peak_price = current_price
        self.stop_level = current_price * (1 - self.trailing_pct)

    def update(self, current_price: float) -> TrailingStopAction:
        """Update with new price tick. Returns HOLD or EXIT."""
        if current_price > self.peak_price:
            self.peak_price = current_price
            self.stop_level = self.peak_price * (1 - self.trailing_pct)
            return TrailingStopAction.HOLD

        if current_price <= self.stop_level:
            return TrailingStopAction.EXIT

        return TrailingStopAction.HOLD


class ScalpCycleManager:
    """Manages multiple concurrent scalp cycles through their state machine."""

    def __init__(self):
        self.active_cycles: dict[str, ScalpCycle] = {}
        self.trailing_stops: dict[str, TrailingStopEngine] = {}
        self.completed_cycles: list[CycleResult] = []
        self._consecutive_losses = 0
        self._cooldown_until: Optional[datetime] = None
        self._cycles_this_hour: list[datetime] = []
        self._cycles_today: list[datetime] = []
        self._session_start = datetime.utcnow()
        self._portfolio_peak: float = 0.0
        self._api_errors: list[datetime] = []
        self._halted = False
        self._halt_reason = ""

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    @property
    def open_cycle_count(self) -> int:
        return len(self.active_cycles)

    @property
    def win_rate(self) -> float:
        """Rolling win rate over last 20 completed cycles."""
        recent = self.completed_cycles[-20:]
        if not recent:
            return 0.0
        wins = sum(1 for c in recent if c.total_pnl > 0)
        return wins / len(recent)

    def in_cooldown(self) -> bool:
        """Check if we're in a loss cooldown period."""
        if self._cooldown_until and datetime.utcnow() < self._cooldown_until:
            return True
        self._cooldown_until = None
        return False

    def can_open_new_cycle(self) -> bool:
        """Check all preconditions for opening a new scalp cycle."""
        if self._halted:
            return False
        if self.in_cooldown():
            return False
        if self.open_cycle_count >= settings.scalp_config.max_concurrent_cycles:
            return False

        # Rate limits
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        self._cycles_this_hour = [t for t in self._cycles_this_hour if t > hour_ago]
        if len(self._cycles_this_hour) >= settings.scalp_config.max_cycles_per_hour:
            return False

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._cycles_today = [t for t in self._cycles_today if t > today_start]
        if len(self._cycles_today) >= settings.scalp_config.max_cycles_per_day:
            return False

        # Session duration limit
        session_hours = (now - self._session_start).total_seconds() / 3600
        if session_hours >= settings.scalp_config.trading_session_hours:
            return False

        return True

    def has_position_in_market(self, market_id: str) -> bool:
        """Check if there's already an active cycle in this market."""
        return any(
            c.market_id == market_id
            for c in self.active_cycles.values()
            if c.state not in (ScalpCycleState.CLOSED, ScalpCycleState.STOPPED_OUT,
                               ScalpCycleState.TIMED_OUT, ScalpCycleState.STAGNATED,
                               ScalpCycleState.ABANDONED, ScalpCycleState.CANCELLED)
        )

    def open_cycle(
        self,
        market_id: str,
        direction: str,
        entry_price: float,
        position_size: float,
        strategy_signals: list[str],
    ) -> Optional[ScalpCycle]:
        """Open a new scalp cycle."""
        if not self.can_open_new_cycle():
            return None
        if self.has_position_in_market(market_id):
            return None

        cycle_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow()

        hard_stop = entry_price * (1 - settings.scalp_sl.hard_stop_pct)

        cycle = ScalpCycle(
            cycle_id=cycle_id,
            market_id=market_id,
            state=ScalpCycleState.ACTIVE,
            direction=direction,
            entry_price=entry_price,
            current_price=entry_price,
            peak_price=entry_price,
            position_size=position_size,
            remaining_size=position_size,
            hard_stop_level=hard_stop,
            entry_time=now,
            last_update=now,
            strategy_signals=strategy_signals,
        )

        self.active_cycles[cycle_id] = cycle
        self._cycles_this_hour.append(now)
        self._cycles_today.append(now)

        logger.info(
            f"CYCLE OPEN [{cycle_id}]: {direction} {market_id} "
            f"@ {entry_price:.4f}, size=${position_size:.2f}, "
            f"hard_stop={hard_stop:.4f}"
        )

        return cycle

    def update_cycle(self, cycle_id: str, current_price: float) -> list[dict]:
        """Update a cycle with a new price tick. Returns list of exit actions."""
        cycle = self.active_cycles.get(cycle_id)
        if not cycle or cycle.state in (
            ScalpCycleState.CLOSED, ScalpCycleState.STOPPED_OUT,
            ScalpCycleState.TIMED_OUT, ScalpCycleState.STAGNATED,
            ScalpCycleState.ABANDONED, ScalpCycleState.CANCELLED,
        ):
            return []

        cycle.current_price = current_price
        cycle.last_update = datetime.utcnow()

        if current_price > (cycle.peak_price or 0):
            cycle.peak_price = current_price

        # Update unrealized P&L
        if cycle.entry_price and cycle.entry_price > 0:
            pnl_pct = (current_price - cycle.entry_price) / cycle.entry_price
            cycle.pnl_unrealized = cycle.remaining_size * pnl_pct

        actions = []

        # Priority 1: Hard stop loss
        action = self._check_hard_stop(cycle, current_price)
        if action:
            return [action]

        # Priority 2: Max cycle duration
        action = self._check_timeout(cycle)
        if action:
            return [action]

        # Priority 3: Momentum reversal
        action = self._check_reversal(cycle, current_price)
        if action:
            return [action]

        # Priority 4: Stagnation
        action = self._check_stagnation(cycle, current_price)
        if action:
            return [action]

        # Priority 5: Take profit tiers
        tp_actions = self._check_take_profits(cycle, current_price)
        actions.extend(tp_actions)

        # Priority 6: Trailing stop (after TP2)
        if cycle.state == ScalpCycleState.TRAILING:
            action = self._check_trailing_stop(cycle, current_price)
            if action:
                actions.append(action)

        return actions

    def _check_hard_stop(self, cycle: ScalpCycle, price: float) -> Optional[dict]:
        """Hard stop at -3% → immediate full exit."""
        if cycle.hard_stop_level and price <= cycle.hard_stop_level:
            return self._close_cycle(
                cycle, price, ScalpCycleState.STOPPED_OUT, "hard_stop",
                exit_size=cycle.remaining_size
            )
        return None

    def _check_timeout(self, cycle: ScalpCycle) -> Optional[dict]:
        """Force exit at max cycle duration."""
        if not cycle.entry_time:
            return None
        elapsed = (datetime.utcnow() - cycle.entry_time).total_seconds() / 60
        if elapsed >= settings.scalp_config.max_cycle_duration:
            return self._close_cycle(
                cycle, cycle.current_price or cycle.entry_price,
                ScalpCycleState.TIMED_OUT, "max_duration",
                exit_size=cycle.remaining_size
            )
        return None

    def _check_reversal(self, cycle: ScalpCycle, price: float) -> Optional[dict]:
        """Exit if price reversed significantly from recent peak."""
        if not settings.scalp_sl.reversal_detection:
            return None
        if not cycle.peak_price or cycle.peak_price <= 0:
            return None

        reversal_pct = (cycle.peak_price - price) / cycle.peak_price
        if reversal_pct >= settings.scalp_sl.reversal_threshold_pct:
            return self._close_cycle(
                cycle, price, ScalpCycleState.STOPPED_OUT, "momentum_reversal",
                exit_size=cycle.remaining_size
            )
        return None

    def _check_stagnation(self, cycle: ScalpCycle, price: float) -> Optional[dict]:
        """Exit if price hasn't moved enough in timeout period."""
        if not cycle.entry_time or not cycle.entry_price:
            return None

        elapsed_min = (datetime.utcnow() - cycle.entry_time).total_seconds() / 60
        if elapsed_min < settings.scalp_sl.stagnation_timeout_minutes:
            return None

        price_move = abs(price - cycle.entry_price) / cycle.entry_price
        if price_move < settings.scalp_sl.stagnation_threshold_pct:
            return self._close_cycle(
                cycle, price, ScalpCycleState.STAGNATED, "stagnation",
                exit_size=cycle.remaining_size
            )
        return None

    def _check_take_profits(self, cycle: ScalpCycle, price: float) -> list[dict]:
        """Multi-tier take profit exits."""
        if not cycle.entry_price:
            return []

        actions = []
        move_pct = (price - cycle.entry_price) / cycle.entry_price

        # TP1: +2% → exit 50% of position
        if not cycle.tp1_hit and move_pct >= settings.scalp_tp.tp1_target_pct:
            exit_size = cycle.position_size * settings.scalp_tp.tp1_exit_pct
            exit_size = min(exit_size, cycle.remaining_size)
            if exit_size > 0:
                cycle.tp1_hit = True
                cycle.state = ScalpCycleState.SCALING_OUT
                pnl = exit_size * move_pct
                cycle.pnl_realized += pnl
                cycle.remaining_size -= exit_size
                actions.append({
                    "type": "partial_exit",
                    "cycle_id": cycle.cycle_id,
                    "reason": "tp1",
                    "exit_size": exit_size,
                    "exit_price": price,
                    "pnl": pnl,
                })
                logger.info(
                    f"TP1 HIT [{cycle.cycle_id}]: +{move_pct:.1%}, "
                    f"exited ${exit_size:.2f}, pnl=${pnl:+.2f}"
                )

        # TP2: +5% → exit 30% of original position
        if cycle.tp1_hit and not cycle.tp2_hit and move_pct >= settings.scalp_tp.tp2_target_pct:
            exit_size = cycle.position_size * settings.scalp_tp.tp2_exit_pct
            exit_size = min(exit_size, cycle.remaining_size)
            if exit_size > 0:
                cycle.tp2_hit = True
                pnl = exit_size * move_pct
                cycle.pnl_realized += pnl
                cycle.remaining_size -= exit_size
                actions.append({
                    "type": "partial_exit",
                    "cycle_id": cycle.cycle_id,
                    "reason": "tp2",
                    "exit_size": exit_size,
                    "exit_price": price,
                    "pnl": pnl,
                })
                logger.info(
                    f"TP2 HIT [{cycle.cycle_id}]: +{move_pct:.1%}, "
                    f"exited ${exit_size:.2f}, pnl=${pnl:+.2f}"
                )

                # Activate trailing stop for remaining 20%
                if cycle.remaining_size > 0:
                    cycle.state = ScalpCycleState.TRAILING
                    trailing = TrailingStopEngine(settings.scalp_tp.tp3_trailing_stop_pct)
                    trailing.activate(price)
                    self.trailing_stops[cycle.cycle_id] = trailing
                    cycle.trailing_stop_level = trailing.stop_level
                    logger.info(
                        f"TRAILING ACTIVATED [{cycle.cycle_id}]: "
                        f"remaining=${cycle.remaining_size:.2f}, "
                        f"stop={trailing.stop_level:.4f}"
                    )

        return actions

    def _check_trailing_stop(self, cycle: ScalpCycle, price: float) -> Optional[dict]:
        """Check trailing stop on remaining position after TP2."""
        trailing = self.trailing_stops.get(cycle.cycle_id)
        if not trailing:
            return None

        action = trailing.update(price)
        cycle.trailing_stop_level = trailing.stop_level

        if action == TrailingStopAction.EXIT:
            return self._close_cycle(
                cycle, price, ScalpCycleState.CLOSED, "trailing_stop",
                exit_size=cycle.remaining_size
            )
        return None

    def _close_cycle(
        self,
        cycle: ScalpCycle,
        exit_price: float,
        state: ScalpCycleState,
        reason: str,
        exit_size: float = 0,
    ) -> dict:
        """Finalize a cycle closure."""
        now = datetime.utcnow()

        # Calculate final PnL on remaining
        if cycle.entry_price and cycle.entry_price > 0 and exit_size > 0:
            move_pct = (exit_price - cycle.entry_price) / cycle.entry_price
            final_pnl = exit_size * move_pct
            cycle.pnl_realized += final_pnl
        else:
            final_pnl = 0

        cycle.state = state
        cycle.exit_time = now
        cycle.exit_reason = reason
        cycle.remaining_size = 0
        cycle.current_price = exit_price

        # Build cycle result
        duration = 0.0
        if cycle.entry_time:
            duration = (now - cycle.entry_time).total_seconds() / 60

        max_drawdown = 0.0
        if cycle.peak_price and cycle.entry_price and cycle.entry_price > 0:
            # Simplified — in production, track min price too
            max_drawdown = 0.0

        avg_exit = exit_price  # Simplified for single-exit; multi-exit would average

        result = CycleResult(
            cycle_id=cycle.cycle_id,
            duration_minutes=duration,
            total_pnl=cycle.pnl_realized,
            pnl_pct=cycle.pnl_realized / cycle.position_size if cycle.position_size > 0 else 0,
            entry_price=cycle.entry_price or 0,
            avg_exit_price=avg_exit,
            peak_price=cycle.peak_price or 0,
            max_drawdown_pct=max_drawdown,
            strategy_signals=cycle.strategy_signals,
            exit_reason=reason,
            tp1_hit=cycle.tp1_hit,
            tp2_hit=cycle.tp2_hit,
            trailing_used=cycle.cycle_id in self.trailing_stops,
        )

        self.completed_cycles.append(result)

        # Update loss tracking
        if cycle.pnl_realized < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= 3:
                self._cooldown_until = now + timedelta(
                    minutes=settings.scalp_config.cooldown_after_streak_loss
                )
                logger.warning(
                    f"STREAK COOLDOWN: {self._consecutive_losses} consecutive losses, "
                    f"pausing for {settings.scalp_config.cooldown_after_streak_loss} min"
                )
            else:
                self._cooldown_until = now + timedelta(
                    minutes=settings.scalp_config.cooldown_after_loss
                )
        else:
            self._consecutive_losses = 0

        # Clean up
        self.active_cycles.pop(cycle.cycle_id, None)
        self.trailing_stops.pop(cycle.cycle_id, None)

        logger.info(
            f"CYCLE CLOSED [{cycle.cycle_id}]: {reason}, "
            f"pnl=${cycle.pnl_realized:+.2f} ({result.pnl_pct:+.1%}), "
            f"duration={duration:.1f}min"
        )

        return {
            "type": "cycle_closed",
            "cycle_id": cycle.cycle_id,
            "reason": reason,
            "state": state.value,
            "exit_price": exit_price,
            "exit_size": exit_size,
            "pnl": cycle.pnl_realized,
            "duration_minutes": duration,
        }

    def check_circuit_breakers(
        self,
        portfolio_value: float,
        daily_pnl: float,
        hourly_pnl: float,
    ) -> Optional[str]:
        """Check all circuit breakers. Returns halt reason or None."""
        if portfolio_value <= 0:
            return None

        # Track portfolio peak
        if portfolio_value > self._portfolio_peak:
            self._portfolio_peak = portfolio_value

        # Daily loss limit
        daily_pct = daily_pnl / portfolio_value
        if daily_pct <= CIRCUIT_BREAKERS["daily_loss_limit"]:
            reason = f"Daily loss limit: {daily_pct:.1%}"
            self._halt(reason)
            return reason

        # Hourly loss limit
        hourly_pct = hourly_pnl / portfolio_value
        if hourly_pct <= CIRCUIT_BREAKERS["hourly_loss_limit"]:
            reason = f"Hourly loss limit: {hourly_pct:.1%}"
            self._halt(reason)
            return reason

        # Consecutive losses
        if self._consecutive_losses >= CIRCUIT_BREAKERS["consecutive_losses"]:
            reason = f"Consecutive losses: {self._consecutive_losses}"
            self._halt(reason)
            return reason

        # Win rate floor
        if len(self.completed_cycles) >= 20:
            if self.win_rate < CIRCUIT_BREAKERS["win_rate_floor"]:
                reason = f"Win rate floor: {self.win_rate:.1%}"
                self._halt(reason)
                return reason

        # Max drawdown from peak
        if self._portfolio_peak > 0:
            drawdown = (portfolio_value - self._portfolio_peak) / self._portfolio_peak
            if drawdown <= CIRCUIT_BREAKERS["max_drawdown_from_peak"]:
                reason = f"Max drawdown: {drawdown:.1%} from peak"
                self._halt(reason)
                return reason

        # API errors
        now = datetime.utcnow()
        recent_errors = [t for t in self._api_errors if (now - t).total_seconds() < 300]
        self._api_errors = recent_errors
        if len(recent_errors) >= CIRCUIT_BREAKERS["api_errors_threshold"]:
            reason = f"API errors: {len(recent_errors)} in 5 min"
            self._halt(reason)
            return reason

        return None

    def record_api_error(self):
        """Record an API error for circuit breaker tracking."""
        self._api_errors.append(datetime.utcnow())

    def _halt(self, reason: str):
        self._halted = True
        self._halt_reason = reason
        logger.warning(f"CIRCUIT BREAKER: {reason}")

    def resume(self):
        """Manual resume after circuit breaker halt."""
        self._halted = False
        self._halt_reason = ""
        self._consecutive_losses = 0
        self._api_errors.clear()
        logger.info("Scalp cycle manager resumed")

    def get_aggregate_metrics(self) -> dict:
        """Get aggregate performance metrics."""
        if not self.completed_cycles:
            return {
                "total_cycles": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "avg_duration_min": 0.0,
                "total_pnl": 0.0,
            }

        wins = [c for c in self.completed_cycles if c.total_pnl > 0]
        losses = [c for c in self.completed_cycles if c.total_pnl <= 0]

        avg_win = sum(c.total_pnl for c in wins) / len(wins) if wins else 0
        avg_loss = sum(abs(c.total_pnl) for c in losses) / len(losses) if losses else 0
        gross_profit = sum(c.total_pnl for c in wins)
        gross_loss = sum(abs(c.total_pnl) for c in losses)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_duration = (
            sum(c.duration_minutes for c in self.completed_cycles) /
            len(self.completed_cycles)
        )

        # Strategy breakdown
        strategy_stats: dict[str, dict] = {}
        for cycle in self.completed_cycles:
            for strat in cycle.strategy_signals:
                if strat not in strategy_stats:
                    strategy_stats[strat] = {"trades": 0, "wins": 0, "pnl": 0.0}
                strategy_stats[strat]["trades"] += 1
                if cycle.total_pnl > 0:
                    strategy_stats[strat]["wins"] += 1
                strategy_stats[strat]["pnl"] += cycle.total_pnl

        return {
            "total_cycles": len(self.completed_cycles),
            "win_rate": len(wins) / len(self.completed_cycles),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "win_loss_ratio": avg_win / avg_loss if avg_loss > 0 else float("inf"),
            "profit_factor": profit_factor,
            "avg_duration_min": avg_duration,
            "total_pnl": sum(c.total_pnl for c in self.completed_cycles),
            "consecutive_losses": self._consecutive_losses,
            "strategy_breakdown": strategy_stats,
        }
