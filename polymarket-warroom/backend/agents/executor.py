"""Executor Agent — orchestrates the full pipeline: scan → analyze → risk → trade."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from backend.agents.analyst import AnalystAgent
from backend.agents.risk_manager import RiskManager
from backend.agents.scanner import ScannerAgent
from backend.config import TradingMode, settings
from backend.db.database import SignalRow, async_session
from backend.models.trade import TradeSignal
from backend.services.paper_trading import PaperTradingEngine
from backend.services.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Orchestrates the full trading pipeline.

    Pipeline: Scanner → Analyst → Risk Manager → Executor
    Supports paper and live trading modes.
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
        self._log("scanner", f"Scanning markets...")
        market_signals = await self.scanner.scan_once()
        self._log(
            "scanner",
            f"{len(market_signals)} signals from "
            f"{self.scanner.scan_count} scans"
        )

        if not market_signals:
            return cycle_results

        # Step 2: Analyze
        self._log("analyst", f"Analyzing {len(market_signals)} market signals...")
        trade_signals = await self.analyst.analyze(market_signals)
        self._log("analyst", f"{len(trade_signals)} trade signals generated")

        if not trade_signals:
            return cycle_results

        # Step 3: Risk check + execute
        current_prices = {
            ms.market_id: ms.current_price_yes for ms in market_signals
        }

        for signal in trade_signals[:5]:  # Top 5 signals per cycle
            approved = await self.risk_manager.evaluate(signal, current_prices)
            if not approved:
                self._log("risk", f"REJECTED: {signal.market_id} ({signal.strategy})")
                continue

            self._log("risk", f"APPROVED: {signal.market_id}, size=${approved.position_size_suggestion:.2f}")

            # Step 4: Execute
            result = await self._execute_trade(approved, current_prices)
            if result:
                cycle_results.append(result)

        # Step 5: Check stop-losses and take-profits
        await self.paper_engine.check_stop_losses(current_prices)
        await self.paper_engine.check_take_profits(current_prices)

        return cycle_results

    async def start(self, interval: Optional[int] = None):
        """Start continuous pipeline execution."""
        interval = interval or settings.scan_interval_seconds
        self._running = True
        self._log("executor", f"Pipeline started, interval={interval}s")

        while self._running:
            if self.risk_manager.is_halted:
                self._log("executor", f"Trading halted: {self.risk_manager.halt_reason}")
                await asyncio.sleep(interval)
                continue

            try:
                results = await self.run_pipeline_once()
                if results:
                    self._log("executor", f"Executed {len(results)} trades this cycle")
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                self._log("executor", f"ERROR: {e}")

            await asyncio.sleep(interval)

    def stop(self):
        """Stop the pipeline."""
        self._running = False
        self._log("executor", "Pipeline stopped")

    async def halt(self):
        """Kill switch — stop all trading and cancel orders."""
        self.risk_manager.halt("Kill switch engaged")
        self._running = False
        self._log("executor", "KILL SWITCH — all trading halted")

        # In live mode, would cancel all open orders here
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
        from backend.models.trade import TradeDirection

        try:
            dir_enum = TradeDirection(direction)
        except ValueError:
            dir_enum = TradeDirection.BUY_YES if direction.upper() in ("YES", "BUY_YES") else TradeDirection.BUY_NO

        # Get current price
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

    async def _execute_trade(self, signal: TradeSignal, prices: dict[str, float]) -> Optional[dict]:
        """Execute an approved trade signal."""
        # Persist signal to database
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
                    f"PAPER BUY: {signal.direction.value} {signal.market_id} "
                    f"@ {trade.entry_price:.4f}, ${signal.position_size_suggestion:.2f} "
                    f"({signal.strategy})"
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
            # Live trading — limit orders only
            self._log("executor", f"LIVE order would be placed: {signal.market_id}")
            # TODO: implement CLOB order placement with wallet auth
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
