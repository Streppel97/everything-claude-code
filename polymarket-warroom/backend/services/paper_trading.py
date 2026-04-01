"""Paper trading engine — simulates order fills and tracks portfolio."""

import logging
import random
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from backend.config import settings
from backend.db.database import TradeRow, async_session
from backend.models.trade import Trade, TradeDirection, TradeMode, TradeStatus

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Simulates trade execution with realistic fills."""

    def __init__(self, initial_balance: Optional[float] = None):
        self.cash = initial_balance or settings.initial_balance
        self.initial_balance = self.cash
        self._open_trades: dict[int, Trade] = {}
        self._trade_counter = 0

    async def initialize(self):
        """Load open trades from database."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(TradeRow).where(
                        TradeRow.status == "OPEN",
                        TradeRow.mode == "PAPER",
                    )
                )
                for row in result.scalars():
                    trade = Trade(
                        id=row.id,
                        market_id=row.market_id,
                        question=row.question,
                        direction=TradeDirection(row.direction),
                        entry_price=row.entry_price,
                        position_size=row.position_size,
                        status=TradeStatus.OPEN,
                        mode=TradeMode.PAPER,
                        opened_at=row.opened_at,
                        strategy=row.strategy,
                        stop_loss=row.stop_loss,
                        target_price=row.target_price,
                    )
                    self._open_trades[row.id] = trade
                    self.cash -= row.position_size

                logger.info(f"Loaded {len(self._open_trades)} open paper trades")
        except Exception as e:
            logger.error(f"Failed to load open trades: {e}")

    async def execute_buy(
        self,
        market_id: str,
        direction: TradeDirection,
        amount: float,
        current_price: float,
        question: str = "",
        strategy: str = "",
        stop_loss: Optional[float] = None,
        target_price: Optional[float] = None,
    ) -> Optional[Trade]:
        """Execute a paper buy order with simulated slippage."""
        if amount > self.cash:
            logger.warning(f"Insufficient cash: {self.cash:.2f} < {amount:.2f}")
            return None

        # Simulate slippage (0.1% - 0.5%)
        slippage = random.uniform(0.001, 0.005)
        fill_price = current_price * (1 + slippage)
        fill_price = min(fill_price, 0.99)  # Cap at 0.99

        trade = Trade(
            market_id=market_id,
            question=question,
            direction=direction,
            entry_price=fill_price,
            position_size=amount,
            status=TradeStatus.OPEN,
            mode=TradeMode.PAPER,
            opened_at=datetime.utcnow(),
            strategy=strategy,
            stop_loss=stop_loss,
            target_price=target_price,
        )

        # Persist to database
        try:
            async with async_session() as session:
                row = TradeRow(
                    market_id=trade.market_id,
                    question=trade.question,
                    direction=trade.direction.value,
                    entry_price=trade.entry_price,
                    position_size=trade.position_size,
                    status=trade.status.value,
                    mode=trade.mode.value,
                    opened_at=trade.opened_at,
                    strategy=trade.strategy,
                    stop_loss=trade.stop_loss,
                    target_price=trade.target_price,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                trade.id = row.id
        except Exception as e:
            logger.error(f"Failed to persist trade: {e}")
            return None

        self._open_trades[trade.id] = trade
        self.cash -= amount

        logger.info(
            f"Paper BUY: {direction.value} {market_id} @ {fill_price:.4f}, "
            f"size=${amount:.2f}, slippage={slippage:.3%}"
        )
        return trade

    async def execute_sell(
        self,
        trade_id: int,
        current_price: float,
        reason: str = "manual",
    ) -> Optional[Trade]:
        """Close a paper position."""
        trade = self._open_trades.get(trade_id)
        if not trade:
            logger.warning(f"Trade {trade_id} not found in open positions")
            return None

        # Simulate slippage on exit
        slippage = random.uniform(0.001, 0.005)
        exit_price = current_price * (1 - slippage)
        exit_price = max(exit_price, 0.01)

        # Calculate P&L
        if trade.direction == TradeDirection.BUY_YES:
            # Bought YES tokens: profit if price went up
            shares = trade.position_size / trade.entry_price
            pnl = shares * (exit_price - trade.entry_price)
        else:
            # Bought NO tokens: profit if YES price went down
            shares = trade.position_size / (1 - trade.entry_price)
            pnl = shares * (trade.entry_price - exit_price)

        status = TradeStatus.STOPPED_OUT if reason == "stop_loss" else TradeStatus.CLOSED

        trade.exit_price = exit_price
        trade.pnl = pnl
        trade.status = status
        trade.closed_at = datetime.utcnow()

        # Update database
        try:
            async with async_session() as session:
                await session.execute(
                    update(TradeRow)
                    .where(TradeRow.id == trade_id)
                    .values(
                        exit_price=exit_price,
                        pnl=pnl,
                        status=status.value,
                        closed_at=trade.closed_at,
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update trade: {e}")

        # Return cash + P&L
        self.cash += trade.position_size + pnl
        del self._open_trades[trade_id]

        logger.info(
            f"Paper SELL: trade #{trade_id} @ {exit_price:.4f}, "
            f"P&L=${pnl:+.2f} ({reason})"
        )
        return trade

    async def check_stop_losses(self, prices: dict[str, float]):
        """Check all open positions for stop-loss triggers."""
        trades_to_close = []

        for trade_id, trade in self._open_trades.items():
            if trade.stop_loss is None:
                continue

            current_price = prices.get(trade.market_id)
            if current_price is None:
                continue

            triggered = False
            if trade.direction == TradeDirection.BUY_YES:
                if current_price <= trade.stop_loss:
                    triggered = True
            else:
                if current_price >= (1 - trade.stop_loss):
                    triggered = True

            if triggered:
                trades_to_close.append((trade_id, current_price))

        for trade_id, price in trades_to_close:
            await self.execute_sell(trade_id, price, reason="stop_loss")

    async def check_take_profits(self, prices: dict[str, float]):
        """Check all open positions for take-profit triggers."""
        trades_to_close = []

        for trade_id, trade in self._open_trades.items():
            if trade.target_price is None:
                continue

            current_price = prices.get(trade.market_id)
            if current_price is None:
                continue

            triggered = False
            if trade.direction == TradeDirection.BUY_YES:
                if current_price >= trade.target_price:
                    triggered = True
            else:
                if current_price <= (1 - trade.target_price):
                    triggered = True

            if triggered:
                trades_to_close.append((trade_id, current_price))

        for trade_id, price in trades_to_close:
            await self.execute_sell(trade_id, price, reason="take_profit")

    @property
    def open_trades(self) -> list[Trade]:
        return list(self._open_trades.values())

    @property
    def open_trade_count(self) -> int:
        return len(self._open_trades)

    def get_positions_value(self, prices: dict[str, float]) -> float:
        """Calculate total value of open positions at current prices."""
        total = 0.0
        for trade in self._open_trades.values():
            current_price = prices.get(trade.market_id, trade.entry_price)
            if trade.direction == TradeDirection.BUY_YES:
                shares = trade.position_size / trade.entry_price
                total += shares * current_price
            else:
                shares = trade.position_size / (1 - trade.entry_price)
                total += shares * (1 - current_price)
        return total

    def get_total_value(self, prices: dict[str, float]) -> float:
        """Get total portfolio value (cash + positions)."""
        return self.cash + self.get_positions_value(prices)
