"""Trade and order models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradeDirection(str, Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"


class TradeMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class TradeSignal(BaseModel):
    """Output from the analyst agent recommending a trade."""

    market_id: str
    direction: TradeDirection
    confidence: float = Field(ge=0.0, le=1.0)
    strategy: str
    entry_price: float
    target_exit_price: float
    stop_loss_price: float
    expected_value: float
    position_size_suggestion: float
    reasoning: str = ""


class Trade(BaseModel):
    """An executed trade (paper or live)."""

    id: Optional[int] = None
    market_id: str
    question: str = ""
    direction: TradeDirection
    entry_price: float
    exit_price: Optional[float] = None
    position_size: float  # USDC
    pnl: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    mode: TradeMode = TradeMode.PAPER
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    strategy: str = ""
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None


class TradeRequest(BaseModel):
    """Manual trade request from CLI/UI."""

    market_id: str
    direction: TradeDirection
    amount: float
    price: Optional[float] = None  # None = market price
