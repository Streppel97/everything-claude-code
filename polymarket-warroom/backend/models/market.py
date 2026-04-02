"""Market data models."""

from datetime import timedelta
from pydantic import BaseModel


class MarketSignal(BaseModel):
    """Output from the scanner — one per flagged market."""

    market_id: str
    question: str
    category: str = ""
    current_price_yes: float  # 0.00 - 1.00
    current_price_no: float
    volume_24h: float
    liquidity: float
    price_change_1h: float
    price_change_6h: float
    price_change_24h: float
    spread: float  # bid-ask spread
    time_to_resolution: timedelta = timedelta(days=30)
    signal_strength: float = 0.0  # 0.0 - 1.0 composite score
    signal_direction: str = ""  # "YES" or "NO"
    reasoning: str = ""


class PolymarketData(BaseModel):
    """Raw market data from the Polymarket API."""

    condition_id: str
    question: str
    slug: str = ""
    category: str = ""
    outcome_yes_price: float = 0.5
    outcome_no_price: float = 0.5
    volume_24h: float = 0.0
    liquidity: float = 0.0
    spread: float = 0.0
    end_date: str = ""
    active: bool = True
