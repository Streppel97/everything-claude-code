"""Executor Agent — orchestrates the full pipeline: scan → analyze → risk → trade.

Scalping-aware: checks exits aggressively, enforces time-based exits,
persists all activity to DB, and prevents duplicate market positions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.agents.analyst import AnalystAgent
from backend.agents.risk_manager import RiskManager
from backend.agents.scanner import ScannerAgent
from backend.config import TradingMode, settings
from backend.db.database import ActivityLogRow, SignalRow, async_session
from backend.models.trade import TradeDirection, TradeSignal
from backend.services.paper_trading import PaperTradingEngine
from backend.services.polymarket_client import PolymarketClient
from backend.services.post_mortem import PostMortemAnalyzer

logger = logging.getLogger(__name__)

MAX_SCALP_HOLD_MINUTES = 120
MAX_CONCURRENT_SCALPS = 5
SCALP_EXIT_CHECK_INTERVAL = 10


class ExecutorAgent:
    """Orchestrates the full trading pipeline with scalping focus."""

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
        # Market name cache: market_id → question text
        self._market_names: dict[str, str] = {}
        self.post_mortem = PostMortemAnalyzer()

    def on_activity(self, callback):
        self._callbacks.append(callback)

    @property
    def activity_log(self) -> list[dict]:
        return self._activity_log.copy()

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_market_name(self, market_id: str) -> str:
        """Get cached market name, falling back to ID."""
        return self._market_names.get(market_id, market_id)

    async def run_pipeline_once(self) -> list[dict]:
        """Execute one full pipeline cycle."""
        cycle_results = []

        # Step 1: Scan (exclude markets with open positions)
        open_market_ids = {t.market_id for t in self.paper_engine.open_trades}
        self.scanner.set_excluded_markets(open_market_ids)
        self._log("scanner", "Scanning markets...")
        market_signals = await self.scanner.scan_once()

        # Cache market names from scan results
        for ms in market_signals:
            if ms.question:
                self._market_names[ms.market_id] = ms.question

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
        current_scalps = sum(
            1 for t in self.paper_engine.open_trades if t.strategy == "scalping"
        )

        for signal in trade_signals[:5]:
            if signal.strategy == "scalping" and current_scalps >= MAX_CONCURRENT_SCALPS:
                self._log("risk", f"Scalp limit reached ({MAX_CONCURRENT_SCALPS}), skipping")
                continue

            market_name = self._get_market_name(signal.market_id)
            approved = await self.risk_manager.evaluate(signal, current_prices)
            if not approved:
                self._log("risk", f"REJECTED: {market_name} ({signal.strategy})")
                continue

            self._log("risk", f"APPROVED: {market_name}, size=${approved.position_size_suggestion:.2f}")

            result = await self._execute_trade(approved, current_prices)
            if result:
                cycle_results.append(result)
                if signal.strategy == "scalping":
                    current_scalps += 1

        return cycle_results

    async def start(self, interval: Optional[int] = None):
        interval = interval or settings.scan_interval_seconds
        self._running = True
        self._log("executor", f"Pipeline started (scalping mode), interval={interval}s")

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
                self.post_mortem.record_system_failure("pipeline", str(e))

            for _ in range(max(1, interval // SCALP_EXIT_CHECK_INTERVAL - 1)):
                if not self._running:
                    break
                await asyncio.sleep(SCALP_EXIT_CHECK_INTERVAL)
                try:
                    await self._quick_exit_check()
                except Exception as e:
                    logger.error(f"Exit check error: {e}")

    def stop(self):
        self._running = False
        self._log("executor", "Pipeline stopped")

    async def halt(self):
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
        self.risk_manager.resume()
        self._log("executor", "Trading resumed")

    async def manual_buy(self, market_id: str, direction: str, amount: float) -> Optional[dict]:
        try:
            dir_enum = TradeDirection(direction)
        except ValueError:
            dir_enum = TradeDirection.BUY_YES if direction.upper() in ("YES", "BUY_YES") else TradeDirection.BUY_NO

        # Duplicate prevention for manual trades
        if self.paper_engine.has_position_in_market(market_id):
            self._log("executor", f"Manual BUY rejected: already have position in {market_id}")
            return None

        market = await self.client.get_market(market_id)
        if not market:
            self._log("executor", f"Market not found: {market_id}")
            return None

        # Cache name
        self._market_names[market_id] = market.question

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
            self._log("executor", f"Manual BUY: {direction} \"{market.question}\" ${amount:.2f}")
            return {
                "action": "buy",
                "trade_id": trade.id,
                "market_id": market_id,
                "market_name": market.question,
                "direction": direction,
                "price": trade.entry_price,
                "amount": amount,
            }
        return None

    async def manual_sell(self, trade_id: int) -> Optional[dict]:
        trade = next((t for t in self.paper_engine.open_trades if t.id == trade_id), None)
        if not trade:
            self._log("executor", f"Trade {trade_id} not found")
            return None

        market = await self.client.get_market(trade.market_id)
        price = market.outcome_yes_price if market else trade.entry_price
        market_name = market.question if market else self._get_market_name(trade.market_id)

        closed = await self.paper_engine.execute_sell(trade_id, price, reason="manual")
        if closed:
            self._log("executor", f"Manual SELL: \"{market_name}\", P&L=${closed.pnl:+.2f}")
            pm = self.post_mortem.analyze_trade(closed)
            self._log("post_mortem", f"[{pm.category}] #{pm.trade_id}: {pm.diagnosis}")
            return {
                "action": "sell",
                "trade_id": trade_id,
                "market_name": market_name,
                "exit_price": closed.exit_price,
                "pnl": closed.pnl,
            }
        return None

    async def _check_all_exits(self, prices: dict[str, float]):
        # Snapshot trade count before exits to detect new closures
        history_before = len(self.paper_engine.trade_history)

        await self.paper_engine.check_stop_losses(prices)
        await self.paper_engine.check_take_profits(prices)
        await self._check_scalp_timeouts(prices)

        # Run post-mortem on any newly closed trades
        new_closures = self.paper_engine.trade_history[history_before:]
        for closed in new_closures:
            pm = self.post_mortem.analyze_trade(closed)
            self._log("post_mortem", f"[{pm.category}] #{pm.trade_id} {pm.strategy}: {pm.diagnosis}")

    async def _quick_exit_check(self):
        if not self.paper_engine.open_trades:
            return
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
        now = datetime.utcnow()
        max_hold = timedelta(minutes=MAX_SCALP_HOLD_MINUTES)

        trades_to_close = []
        for trade in self.paper_engine.open_trades:
            if trade.strategy != "scalping":
                continue
            if (now - trade.opened_at) > max_hold:
                current_price = prices.get(trade.market_id, trade.entry_price)
                trades_to_close.append((trade.id, current_price))

        for trade_id, price in trades_to_close:
            trade = next((t for t in self.paper_engine.open_trades if t.id == trade_id), None)
            market_name = self._get_market_name(trade.market_id) if trade else "?"
            closed = await self.paper_engine.execute_sell(trade_id, price, reason="scalp_timeout")
            if closed:
                self._log(
                    "executor",
                    f"SCALP TIMEOUT: \"{market_name}\" closed after "
                    f"{MAX_SCALP_HOLD_MINUTES}min, P&L=${closed.pnl:+.2f}"
                )

    async def _execute_trade(self, signal: TradeSignal, prices: dict[str, float]) -> Optional[dict]:
        market_name = self._get_market_name(signal.market_id)
        await self._save_signal(signal, market_name)

        if settings.trading_mode == TradingMode.PAPER:
            trade = await self.paper_engine.execute_buy(
                market_id=signal.market_id,
                direction=signal.direction,
                amount=signal.position_size_suggestion,
                current_price=signal.entry_price,
                question=market_name,
                strategy=signal.strategy,
                stop_loss=signal.stop_loss_price,
                target_price=signal.target_exit_price,
            )
            if trade:
                label = "SCALP" if signal.strategy == "scalping" else "SWING"
                self._log(
                    "executor",
                    f"{label} BUY: {signal.direction.value} \"{market_name}\" "
                    f"@ {trade.entry_price:.4f}, ${signal.position_size_suggestion:.2f} "
                    f"(target={signal.target_exit_price:.4f}, stop={signal.stop_loss_price:.4f})"
                )
                return {
                    "action": "buy",
                    "trade_id": trade.id,
                    "market_id": signal.market_id,
                    "market_name": market_name,
                    "direction": signal.direction.value,
                    "price": trade.entry_price,
                    "amount": signal.position_size_suggestion,
                    "strategy": signal.strategy,
                    "mode": "paper",
                }

        elif settings.trading_mode == TradingMode.LIVE:
            self._log("executor", f"LIVE order: \"{market_name}\"")
            return None

        return None

    async def _save_signal(self, signal: TradeSignal, market_name: str = ""):
        try:
            async with async_session() as session:
                row = SignalRow(
                    market_id=signal.market_id,
                    market_name=market_name,
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
        """Add entry to in-memory log, persist to DB, and notify callbacks."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "message": message,
        }
        self._activity_log.append(entry)
        if len(self._activity_log) > self._max_log_size:
            self._activity_log = self._activity_log[-self._max_log_size:]

        logger.info(f"[{agent}] {message}")

        # Persist to DB (fire-and-forget)
        try:
            asyncio.get_event_loop().create_task(self._persist_log(agent, message))
        except RuntimeError:
            pass

        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    async def _persist_log(self, agent: str, message: str):
        """Save activity log entry to database."""
        try:
            async with async_session() as session:
                row = ActivityLogRow(
                    agent=agent,
                    message=message,
                    timestamp=datetime.utcnow(),
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.debug(f"Failed to persist activity log: {e}")
