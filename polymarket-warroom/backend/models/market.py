"""Market data models."""

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field


class Market(BaseModel):
    """Polymarket market metadata."""

    id: str
    question: str
    category: str = ""
    outcome_yes_price: float = 0.5
    outcome_no_price: float = 0.5
    volume_24h: float = 0.0
    liquidity: float = 0.0
    spread: float = 0.0
    resolution_date: Optional[datetime] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    condition_id: str = ""
    slug: str = ""
    active: bool = True


class MarketSignal(BaseModel):
    """Output from the scanner agent for a flagged market."""

    market_id: str
    question: str
    category: str
    current_price_yes: float
    current_price_no: float
    volume_24h: float
    liquidity: float
    price_change_1h: float = 0.0
    price_change_6h: float = 0.0
    price_change_24h: float = 0.0
    spread: float
    time_to_resolution: timedelta = timedelta(hours=24)
    signal_strength: float = Field(ge=0.0, le=1.0)
    signal_direction: str  # "YES" or "NO"
    reasoning: str = ""


class OrderBookLevel(BaseModel):
    """Single level in the order book."""

    price: float
    size: float


class OrderBook(BaseModel):
    """Order book snapshot."""

    market_id: str
    bids: list[OrderBookLevel] = []
    asks: list[OrderBookLevel] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PriceHistory(BaseModel):
    """Historical price point."""

    market_id: str
    price_yes: float
    price_no: float
    volume: float = 0.0
    timestamp: datetime
