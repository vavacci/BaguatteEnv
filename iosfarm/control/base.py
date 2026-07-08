"""ControlClient — the device automation interface.

Any base (simulator via baguette, or a real-iOS VM via vphone) implements this
same surface, so Session and the flows don't care which is underneath.
Coordinates are in device points (same units as the screen width/height).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ControlClient(ABC):
    width: int
    height: int
    udid: str

    # ---- navigation ------------------------------------------------------
    @abstractmethod
    def open_url(self, url: str) -> None: ...

    # ---- input injection -------------------------------------------------
    @abstractmethod
    def tap(self, x: float, y: float, duration: float | None = None) -> None: ...

    @abstractmethod
    def double_tap(self, x: float, y: float) -> None: ...

    @abstractmethod
    def swipe(self, start_x: float, start_y: float, end_x: float, end_y: float,
              duration: float | None = None) -> None: ...

    @abstractmethod
    def type_text(self, text: str) -> None: ...

    @abstractmethod
    def key(self, code: str, modifiers: str | None = None) -> None: ...

    @abstractmethod
    def press(self, button: str) -> None: ...

    # ---- inspection ------------------------------------------------------
    @abstractmethod
    def describe_ui(self) -> Any: ...

    @abstractmethod
    def screenshot(self, output: str | Path) -> Path: ...

    # ---- convenience (default impl in terms of the primitives) -----------
    def scroll(self, direction: str = "up", distance: float | None = None,
               duration: float = 0.3) -> None:
        cx, cy = self.width / 2, self.height / 2
        d = distance if distance is not None else self.height * 0.5
        deltas = {"up": (0, -d), "down": (0, d), "left": (-d, 0), "right": (d, 0)}
        if direction not in deltas:
            raise ValueError(f"bad scroll direction {direction!r}")
        dx, dy = deltas[direction]
        self.swipe(cx, cy, cx + dx, cy + dy, duration=duration)
