"""mitmproxy addon loaded by MitmproxyCapture (`mitmdump -s addon.py`).

Reads its filter + output dir from the config file named in $IOSFARM_CONFIG, and
writes captures via the shared RecordWriter so the on-disk format matches the
WebKit backend exactly. This runs in mitmdump's own process (not sandboxed).
"""
import json
import os
import sys
import time
from pathlib import Path

# make the iosfarm package importable when mitmdump loads this file by path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iosfarm.capture.base import RecordWriter, encode_body  # noqa: E402


def _load_cfg() -> dict:
    p = Path(os.environ.get("IOSFARM_CONFIG", "config.json"))
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


class _Addon:
    def __init__(self) -> None:
        cap = _load_cfg().get("capture", {})
        base = Path(os.environ.get("IOSFARM_CONFIG", "config.json")).resolve().parent
        out = Path(cap.get("output_dir", "captures"))
        out = out if out.is_absolute() else base / out
        self.writer = RecordWriter(out, cap.get("hosts", []), cap.get("path_prefixes", ["/"]))
        self.save_bodies = cap.get("save_bodies", True)
        self.max_body = int(cap.get("max_body_bytes", 5 * 1024 * 1024))

    def response(self, flow) -> None:
        req, resp = flow.request, flow.response
        if not self.writer.matches(req.host, req.path):
            return
        record = {
            "timestamp": time.time(),
            "method": req.method, "url": req.pretty_url,
            "host": req.host, "path": req.path,
            "status_code": resp.status_code if resp else None,
            "request": {"headers": dict(req.headers),
                        "body": encode_body(req.raw_content or b"", self.max_body) if self.save_bodies else None},
            "response": {"headers": dict(resp.headers) if resp else {},
                         "body": encode_body(resp.raw_content or b"", self.max_body) if (self.save_bodies and resp) else None},
        }
        self.writer.write(record)


addons = [_Addon()]
