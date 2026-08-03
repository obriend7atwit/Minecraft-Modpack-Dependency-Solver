"""Light Minecraft-inspired Tkinter theme constants and style setup."""

from __future__ import annotations


COLORS = {
    "grass": "#4F772D",
    "grass_dark": "#31572C",
    "stone": "#6C757D",
    "stone_light": "#D7D9D8",
    "dirt": "#8C5E3C",
    "parchment": "#F4F1E8",
    "panel": "#FCFBF7",
    "error": "#A44A3F",
    "warning": "#C56A32",
    "success": "#3A7D44",
    "technical": "#3D5A80",
    "text": "#252A2D",
}


def configure_ttk_style(style) -> None:
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 11), background=COLORS["parchment"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["parchment"])
    style.configure("Panel.TFrame", background=COLORS["panel"], relief="solid", borderwidth=1)
    style.configure("TLabel", background=COLORS["parchment"], foreground=COLORS["text"])
    style.configure("Header.TLabel", font=("Georgia", 20, "bold"), foreground=COLORS["grass_dark"])
    style.configure("Subheader.TLabel", font=("Georgia", 13, "bold"), foreground=COLORS["dirt"])
    style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"), foreground=COLORS["technical"])
    style.configure("TButton", padding=(10, 6), background=COLORS["stone_light"])
    style.configure("Primary.TButton", background=COLORS["grass"], foreground="white")
    style.map("Primary.TButton", background=[("active", COLORS["grass_dark"])])
    style.configure("TNotebook", background=COLORS["parchment"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(10, 7), background=COLORS["stone_light"])
    style.map("TNotebook.Tab", background=[("selected", COLORS["panel"])], foreground=[("selected", COLORS["grass_dark"])])
