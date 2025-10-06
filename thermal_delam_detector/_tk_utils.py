"""Utilities for working with Tk in a safe, headless-aware fashion."""
from __future__ import annotations


def can_initialise_tk() -> bool:
    """Return ``True`` when a Tk root window can be created.

    The check is intentionally lightweight so callers can determine whether the
    graphical user interface can launch without triggering intrusive error
    popups when no display server is available.
    """

    try:
        import tkinter as tk  # Local import to avoid hard dependency for callers
    except ModuleNotFoundError:
        return False

    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    else:
        root.withdraw()
        root.destroy()
        return True
