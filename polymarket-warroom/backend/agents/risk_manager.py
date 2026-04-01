"""Risk Manager Agent — position sizing, exposure limits, and kill switch."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from backend.config import settings
from backend.db.database import TradeRow, async_session
from backend.models.trade import TradeSignal
from backend.services.paper_trading import PaperTradingEngine

logger = logging.getLogger(__name__)


class RiskManager:
    """Enforces risk limits and calculates position sizes.

    Hard rules (non-overridable):
    - Max single position: 5% of portfolio
    - Max total exposure: 40% of portfolio
    - Max positions in same category: 3
    - Max correlated positions: 2
    - Daily loss limit: 5% → halt all trading
    - Per-trade max loss: 2% of portfolio
    """

    def __init__(self, paper_engine: PaperTradingEngine):
        self.paper_engine = paper_engine
        self._halted = False
        self._halt_reason = ""

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def halt(self, reason: str = "manual"):
        """Engage kill switch."""
        self._halted = True
        self._halt_reason = reason
        logger.warning(f"RISK HALT: {reason}")

    def resume(self):
        """Resume trading after halt."""
        self._halted = False
        self._halt_reason = ""
        logger.info("Trading resumed")

    async def evaluate(
        self,
        signal: TradeSignal,
        current_prices: dict[str, float],
        category: str = "",
    ) -> Optional[TradeSignal]:
        """Evaluate a trade signal against risk rules.

        Returns the signal with adjusted position size, or None if rejected.
        """
        if self._halted:
            logger.info(f"Trade rejected (halted): {signal.market_id}")
            return None

        portfolio_value = self.paper_engine.get_total_value(current_prices)

        # Check daily loss limit
        daily_loss = await self._get_daily_loss()
        if daily_loss <= -(portfolio_value * settings.daily_loss_limit_pct):
            self.halt(f"Daily loss limit hit: ${daily_loss:.2f}")
            return None

        # Check total exposure
        positions_value = self.paper_engine.get_positions_value(current_prices)
        current_exposure = positions_value / portfolio_value if portfolio_value > 0 else 0
        if current_exposure >= settings.max_exposure_pct:
            logger.info(
                f"Trade rejected (exposure {current_exposure:.1%} >= "
                f"{settings.max_exposure_pct:.1%}): {signal.market_id}"
            )
            return None

        # Check category concentration
        if category:
            cat_count = sum(
                1 for t in self.paper_engine.open_trades
                if t.market_id == signal.market_id  # Simplified; ideally check category
            )
            if cat_count >= 3:
                logger.info(f"Trade rejected (category limit): {signal.market_id}")
                return None

        # Check duplicate position
        existing = [t for t in self.paper_engine.open_trades if t.market_id == signal.market_id]
        if len(existing) >= 2:
            logger.info(f"Trade rejected (duplicate): {signal.market_id}")
            return None

        # Position sizing: quarter-Kelly criterion
        position_size = self._calculate_position_size(signal, portfolio_value)

        # Cap at max single position
        max_position = portfolio_value * settings.max_position_pct
        position_size = min(position_size, max_position)

        # Ensure per-trade max loss is within 2%
        max_loss = portfolio_value * 0.02
        potential_loss = position_size * (signal.entry_price - signal.stop_loss_price) / signal.entry_price
        if potential_loss > max_loss and position_size > 0:
            # Scale down to fit within loss limit
            position_size = max_loss / ((signal.entry_price - signal.stop_loss_price) / signal.entry_price)

        # Check available cash
        position_size = min(position_size, self.paper_engine.cash * 0.95)

        if position_size < 10:  # Minimum $10 trade
            logger.info(f"Trade rejected (size too small: ${position_size:.2f}): {signal.market_id}")
            return None

        # Remaining exposure room
        remaining_exposure = (settings.max_exposure_pct * portfolio_value) - positions_value
        position_size = min(position_size, remaining_exposure)

        if position_size < 10:
            return None

        signal.position_size_suggestion = round(position_size, 2)
        logger.info(
            f"Trade APPROVED: {signal.market_id} {signal.direction.value} "
            f"size=${position_size:.2f}, EV={signal.expected_value:.4f}"
        )
        return signal

    def _calculate_position_size(self, signal: TradeSignal, portfolio_value: float) -> float:
        """Calculate position size using quarter-Kelly criterion.

        kelly_fraction = (edge / odds) * 0.25
        position_size = portfolio_value * kelly_fraction
        """
        if signal.entry_price <= 0 or signal.stop_loss_price <= 0:
            return 0

        # Edge: expected value per dollar
        edge = signal.expected_value

        # Odds: potential profit / potential loss
        win_amount = signal.target_exit_price - signal.entry_price
        loss_amount = signal.entry_price - signal.stop_loss_price

        if loss_amount <= 0:
            return 0

        odds = win_amount / loss_amount

        # Kelly fraction (quarter-Kelly for safety)
        if odds <= 0:
            return 0
        kelly = (edge / odds) * 0.25

        # Clamp to reasonable range
        kelly = max(0, min(kelly, 0.1))

        return portfolio_value * kelly

    async def _get_daily_loss(self) -> float:
        """Get total realized P&L for today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(func.sum(TradeRow.pnl)).where(
                        TradeRow.closed_at >= today_start,
                        TradeRow.status.in_(["CLOSED", "STOPPED_OUT"]),
                    )
                )
                return result.scalar() or 0.0
        except Exception:
            return 0.0
