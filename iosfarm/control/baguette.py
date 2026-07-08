"""BaguetteControl — ControlClient over the `baguette` CLI + `simctl openurl`.

CLI reference (baguette >= iOS 26 build): tap/double-tap/swipe/pinch/pan take
--width/--height (device points); key/type/press/describe-ui/screenshot as below.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..errors import ControlError
from .base import ControlClient


class BaguetteControl(ControlClient):
    def __init__(self, udid: str, width: int = 393, height: int = 852,
                 binary: str = "baguette") -> None:
        self.udid = udid
        self.width = width
        self.height = height
        self.binary = binary

    def _run(self, args: list[str], capture: bool = False) -> str:
        cmd = [self.binary, *args, "--udid", self.udid]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ControlError(f"{' '.join(cmd)}\n{proc.stderr.strip()}")
        return proc.stdout if capture else ""

    def _wh(self) -> list[str]:
        return ["--width", str(self.width), "--height", str(self.height)]

    # ---- navigation ------------------------------------------------------
    def open_url(self, url: str) -> None:
        proc = subprocess.run(["xcrun", "simctl", "openurl", self.udid, url],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise ControlError(f"simctl openurl failed: {proc.stderr.strip()}")

    # ---- input injection -------------------------------------------------
    def tap(self, x: float, y: float, duration: float | None = None) -> None:
        args = ["tap", "--x", str(x), "--y", str(y), *self._wh()]
        if duration is not None:
            args += ["--duration", str(duration)]
        self._run(args)

    def double_tap(self, x: float, y: float) -> None:
        self._run(["double-tap", "--x", str(x), "--y", str(y), *self._wh()])

    def swipe(self, start_x: float, start_y: float, end_x: float, end_y: float,
              duration: float | None = None) -> None:
        args = ["swipe", "--startX", str(start_x), "--startY", str(start_y),
                "--endX", str(end_x), "--endY", str(end_y), *self._wh()]
        if duration is not None:
            args += ["--duration", str(duration)]
        self._run(args)

    def type_text(self, text: str) -> None:
        self._run(["type", "--text", text])

    def key(self, code: str, modifiers: str | None = None) -> None:
        args = ["key", "--code", code]
        if modifiers:
            args += ["--modifiers", modifiers]
        self._run(args)

    def press(self, button: str) -> None:
        self._run(["press", "--button", button])

    # ---- inspection ------------------------------------------------------
    def describe_ui(self) -> Any:
        return json.loads(self._run(["describe-ui"], capture=True))

    def screenshot(self, output: str | Path) -> Path:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run(["screenshot", "--output", str(output)])
        return output
