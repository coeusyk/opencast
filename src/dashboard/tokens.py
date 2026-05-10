import plotly.graph_objects as go

PANEL_BG = "#0e0e0f"
GRID_COLOR = "rgba(255, 255, 255, 0.06)"
TEXT_PRIMARY = "#ededee"
TEXT_SECONDARY = "#8b8b8f"
ACCENT = "#57C7FF"
ECO_COLORS = {"A": "#7CC7FF", "B": "#7BE495", "C": "#F6C177", "D": "#F28DA6", "E": "#B9A5FF"}
BODY_FONT = "'Inter', system-ui, sans-serif"
DISPLAY_FONT = "'Instrument Serif', Georgia, serif"
LINE_COLORS = ["#57C7FF", "#7BE495", "#F6C177", "#F28DA6", "#B9A5FF"]


def _hex_to_rgba(hex_color: str, alpha: float = 0.12) -> str:
    """Convert hex color (e.g., '#57C7FF') to an RGBA string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _apply_plotly_typography(fig: go.Figure, title_size: int) -> None:
    fig.update_layout(
        font=dict(family=BODY_FONT, color=TEXT_PRIMARY),
        title_font=dict(family=DISPLAY_FONT, size=title_size, color=TEXT_PRIMARY),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=PANEL_BG,
    )
    fig.update_xaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_SECONDARY),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_SECONDARY),
    )