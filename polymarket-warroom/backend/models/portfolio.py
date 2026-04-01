"""Portfolio state models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    """An open position in the portfolio."""

    trade_id: int
    market_id: str
    question: str
    direction: str
    entry_price: float
    current_price: float = 0.0
    position_size: float
    unrealized_pnl: float = 0.0
    strategy: str = ""
    opened_at: datetime = Field(default_factory=datetime.utcnow)


class Portfolio(BaseModel):
    """Current portfolio state."""

    total_value: float = 10000.0
    cash: float = 10000.0
    positions_value: float = 0.0
    open_positions: list[Position] = []
    total_exposure_pct: float = 0.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.win_count / self.total_trades


class PortfolioSnapshot(BaseModel):
    """Point-in-time portfolio snapshot for charting."""

    id: Optional[int] = None
    total_value: float
    cash: float
    positions_value: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PortfolioStats(BaseModel):
    """Aggregate portfolio statistics."""

    total_trades: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    strategy_breakdown: dict[str, dict] = {}
