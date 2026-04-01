"""Application configuration loaded from environment variables."""

from enum import Enum
from pydantic_settings import BaseSettings


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    HALTED = "halted"


class Settings(BaseSettings):
    # Trading
    trading_mode: TradingMode = TradingMode.PAPER
    initial_balance: float = 10000.0

    # Polymarket
    polymarket_api_key: str = ""
    polymarket_wallet_private_key: str = ""

    # Risk Management
    max_position_pct: float = 0.05
    max_exposure_pct: float = 0.40
    daily_loss_limit_pct: float = 0.05
    min_ev_threshold: float = 0.02

    # Scanner
    scan_interval_seconds: int = 30
    min_liquidity: float = 5000.0
    min_volume_24h: float = 1000.0
    max_spread: float = 0.05

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./warroom.db"

    # Derived filter settings
    min_price: float = 0.05
    max_price: float = 0.95
    min_time_to_resolution_hours: int = 2

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
