"""Typed configuration loaded from a JSON file.

The config is the single source of truth for a run: which simulator, which capture
backend + filter, proxy settings, and per-flow parameters. Paths in the config
(e.g. capture.output_dir) are resolved relative to the config file's directory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SimulatorCfg:
    udid: str = "booted"
    device_type: str | None = None       # e.g. "iPhone 15"; used only when creating
    runtime: str | None = None           # e.g. "iOS-17-5"; used only when creating
    width: int = 393
    height: int = 852
    baguette_binary: str = "baguette"


@dataclass
class CaptureCfg:
    backend: str = "webkit"              # "webkit" | "mitmproxy"
    webkit_page_port: int = 9222
    iwdp_device_port: int = 9221
    output_dir: str = "captures"
    hosts: list[str] = field(default_factory=list)          # substring match; [] = all
    path_prefixes: list[str] = field(default_factory=lambda: ["/"])
    save_bodies: bool = True
    max_body_bytes: int = 5 * 1024 * 1024
    idle_seconds: float = 2.5
    wait_seconds: float = 20.0


@dataclass
class ProxyUpstream:
    label: str = ""
    type: str = "http"                   # "http" | "socks"
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class ProxyCfg:
    network_service: str = "Wi-Fi"
    enabled: bool = False                # apply an upstream on session start?
    # local proxy used by the mitmproxy capture backend:
    host: str = "127.0.0.1"
    port: int = 8080
    # rotatable egress upstreams (non-MITM SOCKS/HTTP that only change IP):
    upstreams: list[ProxyUpstream] = field(default_factory=list)


@dataclass
class Config:
    base_dir: Path
    simulator: SimulatorCfg
    capture: CaptureCfg
    proxy: ProxyCfg
    flows: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def captures_path(self) -> Path:
        p = Path(self.capture.output_dir)
        return p if p.is_absolute() else (self.base_dir / p)

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data, base_dir=path.parent)

    @classmethod
    def from_dict(cls, data: dict, base_dir: Path) -> "Config":
        ups = [ProxyUpstream(**u) for u in data.get("proxy", {}).get("upstreams", [])]
        proxy_raw = {k: v for k, v in data.get("proxy", {}).items() if k != "upstreams"}
        return cls(
            base_dir=base_dir,
            simulator=SimulatorCfg(**data.get("simulator", {})),
            capture=CaptureCfg(**data.get("capture", {})),
            proxy=ProxyCfg(upstreams=ups, **proxy_raw),
            flows=data.get("flows", {}),
            raw=data,
        )
