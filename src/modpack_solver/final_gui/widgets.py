"""Small reusable Tkinter widgets for final GUI text output."""

from __future__ import annotations

from tkinter import scrolledtext

from modpack_solver.final_gui.theme import COLORS


def create_output_text(parent, *, font_size: int = 11):
    widget = scrolledtext.ScrolledText(
        parent,
        wrap="word",
        font=("Consolas", font_size),
        background=COLORS["panel"],
        foreground=COLORS["text"],
        insertbackground=COLORS["text"],
        relief="solid",
        borderwidth=1,
        padx=12,
        pady=10,
    )
    widget.configure(state="disabled")
    return widget


def set_output_text(widget, text: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.configure(state="disabled")
