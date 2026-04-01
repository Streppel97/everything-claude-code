"""Executor Agent — orchestrates the full pipeline: scan → analyze → risk → trade.

Scalping-aware: checks exits more aggressively, enforces time-based exits,
and limits concurrent positions to leave room for new scalps.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.agents.analyst import AnalystAgent
from backend.agents.risk_manager import RiskManager
from backend.agents.scanner import ScannerAgent
from backend.config import TradingMode, settings
from backend.db.database import SignalRow, async_session
from backend.models.trade import TradeDirection, TradeSignal
from backend.services.paper_trading import PaperTradingEngine
from backend.services.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

# Scalping config
MAX_SCALP_HOLD_MINUTES = 120  # Force-close scalps after 2 hours
MAX_CONCURRENT_SCALPS = 5     # Don't overload with too many scalps
SCALP_EXIT_CHECK_INTERVAL = 10  # Check exits every 10 seconds


class ExecutorAgent:
    """Orchestrates the full trading pipeline with scalping focus.

    Pipeline: Scanner → Analyst → Risk Manager → Executor
    Scalping additions:
    - More frequent exit checks
    - Time-based forced exits for stale scalps
    - Position count limits to preserve capital for new opportunities
    """

    def __init__(
        self,
        client: PolymarketClient,
        paper_engine: PaperTradingEngine,
        scanner: ScannerAgent,
        analyst: AnalystAgent,
        risk_manager: RiskManager,
    ):
        self.client = client
        self.paper_engine = paper_engine
        self.scanner = scanner
        self.analyst = analyst
        self.risk_manager = risk_manager
        self._running = False
        self._activity_log: list[dict] = []
        self._max_log_size = 500
        self._callbacks: list = []

    def on_activity(self, callback):
        """Register callback for activity log events."""
        self._callbacks.append(callback)

    @property
    def activity_log(self) -> list[dict]:
        return self._activity_log.copy()

    @property
    def is_running(self) -> bool:
        return self._running

    async def run_pipeline_once(self) -> list[dict]:
        """Execute one full pipeline cycle."""
        cycle_results = []

        # Step 1: Scan
        self._log("scanner", "Scanning markets...")
        market_signals = await self.scanner.scan_once()
        self._log(
            "scanner",
            f"{len(market_signals)} signals from "
            f"{self.scanner.scan_count} scans"
        )

        if not market_signals:
            return cycle_results

        # Step 2: Analyze (scalping-first)
        self._log("analyst", f"Analyzing {len(market_signals)} market signals...")
        trade_signals = await self.analyst.analyze(market_signals)
        scalp_count = sum(1 for s in trade_signals if s.strategy == "scalping")
        self._log("analyst", f"{len(trade_signals)} signals ({scalp_count} scalps)")

        if not trade_signals:
            return cycle_results

        # Step 3: Check exits BEFORE entering new positions
        current_prices = {
            ms.market_id: ms.current_price_yes for ms in market_signals
        }
        await self._check_all_exits(current_prices)

        # Step 4: Risk check + execute new entries
        # Count current scalps
        current_scalps = sum(
            1 for t in self.paper_engine.open_trades if t.strategy == "scalping"
        )

        for signal in trade_signals[:5]:  # Top 5 per cycle
            # Limit concurrent scalps
            if signal.strategy == "scalping" and current_scalps >= MAX_CONCURRENT_SCALPS:
                self._log("risk", f"Scalp limit reached ({MAX_CONCURRENT_SCALPS}), skipping")
                continue

            approved = await self.risk_manager.evaluate(signal, current_prices)
            if not approved:
                self._log("risk", f"REJECTED: {signal.market_id} ({signal.strategy})")
                continue

            self._log("risk", f"APPROVED: {signal.market_id}, size=${approved.position_size_suggestion:.2f}")

            result = await self._execute_trade(approved, current_prices)
            if result:
                cycle_results.append(result)
                if signal.strategy == "scalping":
                    current_scalps += 1

        return cycle_results

    async def start(self, interval: Optional[int] = None):
        """Start continuous pipeline execution."""
        interval = interval or settings.scan_interval_seconds
        self._running = True
        self._log("executor", f"Pipeline started (scalping mode), interval={interval}s")

        # Run exit checks more frequently than scan cycles
        exit_check_counter = 0

        while self._running:
            if self.risk_manager.is_halted:
                self._log("executor", f"Trading halted: {self.risk_manager.halt_reason}")
                await asyncio.sleep(interval)
                continue

            try:
                # Full pipeline every scan interval
                results = await self.run_pipeline_once()
                if results:
                    self._log("executor", f"Executed {len(results)} trades this cycle")
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                self._log("executor", f"ERROR: {e}")

            # Between scans, check exits more frequently for scalps
            for _ in range(max(1, interval // SCALP_EXIT_CHECK_INTERVAL - 1)):
                if not self._running:
                    break
                await asyncio.sleep(SCALP_EXIT_CHECK_INTERVAL)
                try:
                    await self._quick_exit_check()
                except Exception as e:
                    logger.error(f"Exit check error: {e}")

    def stop(self):
        """Stop the pipeline."""
        self._running = False
        self._log("executor", "Pipeline stopped")

    async def halt(self):
        """Kill switch — stop all trading and cancel orders."""
        self.risk_manager.halt("Kill switch engaged")
        self._running = False
        self._log("executor", "KILL SWITCH — all trading halted")

        if settings.trading_mode == TradingMode.LIVE:
            try:
                await self.client.cancel_all_orders()
                self._log("executor", "All open orders cancelled")
            except Exception as e:
                logger.error(f"Failed to cancel orders: {e}")

    def resume(self):
        """Resume after halt."""
        self.risk_manager.resume()
        self._log("executor", "Trading resumed")

    async def manual_buy(
        self,
        market_id: str,
        direction: str,
        amount: float,
    ) -> Optional[dict]:
        """Execute a manual trade."""
        try:
            dir_enum = TradeDirection(direction)
        except ValueError:
            dir_enum = TradeDirection.BUY_YES if direction.upper() in ("YES", "BUY_YES") else TradeDirection.BUY_NO

        market = await self.client.get_market(market_id)
        if not market:
            self._log("executor", f"Market not found: {market_id}")
            return None

        price = market.outcome_yes_price if dir_enum == TradeDirection.BUY_YES else market.outcome_no_price

        trade = await self.paper_engine.execute_buy(
            market_id=market_id,
            direction=dir_enum,
            amount=amount,
            current_price=price,
            question=market.question,
            strategy="manual",
        )

        if trade:
            self._log("executor", f"Manual BUY: {direction} {market_id} ${amount:.2f}")
            return {
                "action": "buy",
                "trade_id": trade.id,
                "market_id": market_id,
                "direction": direction,
                "price": trade.entry_price,
                "amount": amount,
            }
        return None

    async def manual_sell(self, trade_id: int) -> Optional[dict]:
        """Close a position manually."""
        trade = next((t for t in self.paper_engine.open_trades if t.id == trade_id), None)
        if not trade:
            self._log("executor", f"Trade {trade_id} not found")
            return None

        market = await self.client.get_market(trade.market_id)
        price = market.outcome_yes_price if market else trade.entry_price

        closed = await self.paper_engine.execute_sell(trade_id, price, reason="manual")
        if closed:
            self._log("executor", f"Manual SELL: trade #{trade_id}, P&L=${closed.pnl:+.2f}")
            return {
                "action": "sell",
                "trade_id": trade_id,
                "exit_price": closed.exit_price,
                "pnl": closed.pnl,
            }
        return None

    async def _check_all_exits(self, prices: dict[str, float]):
        """Check stop-losses, take-profits, and time-based exits."""
        # Standard stop-loss and take-profit
        await self.paper_engine.check_stop_losses(prices)
        await self.paper_engine.check_take_profits(prices)

        # Time-based exit for scalps
        await self._check_scalp_timeouts(prices)

    async def _quick_exit_check(self):
        """Fast exit check between scan cycles — critical for scalping."""
        if not self.paper_engine.open_trades:
            return

        # Get fresh prices for open positions
        prices = {}
        for trade in self.paper_engine.open_trades:
            try:
                market = await self.client.get_market(trade.market_id)
                if market:
                    prices[trade.market_id] = market.outcome_yes_price
            except Exception:
                pass

        if prices:
            await self._check_all_exits(prices)

    async def _check_scalp_timeouts(self, prices: dict[str, float]):
        """Force-close scalps that have been open too long."""
        now = datetime.utcnow()
        max_hold = timedelta(minutes=MAX_SCALP_HOLD_MINUTES)

        trades_to_close = []
        for trade in self.paper_engine.open_trades:
            if trade.strategy != "scalping":
                continue

            hold_time = now - trade.opened_at
            if hold_time > max_hold:
                current_price = prices.get(trade.market_id, trade.entry_price)
                trades_to_close.append((trade.id, current_price))

        for trade_id, price in trades_to_close:
            closed = await self.paper_engine.execute_sell(trade_id, price, reason="scalp_timeout")
            if closed:
                self._log(
                    "executor",
                    f"SCALP TIMEOUT: trade #{trade_id} closed after "
                    f"{MAX_SCALP_HOLD_MINUTES}min, P&L=${closed.pnl:+.2f}"
                )

    async def _execute_trade(self, signal: TradeSignal, prices: dict[str, float]) -> Optional[dict]:
        """Execute an approved trade signal."""
        await self._save_signal(signal)

        if settings.trading_mode == TradingMode.PAPER:
            trade = await self.paper_engine.execute_buy(
                market_id=signal.market_id,
                direction=signal.direction,
                amount=signal.position_size_suggestion,
                current_price=signal.entry_price,
                strategy=signal.strategy,
                stop_loss=signal.stop_loss_price,
                target_price=signal.target_exit_price,
            )
            if trade:
                self._log(
                    "executor",
                    f"{'SCALP' if signal.strategy == 'scalping' else 'SWING'} BUY: "
                    f"{signal.direction.value} {signal.market_id} "
                    f"@ {trade.entry_price:.4f}, ${signal.position_size_suggestion:.2f} "
                    f"(target={signal.target_exit_price:.4f}, stop={signal.stop_loss_price:.4f})"
                )
                return {
                    "action": "buy",
                    "trade_id": trade.id,
                    "market_id": signal.market_id,
                    "direction": signal.direction.value,
                    "price": trade.entry_price,
                    "amount": signal.position_size_suggestion,
                    "strategy": signal.strategy,
                    "mode": "paper",
                }

        elif settings.trading_mode == TradingMode.LIVE:
            self._log("executor", f"LIVE order would be placed: {signal.market_id}")
            return None

        return None

    async def _save_signal(self, signal: TradeSignal):
        """Persist trade signal to database."""
        try:
            async with async_session() as session:
                row = SignalRow(
                    market_id=signal.market_id,
                    direction=signal.direction.value,
                    confidence=signal.confidence,
                    strategy=signal.strategy,
                    entry_price=signal.entry_price,
                    target_price=signal.target_exit_price,
                    stop_loss=signal.stop_loss_price,
                    expected_value=signal.expected_value,
                    reasoning=signal.reasoning,
                    acted_on=True,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")

    def _log(self, agent: str, message: str):
        """Add entry to activity log."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "message": message,
        }
        self._activity_log.append(entry)
        if len(self._activity_log) > self._max_log_size:
            self._activity_log = self._activity_log[-self._max_log_size:]

        logger.info(f"[{agent}] {message}")

        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception:
                pass
