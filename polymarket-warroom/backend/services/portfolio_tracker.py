"""Portfolio tracking service — P&L, positions, trade history."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from backend.config import settings
from backend.db.database import (
    PortfolioSnapshotRow,
    TradeRow,
    async_session,
)
from backend.models.portfolio import (
    Portfolio,
    PortfolioSnapshot,
    PortfolioStats,
    Position,
)
from backend.models.trade import Trade, TradeDirection, TradeMode, TradeStatus
from backend.services.paper_trading import PaperTradingEngine

logger = logging.getLogger(__name__)


class PortfolioTracker:
    """Tracks portfolio state, P&L, and generates analytics."""

    def __init__(self, paper_engine: PaperTradingEngine):
        self.paper_engine = paper_engine

    async def get_portfolio(self, current_prices: dict[str, float]) -> Portfolio:
        """Get current portfolio state."""
        positions = []
        positions_value = 0.0

        for trade in self.paper_engine.open_trades:
            current_price = current_prices.get(trade.market_id, trade.entry_price)

            if trade.direction == TradeDirection.BUY_YES:
                shares = trade.position_size / trade.entry_price
                pos_value = shares * current_price
                unrealized = pos_value - trade.position_size
            else:
                shares = trade.position_size / (1 - trade.entry_price)
                pos_value = shares * (1 - current_price)
                unrealized = pos_value - trade.position_size

            positions_value += pos_value

            positions.append(Position(
                trade_id=trade.id,
                market_id=trade.market_id,
                question=trade.question,
                direction=trade.direction.value,
                entry_price=trade.entry_price,
                current_price=current_price,
                position_size=trade.position_size,
                unrealized_pnl=unrealized,
                strategy=trade.strategy,
                opened_at=trade.opened_at,
            ))

        cash = self.paper_engine.cash
        total_value = cash + positions_value
        total_exposure = positions_value / total_value if total_value > 0 else 0.0

        # Get trade stats
        stats = await self._get_trade_stats()

        # Daily P&L
        daily_pnl = await self._get_daily_pnl()

        return Portfolio(
            total_value=total_value,
            cash=cash,
            positions_value=positions_value,
            open_positions=positions,
            total_exposure_pct=total_exposure,
            daily_pnl=daily_pnl,
            total_pnl=total_value - self.paper_engine.initial_balance,
            win_count=stats.get("wins", 0),
            loss_count=stats.get("losses", 0),
            total_trades=stats.get("total", 0),
        )

    async def get_trade_history(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> list[Trade]:
        """Get trade history from database."""
        try:
            async with async_session() as session:
                query = select(TradeRow).order_by(TradeRow.opened_at.desc())
                if status:
                    query = query.where(TradeRow.status == status)
                query = query.limit(limit).offset(offset)

                result = await session.execute(query)
                trades = []
                for row in result.scalars():
                    trades.append(Trade(
                        id=row.id,
                        market_id=row.market_id,
                        question=row.question,
                        direction=TradeDirection(row.direction),
                        entry_price=row.entry_price,
                        exit_price=row.exit_price,
                        position_size=row.position_size,
                        pnl=row.pnl,
                        status=TradeStatus(row.status),
                        mode=TradeMode(row.mode),
                        opened_at=row.opened_at,
                        closed_at=row.closed_at,
                        strategy=row.strategy,
                    ))
                return trades
        except Exception as e:
            logger.error(f"Failed to get trade history: {e}")
            return []

    async def take_snapshot(self, current_prices: dict[str, float]):
        """Take a portfolio snapshot for charting."""
        portfolio = await self.get_portfolio(current_prices)
        try:
            async with async_session() as session:
                row = PortfolioSnapshotRow(
                    total_value=portfolio.total_value,
                    cash=portfolio.cash,
                    positions_value=portfolio.positions_value,
                    timestamp=datetime.utcnow(),
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to take snapshot: {e}")

    async def get_snapshots(self, hours: int = 24) -> list[PortfolioSnapshot]:
        """Get portfolio snapshots for charting."""
        since = datetime.utcnow() - timedelta(hours=hours)
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(PortfolioSnapshotRow)
                    .where(PortfolioSnapshotRow.timestamp >= since)
                    .order_by(PortfolioSnapshotRow.timestamp)
                )
                return [
                    PortfolioSnapshot(
                        id=row.id,
                        total_value=row.total_value,
                        cash=row.cash,
                        positions_value=row.positions_value,
                        timestamp=row.timestamp,
                    )
                    for row in result.scalars()
                ]
        except Exception as e:
            logger.error(f"Failed to get snapshots: {e}")
            return []

    async def get_stats(self) -> PortfolioStats:
        """Calculate aggregate portfolio statistics."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(TradeRow).where(TradeRow.status.in_(["CLOSED", "STOPPED_OUT"]))
                )
                trades = list(result.scalars())

                if not trades:
                    return PortfolioStats()

                pnls = [t.pnl or 0 for t in trades]
                wins = [p for p in pnls if p > 0]
                losses = [p for p in pnls if p <= 0]

                # Strategy breakdown
                strategy_stats = {}
                for trade in trades:
                    strat = trade.strategy or "unknown"
                    if strat not in strategy_stats:
                        strategy_stats[strat] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
                    strategy_stats[strat]["trades"] += 1
                    strategy_stats[strat]["total_pnl"] += trade.pnl or 0
                    if (trade.pnl or 0) > 0:
                        strategy_stats[strat]["wins"] += 1

                for strat in strategy_stats:
                    s = strategy_stats[strat]
                    s["win_rate"] = s["wins"] / s["trades"] if s["trades"] > 0 else 0

                # Max drawdown
                max_drawdown = 0.0
                peak = 0.0
                cumulative = 0.0
                for pnl in pnls:
                    cumulative += pnl
                    peak = max(peak, cumulative)
                    drawdown = peak - cumulative
                    max_drawdown = max(max_drawdown, drawdown)

                # Sharpe ratio (simplified)
                import statistics
                avg_return = statistics.mean(pnls) if pnls else 0
                std_return = statistics.stdev(pnls) if len(pnls) > 1 else 1
                sharpe = (avg_return / std_return) if std_return > 0 else 0

                return PortfolioStats(
                    total_trades=len(trades),
                    win_rate=len(wins) / len(trades) if trades else 0,
                    avg_return=avg_return,
                    best_trade_pnl=max(pnls) if pnls else 0,
                    worst_trade_pnl=min(pnls) if pnls else 0,
                    sharpe_ratio=sharpe,
                    max_drawdown=max_drawdown,
                    strategy_breakdown=strategy_stats,
                )
        except Exception as e:
            logger.error(f"Failed to calculate stats: {e}")
            return PortfolioStats()

    async def _get_trade_stats(self) -> dict:
        """Get basic win/loss stats."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(TradeRow).where(TradeRow.status.in_(["CLOSED", "STOPPED_OUT"]))
                )
                trades = list(result.scalars())
                wins = sum(1 for t in trades if (t.pnl or 0) > 0)
                return {
                    "total": len(trades),
                    "wins": wins,
                    "losses": len(trades) - wins,
                }
        except Exception:
            return {"total": 0, "wins": 0, "losses": 0}

    async def _get_daily_pnl(self) -> float:
        """Get P&L for today."""
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
