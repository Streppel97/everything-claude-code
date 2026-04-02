"""Polymarket War Room — FastAPI backend.

Provides REST API + WebSocket for the trading dashboard.
Orchestrates scanner → analyst → risk manager → executor pipeline.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.analyst import AnalystAgent
from backend.agents.executor import ExecutorAgent
from backend.agents.risk_manager import RiskManager
from backend.agents.scanner import ScannerAgent
from backend.config import settings
from backend.db.database import init_db
from backend.services.paper_trading import PaperTradingEngine
from backend.services.polymarket_client import PolymarketClient
from backend.strategies.scalp_cycle_engine import ScalpCycleManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global components
client = PolymarketClient()
paper_engine = PaperTradingEngine(initial_balance=settings.initial_balance)
scanner = ScannerAgent(client)
analyst = AnalystAgent()
risk_manager = RiskManager(paper_engine)
executor = ExecutorAgent(client, paper_engine, scanner, analyst, risk_manager)
cycle_manager = ScalpCycleManager()

# WebSocket connections
ws_connections: list[WebSocket] = []


async def broadcast(data: dict):
    """Broadcast data to all connected WebSocket clients."""
    dead = []
    for ws in ws_connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_connections.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, cleanup on shutdown."""
    await init_db()
    logger.info(
        f"War Room initialized — mode={settings.trading_mode.value}, "
        f"balance=${settings.initial_balance:,.2f}"
    )

    # Wire up activity log broadcasting
    executor.on_activity(lambda entry: asyncio.ensure_future(
        broadcast({"type": "activity", "data": entry})
    ))

    yield

    executor.stop()
    await client.close()
    logger.info("War Room shut down")


app = FastAPI(
    title="Polymarket War Room",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── REST Endpoints ──────────────────────────────────────────────────────────


@app.get("/api/status")
async def get_status():
    """Overall system status."""
    prices = {}
    for trade in paper_engine.open_trades:
        try:
            market = await client.get_market(trade.market_id)
            if market:
                prices[trade.market_id] = market.outcome_yes_price
        except Exception:
            pass

    return {
        "running": executor.is_running,
        "mode": settings.trading_mode.value,
        "halted": risk_manager.is_halted,
        "halt_reason": risk_manager.halt_reason,
        "portfolio": {
            "total_value": paper_engine.get_total_value(prices),
            "cash": paper_engine.cash,
            "positions_value": paper_engine.get_positions_value(prices),
            "initial_balance": paper_engine.initial_balance,
            "total_pnl": paper_engine.total_pnl,
        },
        "open_positions": len(paper_engine.open_trades),
        "scan_count": scanner.scan_count,
        "analysis_count": analyst.analysis_count,
        "cycle_manager": {
            "active_cycles": cycle_manager.open_cycle_count,
            "win_rate": cycle_manager.win_rate,
            "halted": cycle_manager.is_halted,
        },
    }


@app.get("/api/positions")
async def get_positions():
    """All open positions."""
    positions = []
    for trade in paper_engine.open_trades:
        try:
            market = await client.get_market(trade.market_id)
            current_price = market.outcome_yes_price if market else trade.entry_price
        except Exception:
            current_price = trade.entry_price

        pnl_pct = (current_price - trade.entry_price) / trade.entry_price if trade.entry_price > 0 else 0
        pnl = trade.position_size * pnl_pct

        positions.append({
            "id": trade.id,
            "market_id": trade.market_id,
            "question": trade.question,
            "direction": trade.direction.value,
            "entry_price": trade.entry_price,
            "current_price": current_price,
            "position_size": trade.position_size,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "strategy": trade.strategy,
            "stop_loss": trade.stop_loss,
            "target_price": trade.target_price,
            "opened_at": trade.opened_at.isoformat(),
        })

    return {"positions": positions}


@app.get("/api/trades")
async def get_trades():
    """Trade history (closed trades)."""
    history = []
    for trade in paper_engine.trade_history[-100:]:
        history.append({
            "id": trade.id,
            "market_id": trade.market_id,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "position_size": trade.position_size,
            "pnl": trade.pnl,
            "reason": trade.reason,
        })
    return {"trades": history}


@app.get("/api/signals")
async def get_signals():
    """Latest analyst signals."""
    return {
        "signals": [
            {
                "market_id": s.market_id,
                "direction": s.direction.value,
                "confidence": s.confidence,
                "strategy": s.strategy,
                "entry_price": s.entry_price,
                "target": s.target_exit_price,
                "stop_loss": s.stop_loss_price,
                "ev": s.expected_value,
                "reasoning": s.reasoning,
            }
            for s in analyst.latest_signals[:20]
        ]
    }


@app.get("/api/activity")
async def get_activity():
    """Recent activity log."""
    return {"activity": executor.activity_log[-50:]}


@app.get("/api/metrics")
async def get_metrics():
    """Scalp cycle aggregate metrics."""
    return cycle_manager.get_aggregate_metrics()


@app.post("/api/start")
async def start_pipeline():
    """Start the trading pipeline."""
    if executor.is_running:
        return {"status": "already_running"}
    asyncio.create_task(executor.start())
    return {"status": "started"}


@app.post("/api/stop")
async def stop_pipeline():
    """Stop the trading pipeline."""
    executor.stop()
    return {"status": "stopped"}


@app.post("/api/halt")
async def halt_trading():
    """Engage kill switch."""
    await executor.halt()
    cycle_manager._halt("Kill switch from dashboard")
    return {"status": "halted"}


@app.post("/api/resume")
async def resume_trading():
    """Resume after halt."""
    executor.resume()
    cycle_manager.resume()
    return {"status": "resumed"}


@app.post("/api/buy")
async def manual_buy(market_id: str, direction: str = "BUY_YES", amount: float = 50):
    """Manual trade entry."""
    result = await executor.manual_buy(market_id, direction, amount)
    if result:
        return {"status": "ok", "trade": result}
    return {"status": "failed"}


@app.post("/api/sell")
async def manual_sell(trade_id: int):
    """Manual trade exit."""
    result = await executor.manual_sell(trade_id)
    if result:
        return {"status": "ok", "trade": result}
    return {"status": "failed"}


# ─── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Real-time updates via WebSocket."""
    await ws.accept()
    ws_connections.append(ws)
    logger.info(f"WebSocket connected ({len(ws_connections)} total)")

    try:
        while True:
            # Send periodic status updates
            await asyncio.sleep(2)
            prices = {}
            for trade in paper_engine.open_trades:
                try:
                    market = await client.get_market(trade.market_id)
                    if market:
                        prices[trade.market_id] = market.outcome_yes_price
                except Exception:
                    pass

            await ws.send_json({
                "type": "status",
                "data": {
                    "portfolio_value": paper_engine.get_total_value(prices),
                    "cash": paper_engine.cash,
                    "total_pnl": paper_engine.total_pnl,
                    "open_positions": len(paper_engine.open_trades),
                    "running": executor.is_running,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            })
    except WebSocketDisconnect:
        ws_connections.remove(ws)
        logger.info(f"WebSocket disconnected ({len(ws_connections)} total)")
    except Exception:
        if ws in ws_connections:
            ws_connections.remove(ws)
