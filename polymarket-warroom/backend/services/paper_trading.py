"""Paper Trading Engine — simulates trades with realistic slippage.

Default mode: all trades are paper. Tracks positions, P&L, and portfolio
value in real-time.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from backend.db.database import TradeRow, async_session
from backend.models.trade import TradeDirection

logger = logging.getLogger(__name__)

# Simulated slippage range
SLIPPAGE_MIN = 0.001
SLIPPAGE_MAX = 0.005


class OpenTrade:
    """In-memory representation of an open paper trade."""

    def __init__(
        self,
        id: int,
        market_id: str,
        question: str,
        direction: TradeDirection,
        entry_price: float,
        position_size: float,
        strategy: str = "",
        stop_loss: Optional[float] = None,
        target_price: Optional[float] = None,
        opened_at: Optional[datetime] = None,
    ):
        self.id = id
        self.market_id = market_id
        self.question = question
        self.direction = direction
        self.entry_price = entry_price
        self.position_size = position_size
        self.strategy = strategy
        self.stop_loss = stop_loss
        self.target_price = target_price
        self.opened_at = opened_at or datetime.utcnow()


class ClosedTrade:
    """Result of closing a paper trade."""

    def __init__(
        self,
        id: int,
        market_id: str,
        entry_price: float,
        exit_price: float,
        position_size: float,
        pnl: float,
        reason: str = "",
        question: str = "",
        direction: str = "",
        strategy: str = "",
        opened_at: Optional[datetime] = None,
        closed_at: Optional[datetime] = None,
    ):
        self.id = id
        self.market_id = market_id
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.position_size = position_size
        self.pnl = pnl
        self.reason = reason
        self.question = question
        self.direction = direction
        self.strategy = strategy
        self.opened_at = opened_at
        self.closed_at = closed_at or datetime.utcnow()


class PaperTradingEngine:
    """Simulates trading with paper money."""

    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.cash = initial_balance
        self.open_trades: list[OpenTrade] = []
        self._trade_counter = 0
        self._total_pnl = 0.0
        self._trade_history: list[ClosedTrade] = []

    @property
    def total_pnl(self) -> float:
        return self._total_pnl

    @property
    def trade_history(self) -> list[ClosedTrade]:
        return self._trade_history.copy()

    def get_total_value(self, current_prices: dict[str, float]) -> float:
        """Total portfolio value: cash + mark-to-market positions."""
        positions_value = self.get_positions_value(current_prices)
        return self.cash + positions_value

    def get_positions_value(self, current_prices: dict[str, float]) -> float:
        """Mark-to-market value of all open positions."""
        total = 0.0
        for trade in self.open_trades:
            current = current_prices.get(trade.market_id, trade.entry_price)
            if trade.direction == TradeDirection.BUY_YES:
                pnl_pct = (current - trade.entry_price) / trade.entry_price if trade.entry_price > 0 else 0
            else:
                pnl_pct = (trade.entry_price - current) / trade.entry_price if trade.entry_price > 0 else 0
            total += trade.position_size * (1 + pnl_pct)
        return total

    def has_position_in_market(self, market_id: str) -> bool:
        """Check if there's already an open position in this market."""
        return any(t.market_id == market_id for t in self.open_trades)

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
    ) -> Optional[OpenTrade]:
        """Execute a paper buy order."""
        # Duplicate prevention — one position per market
        if self.has_position_in_market(market_id):
            logger.warning(f"Duplicate blocked: already have position in {market_id}")
            return None

        if amount > self.cash:
            logger.warning(f"Insufficient cash: need ${amount:.2f}, have ${self.cash:.2f}")
            return None

        # Simulate slippage (adverse)
        import random
        slippage = random.uniform(SLIPPAGE_MIN, SLIPPAGE_MAX)
        fill_price = current_price * (1 + slippage)
        fill_price = min(fill_price, 0.99)

        self._trade_counter += 1
        trade_id = self._trade_counter

        trade = OpenTrade(
            id=trade_id,
            market_id=market_id,
            question=question,
            direction=direction,
            entry_price=fill_price,
            position_size=amount,
            strategy=strategy,
            stop_loss=stop_loss,
            target_price=target_price,
        )

        self.cash -= amount
        self.open_trades.append(trade)

        # Persist to DB
        await self._save_trade_open(trade)

        logger.info(
            f"PAPER BUY #{trade_id}: {direction.value} {market_id} "
            f"@ {fill_price:.4f}, size=${amount:.2f}"
        )

        return trade

    async def execute_sell(
        self, trade_id: int, current_price: float, reason: str = ""
    ) -> Optional[ClosedTrade]:
        """Close a paper position."""
        trade = next((t for t in self.open_trades if t.id == trade_id), None)
        if not trade:
            return None

        # Simulate slippage (adverse on exit too)
        import random
        slippage = random.uniform(SLIPPAGE_MIN, SLIPPAGE_MAX)
        fill_price = current_price * (1 - slippage)
        fill_price = max(fill_price, 0.01)

        # Calculate P&L
        if trade.direction == TradeDirection.BUY_YES:
            pnl_pct = (fill_price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - fill_price) / trade.entry_price

        pnl = trade.position_size * pnl_pct

        self.cash += trade.position_size + pnl
        self._total_pnl += pnl
        self.open_trades = [t for t in self.open_trades if t.id != trade_id]

        closed = ClosedTrade(
            id=trade_id,
            market_id=trade.market_id,
            entry_price=trade.entry_price,
            exit_price=fill_price,
            position_size=trade.position_size,
            pnl=pnl,
            reason=reason,
            question=trade.question,
            direction=trade.direction.value,
            strategy=trade.strategy,
            opened_at=trade.opened_at,
        )
        self._trade_history.append(closed)

        # Persist to DB
        await self._save_trade_close(trade_id, fill_price, pnl, reason)

        logger.info(
            f"PAPER SELL #{trade_id}: {trade.market_id} "
            f"@ {fill_price:.4f}, P&L=${pnl:+.2f} ({reason})"
        )

        return closed

    async def check_stop_losses(self, prices: dict[str, float]):
        """Check all open trades against their stop losses."""
        trades_to_close = []
        for trade in self.open_trades:
            if trade.stop_loss is None:
                continue
            current = prices.get(trade.market_id)
            if current is None:
                continue

            if trade.direction == TradeDirection.BUY_YES:
                if current <= trade.stop_loss:
                    trades_to_close.append((trade.id, current))
            else:
                if current >= (1 - trade.stop_loss):
                    trades_to_close.append((trade.id, current))

        for trade_id, price in trades_to_close:
            await self.execute_sell(trade_id, price, reason="stop_loss")

    async def check_take_profits(self, prices: dict[str, float]):
        """Check all open trades against their take profit targets."""
        trades_to_close = []
        for trade in self.open_trades:
            if trade.target_price is None:
                continue
            current = prices.get(trade.market_id)
            if current is None:
                continue

            if trade.direction == TradeDirection.BUY_YES:
                if current >= trade.target_price:
                    trades_to_close.append((trade.id, current))
            else:
                if current <= (1 - trade.target_price):
                    trades_to_close.append((trade.id, current))

        for trade_id, price in trades_to_close:
            await self.execute_sell(trade_id, price, reason="take_profit")

    async def _save_trade_open(self, trade: OpenTrade):
        """Persist a new trade to the database."""
        try:
            async with async_session() as session:
                row = TradeRow(
                    id=trade.id,
                    market_id=trade.market_id,
                    question=trade.question,
                    direction=trade.direction.value,
                    entry_price=trade.entry_price,
                    position_size=trade.position_size,
                    status="OPEN",
                    mode="PAPER",
                    opened_at=trade.opened_at,
                    strategy=trade.strategy,
                    stop_loss=trade.stop_loss,
                    target_price=trade.target_price,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")

    async def _save_trade_close(
        self, trade_id: int, exit_price: float, pnl: float, reason: str
    ):
        """Update a closed trade in the database."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(TradeRow).where(TradeRow.id == trade_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.exit_price = exit_price
                    row.pnl = pnl
                    row.status = "STOPPED_OUT" if reason == "stop_loss" else "CLOSED"
                    row.closed_at = datetime.utcnow()
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to update trade: {e}")
