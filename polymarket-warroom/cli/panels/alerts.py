"""Agent alerts / activity panel for the CLI War Room."""

from textual.widgets import Static
from rich.table import Table
from rich.text import Text


class AlertsPanel(Static):
    """Panel showing agent activity log."""

    DEFAULT_CSS = """
    AlertsPanel {
        height: 100%;
        border: solid magenta;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entries = []

    def update_log(self, entries: list[dict]):
        """Update activity log entries."""
        self._entries = entries[-10:]
        self._render()

    def _render(self):
        table = Table(
            title="AGENT ACTIVITY",
            title_style="bold magenta",
            expand=True,
            padding=(0, 1),
            show_header=False,
        )
        table.add_column("Entry", ratio=1)

        agent_colors = {
            "scanner": "green",
            "analyst": "cyan",
            "risk": "yellow",
            "executor": "bright_white",
        }

        for entry in self._entries:
            ts = entry.get("timestamp", "")
            if isinstance(ts, str) and len(ts) > 11:
                time_str = ts[11:16]
            else:
                time_str = "?"

            agent = entry.get("agent", "?")
            msg = entry.get("message", "")
            color = agent_colors.get(agent, "white")

            text = Text()
            text.append(f"[{time_str}] ", style="dim")
            text.append(f"{agent}: ", style=f"bold {color}")
            text.append(msg[:60])

            table.add_row(text)

        if not self._entries:
            table.add_row(Text("Waiting for agent activity...", style="dim"))

        self.update(table)
