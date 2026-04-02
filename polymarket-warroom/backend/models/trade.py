"""Trade data models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TradeDirection(str, Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"


class TradeSignal(BaseModel):
    """Output from the analyst — a recommended trade."""

    market_id: str
    direction: TradeDirection
    confidence: float  # 0.0 - 1.0
    strategy: str  # which strategy triggered
    entry_price: float
    target_exit_price: float
    stop_loss_price: float
    expected_value: float
    position_size_suggestion: float = 0.0  # in USDC, set by risk manager
    reasoning: str = ""


class ScalpCycleState(str, Enum):
    SCANNING = "scanning"
    ENTRY_PENDING = "entry_pending"
    FILLING = "filling"
    ACTIVE = "active"
    SCALING_OUT = "scaling_out"
    TRAILING = "trailing"
    STOPPED_OUT = "stopped_out"
    TIMED_OUT = "timed_out"
    STAGNATED = "stagnated"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class ScalpCycle(BaseModel):
    """Full state of a single scalp trade cycle."""

    cycle_id: str
    market_id: str
    state: ScalpCycleState = ScalpCycleState.SCANNING
    direction: str = ""  # BUY_YES or BUY_NO
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    peak_price: Optional[float] = None
    position_size: float = 0.0  # Original full position in USDC
    remaining_size: float = 0.0
    tp1_hit: bool = False
    tp2_hit: bool = False
    trailing_stop_level: Optional[float] = None
    hard_stop_level: Optional[float] = None
    pnl_realized: float = 0.0
    pnl_unrealized: float = 0.0
    entry_time: Optional[datetime] = None
    last_update: datetime = datetime.utcnow()
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    strategy_signals: list[str] = []


class CycleResult(BaseModel):
    """Post-mortem for a closed scalp cycle."""

    cycle_id: str
    duration_minutes: float
    total_pnl: float
    pnl_pct: float
    entry_price: float
    avg_exit_price: float
    peak_price: float
    max_drawdown_pct: float
    strategy_signals: list[str] = []
    exit_reason: str = ""
    tp1_hit: bool = False
    tp2_hit: bool = False
    trailing_used: bool = False


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    HALTED = "halted"
