"""FastAPI backend — REST + WebSocket for the Polymarket War Room."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.analyst import AnalystAgent
from backend.agents.executor import ExecutorAgent
from backend.agents.risk_manager import RiskManager
from backend.agents.scanner import ScannerAgent
from backend.config import TradingMode, settings
from backend.db.database import init_db
from backend.services.paper_trading import PaperTradingEngine
from backend.services.polymarket_client import PolymarketClient
from backend.services.portfolio_tracker import PortfolioTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances
client: Optional[PolymarketClient] = None
paper_engine: Optional[PaperTradingEngine] = None
scanner: Optional[ScannerAgent] = None
analyst: Optional[AnalystAgent] = None
risk_manager: Optional[RiskManager] = None
executor: Optional[ExecutorAgent] = None
portfolio_tracker: Optional[PortfolioTracker] = None
pipeline_task: Optional[asyncio.Task] = None
snapshot_task: Optional[asyncio.Task] = None

# WebSocket connections
ws_connections: set[WebSocket] = set()


async def snapshot_loop():
    """Take portfolio snapshots every 60 seconds."""
    while True:
        try:
            prices = {
                ms.market_id: ms.current_price_yes
                for ms in (scanner.latest_signals if scanner else [])
            }
            if portfolio_tracker:
                await portfolio_tracker.take_snapshot(prices)
        except Exception as e:
            logger.error(f"Snapshot error: {e}")
        await asyncio.sleep(60)


async def broadcast_ws(event_type: str, data: dict):
    """Broadcast event to all WebSocket clients."""
    message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.utcnow().isoformat()})
    dead = set()
    for ws in ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    ws_connections -= dead


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global client, paper_engine, scanner, analyst, risk_manager, executor
    global portfolio_tracker, pipeline_task, snapshot_task

    # Initialize database
    await init_db()

    # Initialize components
    client = PolymarketClient(api_key=settings.polymarket_api_key)
    paper_engine = PaperTradingEngine(initial_balance=settings.initial_balance)
    await paper_engine.initialize()

    scanner = ScannerAgent(client)
    analyst = AnalystAgent()
    risk_manager = RiskManager(paper_engine)
    executor = ExecutorAgent(client, paper_engine, scanner, analyst, risk_manager)
    portfolio_tracker = PortfolioTracker(paper_engine)

    # Wire up WebSocket broadcasts
    def on_activity(entry):
        asyncio.create_task(broadcast_ws("activity", entry))

    executor.on_activity(on_activity)

    async def on_signals(signals):
        await broadcast_ws("signals", {
            "count": len(signals),
            "top": [s.model_dump(mode="json") for s in signals[:10]],
        })

    scanner.on_signals(on_signals)

    # Start pipeline in background
    if settings.trading_mode != TradingMode.HALTED:
        pipeline_task = asyncio.create_task(executor.start())
        snapshot_task = asyncio.create_task(snapshot_loop())
        logger.info(f"Pipeline started in {settings.trading_mode.value} mode")

    yield

    # Shutdown
    if pipeline_task:
        executor.stop()
        pipeline_task.cancel()
    if snapshot_task:
        snapshot_task.cancel()
    if client:
        await client.close()

    logger.info("Shutdown complete")


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


# ---- REST Endpoints ----

@app.get("/api/status")
async def get_status():
    """System status overview."""
    prices = {ms.market_id: ms.current_price_yes for ms in (scanner.latest_signals if scanner else [])}
    return {
        "trading_mode": settings.trading_mode.value,
        "pipeline_running": executor.is_running if executor else False,
        "halted": risk_manager.is_halted if risk_manager else False,
        "halt_reason": risk_manager.halt_reason if risk_manager else "",
        "scan_count": scanner.scan_count if scanner else 0,
        "open_positions": paper_engine.open_trade_count if paper_engine else 0,
        "cash": paper_engine.cash if paper_engine else 0,
        "total_value": paper_engine.get_total_value(prices) if paper_engine else 0,
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Get current portfolio state."""
    prices = {ms.market_id: ms.current_price_yes for ms in (scanner.latest_signals if scanner else [])}
    # Also add prices from open trades
    if paper_engine:
        for t in paper_engine.open_trades:
            if t.market_id not in prices:
                prices[t.market_id] = t.entry_price
    portfolio = await portfolio_tracker.get_portfolio(prices)
    return portfolio.model_dump(mode="json")


@app.get("/api/signals")
async def get_signals(limit: int = Query(20, ge=1, le=100)):
    """Get latest scanner signals."""
    signals = scanner.latest_signals if scanner else []
    return [s.model_dump(mode="json") for s in signals[:limit]]


@app.get("/api/trade-signals")
async def get_trade_signals():
    """Get latest analyst trade signals."""
    signals = analyst.latest_signals if analyst else []
    return [s.model_dump(mode="json") for s in signals]


@app.get("/api/positions")
async def get_positions():
    """Get open positions."""
    if not paper_engine:
        return []
    trades = paper_engine.open_trades
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/trades")
async def get_trades(limit: int = 50, offset: int = 0, status: Optional[str] = None):
    """Get trade history."""
    trades = await portfolio_tracker.get_trade_history(limit=limit, offset=offset, status=status)
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/activity")
async def get_activity(limit: int = Query(50, ge=1, le=200)):
    """Get agent activity log."""
    log = executor.activity_log if executor else []
    return log[-limit:]


@app.get("/api/stats")
async def get_stats():
    """Get portfolio statistics."""
    stats = await portfolio_tracker.get_stats()
    return stats.model_dump(mode="json")


@app.get("/api/snapshots")
async def get_snapshots(hours: int = Query(24, ge=1, le=168)):
    """Get portfolio snapshots for charting."""
    snapshots = await portfolio_tracker.get_snapshots(hours=hours)
    return [s.model_dump(mode="json") for s in snapshots]


@app.get("/api/markets/{market_id}")
async def get_market(market_id: str):
    """Get single market detail."""
    market = await client.get_market(market_id)
    if not market:
        return {"error": "Market not found"}
    return market.model_dump(mode="json")


# ---- Trading Actions ----

@app.post("/api/scan")
async def force_scan():
    """Force an immediate market scan."""
    signals = await scanner.scan_once()
    return {"signals_count": len(signals)}


@app.post("/api/buy")
async def buy(market_id: str, direction: str, amount: float):
    """Place a manual buy order."""
    result = await executor.manual_buy(market_id, direction, amount)
    if result:
        await broadcast_ws("trade", result)
        return result
    return {"error": "Trade failed"}


@app.post("/api/sell")
async def sell(trade_id: int):
    """Close a position."""
    result = await executor.manual_sell(trade_id)
    if result:
        await broadcast_ws("trade", result)
        return result
    return {"error": "Sell failed"}


@app.post("/api/halt")
async def halt_trading():
    """Engage kill switch."""
    await executor.halt()
    await broadcast_ws("status", {"halted": True, "reason": "Kill switch engaged"})
    return {"status": "halted"}


@app.post("/api/resume")
async def resume_trading():
    """Resume trading after halt."""
    global pipeline_task
    executor.resume()
    if not executor.is_running:
        pipeline_task = asyncio.create_task(executor.start())
    await broadcast_ws("status", {"halted": False})
    return {"status": "resumed"}


@app.post("/api/config")
async def update_config(key: str, value: str):
    """Update a runtime configuration value."""
    allowed_keys = {
        "scan_interval_seconds", "min_liquidity", "min_volume_24h",
        "max_spread", "min_ev_threshold",
    }
    if key not in allowed_keys:
        return {"error": f"Key '{key}' not configurable at runtime"}

    try:
        if key == "scan_interval_seconds":
            setattr(settings, key, int(value))
        else:
            setattr(settings, key, float(value))
        return {"status": "updated", "key": key, "value": value}
    except ValueError:
        return {"error": "Invalid value"}


# ---- WebSocket ----

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for real-time updates."""
    await ws.accept()
    ws_connections.add(ws)
    logger.info(f"WebSocket client connected ({len(ws_connections)} total)")

    try:
        # Send initial state
        prices = {ms.market_id: ms.current_price_yes for ms in (scanner.latest_signals if scanner else [])}
        portfolio = await portfolio_tracker.get_portfolio(prices)
        await ws.send_text(json.dumps({
            "type": "init",
            "data": {
                "portfolio": portfolio.model_dump(mode="json"),
                "status": {
                    "trading_mode": settings.trading_mode.value,
                    "pipeline_running": executor.is_running if executor else False,
                    "halted": risk_manager.is_halted if risk_manager else False,
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }))

        # Keep alive and handle incoming messages
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "subscribe_signals":
                # Client wants signal updates
                signals = scanner.latest_signals if scanner else []
                await ws.send_text(json.dumps({
                    "type": "signals",
                    "data": [s.model_dump(mode="json") for s in signals[:20]],
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ws_connections.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(ws_connections)} remaining)")
