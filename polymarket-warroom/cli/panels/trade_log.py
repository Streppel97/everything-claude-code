"""Trade log panel for the CLI War Room."""

from textual.widgets import Static
from rich.table import Table
from rich.text import Text


class TradeLogPanel(Static):
    """Panel showing recent trade history."""

    DEFAULT_CSS = """
    TradeLogPanel {
        height: 100%;
        border: solid yellow;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._trades = []
        self._win_count = 0
        self._loss_count = 0

    def update_trades(self, trades: list[dict], wins: int = 0, losses: int = 0):
        """Update displayed trades."""
        self._trades = trades[:10]
        self._win_count = wins
        self._loss_count = losses
        self._render()

    def _render(self):
        total = self._win_count + self._loss_count
        title = f"TRADE HISTORY  ({total} trades, {self._win_count}W/{self._loss_count}L)"

        table = Table(
            title=title,
            title_style="bold yellow",
            expand=True,
            padding=(0, 1),
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Time", width=6)
        table.add_column("Action", width=8)
        table.add_column("Market", ratio=2, no_wrap=True)
        table.add_column("Size", width=7)
        table.add_column("P&L", width=9)

        for trade in self._trades:
            opened = trade.get("opened_at", "")
            if isinstance(opened, str) and len(opened) > 11:
                time_str = opened[11:16]
            else:
                time_str = "?"

            direction = trade.get("direction", "?")
            status = trade.get("status", "OPEN")
            action = "SELL" if status in ("CLOSED", "STOPPED_OUT") else "BUY"
            action_style = "red" if action == "SELL" else "green"

            pnl = trade.get("pnl")
            if pnl is not None:
                pnl_text = Text(f"${pnl:+.2f}")
                pnl_text.stylize("green" if pnl >= 0 else "red")
            else:
                pnl_text = Text("--")

            question = trade.get("question", trade.get("market_id", "?"))[:25]

            table.add_row(
                time_str,
                Text(f"{action} {direction.replace('BUY_', '')}", style=action_style),
                question,
                f"${trade.get('position_size', 0):.0f}",
                pnl_text,
            )

        if not self._trades:
            table.add_row("--", "No trades yet", "", "", "")

        self.update(table)
