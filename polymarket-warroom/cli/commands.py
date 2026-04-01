"""CLI command handler for manual overrides."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"


class CommandHandler:
    """Handles CLI commands by calling the backend API."""

    def __init__(self, api_base: str = API_BASE):
        self.api_base = api_base
        self._client = httpx.AsyncClient(base_url=api_base, timeout=10.0)

    async def close(self):
        await self._client.aclose()

    async def execute(self, command_str: str) -> str:
        """Parse and execute a command string."""
        parts = command_str.strip().split()
        if not parts:
            return ""

        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "scan": self._cmd_scan,
            "buy": self._cmd_buy,
            "sell": self._cmd_sell,
            "halt": self._cmd_halt,
            "resume": self._cmd_resume,
            "status": self._cmd_status,
            "detail": self._cmd_detail,
            "config": self._cmd_config,
            "help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if not handler:
            return f"Unknown command: {cmd}. Type 'help' for available commands."

        try:
            return await handler(args)
        except httpx.ConnectError:
            return "ERROR: Cannot connect to backend. Is it running?"
        except Exception as e:
            return f"ERROR: {e}"

    async def _cmd_scan(self, args: list[str]) -> str:
        resp = await self._client.post("/api/scan")
        data = resp.json()
        return f"Scan complete: {data.get('signals_count', 0)} signals generated"

    async def _cmd_buy(self, args: list[str]) -> str:
        if len(args) < 3:
            return "Usage: buy <market_id> <YES/NO> <amount>"
        market_id, direction, amount = args[0], args[1].upper(), args[2]
        try:
            amount_f = float(amount)
        except ValueError:
            return "Amount must be a number"

        if direction not in ("YES", "NO", "BUY_YES", "BUY_NO"):
            return "Direction must be YES or NO"

        direction = f"BUY_{direction}" if not direction.startswith("BUY_") else direction
        resp = await self._client.post(
            "/api/buy",
            params={"market_id": market_id, "direction": direction, "amount": amount_f},
        )
        data = resp.json()
        if "error" in data:
            return f"Buy failed: {data['error']}"
        return f"BUY {direction} {market_id} @ {data.get('price', '?'):.4f}, ${amount_f:.2f}"

    async def _cmd_sell(self, args: list[str]) -> str:
        if len(args) < 1:
            return "Usage: sell <trade_id>"
        try:
            trade_id = int(args[0])
        except ValueError:
            return "Trade ID must be a number"

        resp = await self._client.post("/api/sell", params={"trade_id": trade_id})
        data = resp.json()
        if "error" in data:
            return f"Sell failed: {data['error']}"
        return f"SOLD trade #{trade_id} @ {data.get('exit_price', '?'):.4f}, P&L: ${data.get('pnl', 0):+.2f}"

    async def _cmd_halt(self, args: list[str]) -> str:
        resp = await self._client.post("/api/halt")
        return "⚠️  TRADING HALTED — kill switch engaged"

    async def _cmd_resume(self, args: list[str]) -> str:
        resp = await self._client.post("/api/resume")
        return "✅ Trading resumed"

    async def _cmd_status(self, args: list[str]) -> str:
        resp = await self._client.get("/api/status")
        data = resp.json()
        lines = [
            f"Mode: {data.get('trading_mode', '?')}",
            f"Pipeline: {'running' if data.get('pipeline_running') else 'stopped'}",
            f"Halted: {data.get('halted', False)}",
            f"Scans: {data.get('scan_count', 0)}",
            f"Positions: {data.get('open_positions', 0)}",
            f"Cash: ${data.get('cash', 0):,.2f}",
            f"Total: ${data.get('total_value', 0):,.2f}",
        ]
        return "\n".join(lines)

    async def _cmd_detail(self, args: list[str]) -> str:
        if len(args) < 1:
            return "Usage: detail <market_id>"
        resp = await self._client.get(f"/api/markets/{args[0]}")
        data = resp.json()
        if "error" in data:
            return f"Market not found: {args[0]}"
        lines = [
            f"Market: {data.get('question', '?')}",
            f"YES: {data.get('outcome_yes_price', 0):.3f}  NO: {data.get('outcome_no_price', 0):.3f}",
            f"Volume 24h: ${data.get('volume_24h', 0):,.0f}",
            f"Liquidity: ${data.get('liquidity', 0):,.0f}",
            f"Spread: {data.get('spread', 0):.3f}",
            f"Category: {data.get('category', '?')}",
        ]
        return "\n".join(lines)

    async def _cmd_config(self, args: list[str]) -> str:
        if len(args) < 2:
            return "Usage: config <key> <value>"
        resp = await self._client.post("/api/config", params={"key": args[0], "value": args[1]})
        data = resp.json()
        if "error" in data:
            return f"Config error: {data['error']}"
        return f"Updated {args[0]} = {args[1]}"

    async def _cmd_help(self, args: list[str]) -> str:
        return """Available commands:
  scan                         - Force immediate market scan
  buy <market_id> <YES/NO> <$> - Manual buy order
  sell <trade_id>              - Close position
  halt                         - Kill switch, stop all trading
  resume                       - Resume after halt
  status                       - Portfolio summary
  detail <market_id>           - Deep dive on market
  config <key> <value>         - Change setting at runtime
  help                         - Show this help"""
