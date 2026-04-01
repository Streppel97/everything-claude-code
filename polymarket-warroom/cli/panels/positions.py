"""Open positions panel for the CLI War Room."""

from textual.widgets import Static
from rich.table import Table
from rich.text import Text


class PositionsPanel(Static):
    """Panel showing open positions and unrealized P&L."""

    DEFAULT_CSS = """
    PositionsPanel {
        height: 100%;
        border: solid blue;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._positions = []

    def update_positions(self, positions: list[dict]):
        """Update displayed positions."""
        self._positions = positions[:8]
        self._render()

    def _render(self):
        table = Table(
            title="OPEN POSITIONS",
            title_style="bold blue",
            expand=True,
            padding=(0, 1),
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Market", ratio=3, no_wrap=True)
        table.add_column("Dir", width=5)
        table.add_column("Entry", width=6)
        table.add_column("Now", width=6)
        table.add_column("Size", width=8)
        table.add_column("P&L", width=9)

        for pos in self._positions:
            direction = pos.get("direction", "?")
            dir_style = "green" if "YES" in direction else "red"
            pnl = pos.get("unrealized_pnl", 0)
            pnl_text = Text(f"${pnl:+.2f}")
            pnl_text.stylize("green" if pnl >= 0 else "red")

            question = pos.get("question", "Unknown")[:30]

            table.add_row(
                question,
                Text(direction.replace("BUY_", ""), style=dir_style),
                f"{pos.get('entry_price', 0):.3f}",
                f"{pos.get('current_price', 0):.3f}",
                f"${pos.get('position_size', 0):.0f}",
                pnl_text,
            )

        if not self._positions:
            table.add_row("No open positions", "", "", "", "", "")

        self.update(table)
