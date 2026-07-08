"""Session — the runtime that composes all four modules for a flow to drive.

    lifecycle (SimulatorManager) + control (ControlClient)
    + capture (CaptureBackend) + proxy (ProxyManager)

Use as a context manager: __enter__ ensures the sim is booted, optionally applies a
proxy upstream, and starts capture; __exit__ stops capture and restores the proxy.

A Flow receives a started Session and calls its control + capture methods. Nothing
in Session or the flows is baguette-specific except the control client it's given,
so swapping in a vphone control client moves the whole stack to a real-iOS base.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .control import BaguetteControl
from .control.base import ControlClient
from .capture import make_capture
from .capture.base import CaptureBackend
from .lifecycle import SimulatorManager
from .proxy import ProxyManager


class Session:
    def __init__(self, config: Config,
                 control: ControlClient | None = None,
                 capture: CaptureBackend | None = None) -> None:
        self.cfg = config
        self.captures_dir = config.captures_path

        sim_cfg = config.simulator
        self.simulator = SimulatorManager(
            udid=sim_cfg.udid, device_type=sim_cfg.device_type, runtime=sim_cfg.runtime)
        self.proxy = ProxyManager(config.proxy.network_service, config.proxy.upstreams)

        # control + capture are injectable (swap for vphone / a fake in tests)
        self._control = control
        self._capture = capture
        self._proxy_applied = False

    # ---- lazily-built, udid-resolved control + capture -------------------
    @property
    def control(self) -> ControlClient:
        if self._control is None:
            sc = self.cfg.simulator
            self._control = BaguetteControl(
                udid=self.simulator.udid, width=sc.width, height=sc.height,
                binary=sc.baguette_binary)
        return self._control

    @property
    def capture(self) -> CaptureBackend:
        if self._capture is None:
            self._capture = make_capture(self.cfg, self.cfg.base_dir)
        return self._capture

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> "Session":
        self.simulator.ensure_booted()
        if self.cfg.proxy.enabled and self.cfg.proxy.upstreams:
            up = self.proxy.rotate()
            self._proxy_applied = True
            print(f"[session] proxy upstream: {up.label or up.host}:{up.port}")
        _ = self.control          # resolve udid / build control now (clear errors early)
        self.capture.start()
        print(f"[session] ready: udid={self.simulator.udid} "
              f"backend={self.cfg.capture.backend} captures={self.captures_dir}")
        return self

    def stop(self) -> None:
        try:
            if self._capture is not None:
                self.capture.stop()
        finally:
            if self._proxy_applied:
                self.proxy.clear()

    def __enter__(self) -> "Session":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def rotate_proxy(self):
        up = self.proxy.rotate()
        self._proxy_applied = up is not None
        return up

    # ---- control passthrough (navigation + input + inspection) ----------
    def open(self, url: str) -> None:
        self.control.open_url(url)

    def tap(self, x, y, duration=None): self.control.tap(x, y, duration=duration)
    def double_tap(self, x, y): self.control.double_tap(x, y)
    def swipe(self, sx, sy, ex, ey, duration=None): self.control.swipe(sx, sy, ex, ey, duration=duration)
    def scroll(self, direction="up", distance=None, duration=0.3):
        self.control.scroll(direction, distance, duration)
    def type_text(self, text): self.control.type_text(text)
    def key(self, code, modifiers=None): self.control.key(code, modifiers=modifiers)
    def press(self, button): self.control.press(button)

    def describe_ui(self, save_as: str | None = None) -> Any:
        tree = self.control.describe_ui()
        if save_as:
            (self.captures_dir / f"ui_{save_as}.json").write_text(
                __import__("json").dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        return tree

    def screenshot(self, name: str) -> Path:
        return self.control.screenshot(self.captures_dir / f"shot_{name}.png")

    # ---- capture passthrough --------------------------------------------
    def mark(self) -> int:
        return self.capture.mark()

    def wait_idle(self, idle_seconds: float | None = None, max_seconds: float | None = None) -> int:
        c = self.cfg.capture
        return self.capture.wait_idle(
            idle_seconds if idle_seconds is not None else c.idle_seconds,
            max_seconds if max_seconds is not None else c.wait_seconds)

    def flows_since(self, marker: int) -> list[dict]:
        return self.capture.flows_since(marker)

    def index_since(self, marker: int) -> list[dict]:
        return self.capture.index_since(marker)
