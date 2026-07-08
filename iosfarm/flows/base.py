"""Flow abstraction + registry.

A Flow is one business process (browse a site, search, collect responses…). It is
handed a started Session and returns a FlowResult. Flows contain ZERO framework
plumbing — no proxy/capture/boot logic — they just drive the Session.

Register a flow with @register; run it by name via get_flow(name).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FlowResult:
    name: str
    params: dict
    captured: int = 0
    data: dict = field(default_factory=dict)
    screenshots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "params": self.params, "captured": self.captured,
                "data": self.data, "screenshots": self.screenshots}


class Flow(ABC):
    name: str = "flow"

    @abstractmethod
    def run(self, session, params: dict) -> FlowResult: ...


_REGISTRY: dict[str, type[Flow]] = {}


def register(cls: type[Flow]) -> type[Flow]:
    _REGISTRY[cls.name] = cls
    return cls


def get_flow(name: str) -> Flow:
    if name not in _REGISTRY:
        raise KeyError(f"unknown flow {name!r}; available: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[name]()


def list_flows() -> list[str]:
    return sorted(_REGISTRY)
