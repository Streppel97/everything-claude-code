"""Polymarket War Room — Textual TUI dashboard."""

import asyncio
import json
from datetime import datetime

import httpx
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Static
from rich.text import Text

from cli.commands import CommandHandler
from cli.panels.alerts import AlertsPanel
from cli.panels.market_scanner import MarketScannerPanel
from cli.panels.positions import PositionsPanel
from cli.panels.trade_log import TradeLogPanel


class StatusBar(Static):
    """Top status bar with mode, P&L, and key metrics."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $primary-background;
        color: $text;
        padding: 0 2;
    }
    """

    def update_status(self, mode: str = "PAPER", pnl: float = 0.0, total: float = 10000.0, halted: bool = False):
        mode_style = "red bold" if halted else ("yellow" if mode == "LIVE" else "green")
        display_mode = "HALTED" if halted else mode.upper()

        text = Text()
        text.append("  POLYMARKET WAR ROOM  ", style="bold white on dark_blue")
        text.append("  Mode: ", style="dim")
        text.append(display_mode, style=mode_style)
        text.append("  │  P&L: ", style="dim")

        pnl_style = "green" if pnl >= 0 else "red"
        text.append(f"${pnl:+,.2f}", style=pnl_style)
        text.append("  │  Portfolio: ", style="dim")
        text.append(f"${total:,.2f}", style="bold")

        self.update(text)


class CommandOutput(Static):
    """Shows the last command output."""

    DEFAULT_CSS = """
    CommandOutput {
        height: 3;
        padding: 0 1;
        border-top: solid $accent;
    }
    """


class WarRoom(App):
    """Polymarket War Room TUI Application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-grid {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 0;
        height: 1fr;
    }

    #bottom-bar {
        dock: bottom;
        height: 5;
    }

    #cmd-input {
        dock: bottom;
        height: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "scan", "Scan"),
        ("h", "halt_toggle", "Halt/Resume"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__()
        self.api_base = api_base
        self.cmd_handler = CommandHandler(api_base)
        self._http = httpx.AsyncClient(base_url=api_base, timeout=10.0)
        self._refresh_task = None
        self._halted = False

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        with Container(id="main-grid"):
            yield MarketScannerPanel(id="scanner")
            yield PositionsPanel(id="positions")
            yield AlertsPanel(id="alerts")
            yield TradeLogPanel(id="trades")
        with Vertical(id="bottom-bar"):
            yield CommandOutput(id="cmd-output")
            yield Input(placeholder="CMD: type command | help | buy | sell | halt | status", id="cmd-input")
        yield Footer()

    async def on_mount(self):
        """Start refresh loop on mount."""
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def on_unmount(self):
        if self._refresh_task:
            self._refresh_task.cancel()
        await self._http.aclose()
        await self.cmd_handler.close()

    async def on_input_submitted(self, event: Input.Submitted):
        """Handle command input."""
        cmd = event.value.strip()
        if not cmd:
            return

        input_widget = self.query_one("#cmd-input", Input)
        input_widget.value = ""

        output = await self.cmd_handler.execute(cmd)
        cmd_output = self.query_one("#cmd-output", CommandOutput)
        cmd_output.update(Text(f"> {cmd}\n{output}"))

        # Refresh after command
        await self._refresh_panels()

    async def action_scan(self):
        output = await self.cmd_handler.execute("scan")
        self.query_one("#cmd-output", CommandOutput).update(Text(output))
        await self._refresh_panels()

    async def action_halt_toggle(self):
        if self._halted:
            output = await self.cmd_handler.execute("resume")
        else:
            output = await self.cmd_handler.execute("halt")
        self._halted = not self._halted
        self.query_one("#cmd-output", CommandOutput).update(Text(output))
        await self._refresh_panels()

    async def action_refresh(self):
        await self._refresh_panels()

    async def _refresh_loop(self):
        """Periodically refresh all panels."""
        while True:
            try:
                await self._refresh_panels()
            except Exception:
                pass
            await asyncio.sleep(5)

    async def _refresh_panels(self):
        """Fetch data from backend and update all panels."""
        try:
            # Fetch all data in parallel
            status_resp, signals_resp, portfolio_resp, trades_resp, activity_resp = await asyncio.gather(
                self._http.get("/api/status"),
                self._http.get("/api/signals"),
                self._http.get("/api/portfolio"),
                self._http.get("/api/trades", params={"limit": 10}),
                self._http.get("/api/activity", params={"limit": 10}),
                return_exceptions=True,
            )

            # Update status bar
            if not isinstance(status_resp, Exception):
                status = status_resp.json()
                self._halted = status.get("halted", False)
                self.query_one("#status-bar", StatusBar).update_status(
                    mode=status.get("trading_mode", "paper"),
                    pnl=status.get("total_value", 10000) - 10000,
                    total=status.get("total_value", 10000),
                    halted=self._halted,
                )

            # Update scanner panel
            if not isinstance(signals_resp, Exception):
                signals = signals_resp.json()
                self.query_one("#scanner", MarketScannerPanel).update_signals(signals)

            # Update positions panel
            if not isinstance(portfolio_resp, Exception):
                portfolio = portfolio_resp.json()
                self.query_one("#positions", PositionsPanel).update_positions(
                    portfolio.get("open_positions", [])
                )

            # Update trade log
            if not isinstance(trades_resp, Exception) and not isinstance(portfolio_resp, Exception):
                trades = trades_resp.json()
                portfolio = portfolio_resp.json() if not isinstance(portfolio_resp, Exception) else {}
                self.query_one("#trades", TradeLogPanel).update_trades(
                    trades,
                    wins=portfolio.get("win_count", 0),
                    losses=portfolio.get("loss_count", 0),
                )

            # Update activity log
            if not isinstance(activity_resp, Exception):
                activity = activity_resp.json()
                self.query_one("#alerts", AlertsPanel).update_log(activity)

        except httpx.ConnectError:
            self.query_one("#cmd-output", CommandOutput).update(
                Text("Cannot connect to backend. Start it with: uvicorn backend.main:app", style="red")
            )


def main():
    """Entry point for the CLI War Room."""
    import sys
    api_base = "http://localhost:8000"
    if len(sys.argv) > 1:
        api_base = sys.argv[1]

    app = WarRoom(api_base=api_base)
    app.run()


if __name__ == "__main__":
    main()
