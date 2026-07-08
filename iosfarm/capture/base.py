"""Capture interface + the shared on-disk record format.

Every backend writes one JSON file per captured flow into output_dir, and appends
one line to output_dir/_index.jsonl. Downstream tooling (Session.flows_since, any
decoder you plug in) only depends on this schema, so backends are interchangeable.

Record schema (captures/<ts>_<host>_<path>_<n>.json):
    {
      "timestamp": float,
      "method": str, "url": str, "host": str, "path": str, "status_code": int|null,
      "request":  {"headers": {...}, "body": <body>|null},
      "response": {"headers": {...}, "body": <body>|null}
    }
    <body> = {"encoding":"text","text":...} | {"encoding":"base64","base64":...}
             (+ "length", "truncated" for proxy-captured bodies)
"""
from __future__ import annotations

import base64
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


def _sanitize(text: str, limit: int = 80) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "").strip("_")
    return text[:limit] or "root"


def encode_body(raw: bytes, max_bytes: int) -> dict:
    length = len(raw)
    truncated = length > max_bytes
    clipped = raw[:max_bytes]
    try:
        return {"encoding": "text", "text": clipped.decode("utf-8"),
                "length": length, "truncated": truncated}
    except UnicodeDecodeError:
        return {"encoding": "base64", "base64": base64.b64encode(clipped).decode("ascii"),
                "length": length, "truncated": truncated}


class RecordWriter:
    """Shared filter + writer used by both backends (and the mitmproxy addon)."""

    def __init__(self, output_dir: str | Path, hosts: list[str] | None = None,
                 path_prefixes: list[str] | None = None) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.output_dir / "_index.jsonl"
        self.hosts = [h.lower() for h in (hosts or [])]
        self.path_prefixes = path_prefixes if path_prefixes is not None else ["/"]
        self.count = 0

    def matches(self, host: str, path: str) -> bool:
        host = (host or "").lower()
        host_ok = not self.hosts or any(h in host for h in self.hosts)
        path_ok = not self.path_prefixes or any((path or "").startswith(p) for p in self.path_prefixes)
        return host_ok and path_ok

    def write(self, record: dict) -> str:
        self.count += 1
        ts = record.get("timestamp") or time.time()
        fname = f"{ts:.3f}_{_sanitize(record.get('host'))}_{_sanitize(record.get('path'))}_{self.count}.json"
        (self.output_dir / fname).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "timestamp": ts, "file": fname, "method": record.get("method"),
                "url": record.get("url"), "status_code": record.get("status_code"),
            }, ensure_ascii=False) + "\n")
        return fname


class CaptureBackend(ABC):
    """Lifecycle + read surface for a capture layer."""

    output_dir: Path
    index_path: Path

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    # ---- read helpers (shared) ------------------------------------------
    def index_count(self) -> int:
        if not self.index_path.exists():
            return 0
        with self.index_path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def mark(self) -> int:
        """Return a marker (current index size) to bound a later flows_since()."""
        return self.index_count()

    def wait_idle(self, idle_seconds: float, max_seconds: float) -> int:
        """Block until no new captures for idle_seconds; return #new since call."""
        start = self.index_count()
        deadline = time.monotonic() + max_seconds
        last_count = start
        last_change = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(0.5)
            now = self.index_count()
            if now != last_count:
                last_count = now
                last_change = time.monotonic()
            elif time.monotonic() - last_change >= idle_seconds:
                break
        return last_count - start

    def index_since(self, marker: int) -> list[dict]:
        if not self.index_path.exists():
            return []
        rows: list[dict] = []
        with self.index_path.open("r", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i < marker:
                    continue
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def flows_since(self, marker: int) -> list[dict]:
        out: list[dict] = []
        for row in self.index_since(marker):
            f = self.output_dir / row["file"]
            if f.exists():
                out.append(json.loads(f.read_text(encoding="utf-8")))
        return out
