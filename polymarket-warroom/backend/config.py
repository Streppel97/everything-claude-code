"""Global configuration for the Polymarket War Room."""

from pydantic import BaseModel, Field
from backend.models.trade import TradingMode


class ScalpCycleConfig(BaseModel):
    """Scalping cycle timing and constraints."""

    # Cycle timing
    min_cycle_duration: int = 5  # Minutes before exit allowed
    max_cycle_duration: int = 120  # Force exit after this
    scan_interval: int = 30  # Seconds between opportunity scans
    cooldown_after_loss: int = 10  # Minutes to pause after loss
    cooldown_after_streak_loss: int = 30  # Minutes after 3 consecutive losses
    max_concurrent_cycles: int = 5

    # Session limits
    max_cycles_per_hour: int = 12
    max_cycles_per_day: int = 100
    trading_session_hours: int = 16

    # Contract selection
    min_time_to_resolution_hours: int = 6
    max_time_to_resolution_days: int = 30
    target_price_min: float = 0.15
    target_price_max: float = 0.85


class ScalpEntryConditions(BaseModel):
    """ALL conditions must be True to enter a scalp."""

    min_liquidity: float = 5000
    min_order_book_depth: float = 500
    max_spread_pct: float = 0.03
    min_strategies_agreeing: int = 1
    min_composite_confidence: float = 0.65
    price_moving_in_direction: bool = True
    no_recent_reversal: bool = True
    volume_above_avg: bool = True
    not_near_resolution: bool = True
    not_at_price_extreme: bool = True
    no_active_position_same_market: bool = True
    daily_loss_limit_not_hit: bool = True


class TakeProfitConfig(BaseModel):
    """Multi-tier take profit levels."""

    # Tier 1: Quick profit
    tp1_target_pct: float = 0.02  # +2% price move
    tp1_exit_pct: float = 0.50  # Exit 50% of position

    # Tier 2: Extended profit
    tp2_target_pct: float = 0.05  # +5% price move
    tp2_exit_pct: float = 0.30  # Exit 30% of position

    # Tier 3: Trailing stop on remainder
    tp3_trailing_stop_pct: float = 0.015  # 1.5% below peak


class StopLossConfig(BaseModel):
    """Hard and conditional stop losses."""

    hard_stop_pct: float = 0.03  # -3% → immediate full exit
    stagnation_timeout_minutes: int = 45
    stagnation_threshold_pct: float = 0.005
    reversal_detection: bool = True
    reversal_lookback_minutes: int = 10
    reversal_threshold_pct: float = 0.015
    max_cycle_force_exit: bool = True


CIRCUIT_BREAKERS = {
    "daily_loss_limit": -0.05,  # -5% of portfolio → HALT
    "consecutive_losses": 5,  # 5 in a row → HALT 2h
    "hourly_loss_limit": -0.02,  # -2% last hour → HALT 1h
    "win_rate_floor": 0.40,  # Rolling 20-trade WR < 40% → HALT
    "max_drawdown_from_peak": -0.10,  # -10% from peak → HALT manual resume
    "api_errors_threshold": 3,  # 3 errors in 5 min → HALT
}


class Settings(BaseModel):
    """App-wide settings."""

    # Trading
    trading_mode: TradingMode = TradingMode.PAPER
    initial_balance: float = 10000.0
    scan_interval_seconds: int = 30

    # Risk limits
    max_position_pct: float = 0.05  # 5% of portfolio per position
    max_exposure_pct: float = 0.40  # 40% total exposure
    daily_loss_limit_pct: float = 0.05  # 5% daily loss halt
    min_ev_threshold: float = 0.02  # 2% minimum EV

    # Scanner filters
    scanner_min_liquidity: float = 5000.0
    scanner_max_spread: float = 0.05
    scanner_min_volume_24h: float = 1000.0
    scanner_min_time_hours: float = 2.0
    scanner_price_min: float = 0.05
    scanner_price_max: float = 0.95

    # Scalping
    scalp_config: ScalpCycleConfig = Field(default_factory=ScalpCycleConfig)
    scalp_entry: ScalpEntryConditions = Field(default_factory=ScalpEntryConditions)
    scalp_tp: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    scalp_sl: StopLossConfig = Field(default_factory=StopLossConfig)

    # Database
    database_url: str = "sqlite+aiosqlite:///warroom.db"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    polymarket_base_url: str = "https://gamma-api.polymarket.com"


settings = Settings()
