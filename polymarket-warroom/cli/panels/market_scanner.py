"""Market scanner panel for the CLI War Room."""

from textual.widgets import Static
from rich.table import Table
from rich.text import Text


class MarketScannerPanel(Static):
    """Live market feed panel showing scanner signals."""

    DEFAULT_CSS = """
    MarketScannerPanel {
        height: 100%;
        border: solid green;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._signals = []

    def update_signals(self, signals: list[dict]):
        """Update displayed signals."""
        self._signals = signals[:8]
        self._render()

    def _render(self):
        table = Table(
            title="MARKET SCANNER",
            title_style="bold green",
            expand=True,
            padding=(0, 1),
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Market", ratio=3, no_wrap=True)
        table.add_column("Dir", width=4)
        table.add_column("Price", width=6)
        table.add_column("Chg 1h", width=8)
        table.add_column("Signal", width=7)
        table.add_column("Strategy", width=10)

        for sig in self._signals:
            direction = sig.get("signal_direction", "?")
            dir_style = "green" if direction == "YES" else "red"
            price = sig.get("current_price_yes", 0)
            change = sig.get("price_change_1h", 0)

            change_text = Text(f"{change:+.1%}")
            change_text.stylize("green" if change > 0 else "red")

            strength = sig.get("signal_strength", 0)
            signal_indicator = "🟢" if strength > 0.7 else "🟡" if strength > 0.4 else "🔴"

            question = sig.get("question", "Unknown")[:30]

            table.add_row(
                question,
                Text(direction, style=dir_style),
                f"{price:.2f}",
                change_text,
                f"{signal_indicator} {strength:.2f}",
                sig.get("strategy", "")[:10] if "strategy" in sig else "",
            )

        if not self._signals:
            table.add_row("Scanning...", "", "", "", "", "")

        self.update(table)
