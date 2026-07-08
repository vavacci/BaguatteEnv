"""WebKitCapture — in-browser capture via ios-webkit-debug-proxy.

Manages iwdp (auto-discovering the per-boot webinspectord_sim unix socket) and runs
a WebKit-inspector client in a background thread that subscribes to the Network
domain and dumps matched flows. Safari makes the real connection, so egress TLS is
the simulator's own (see docs/COMPARISON: still not a real iPhone, but not a proxy).

Stealth: only Network.enable + passive reads. We never send Network.setCacheDisabled
or any Emulation override (they leave detectable signals). Do not add them.

Requires: `brew install ios-webkit-debug-proxy`, and `pip install websockets`.
Precondition: a simulator is booted with Safari showing a real (inspectable) page.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ..errors import CaptureError
from .base import CaptureBackend, RecordWriter


def _find_sim_socket() -> str | None:
    try:
        out = subprocess.run(["lsof", "-aUc", "launchd_sim"],
                             capture_output=True, text=True).stdout
    except FileNotFoundError:
        return None
    for line in out.splitlines():
        m = re.search(r"(/private/tmp/com\.apple\.launchd\.[^\s]*webinspectord_sim\.socket)", line)
        if m:
            return m.group(1)
    return None


class WebKitCapture(CaptureBackend):
    def __init__(self, cfg, base_dir: Path) -> None:
        cap = cfg.capture
        self.output_dir = cfg.captures_path
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.output_dir / "_index.jsonl"
        self.writer = RecordWriter(self.output_dir, cap.hosts, cap.path_prefixes)
        self.device_port = cap.iwdp_device_port
        self.page_port = cap.webkit_page_port
        self.page_range = f"{cap.webkit_page_port}-{cap.webkit_page_port + 100}"

        self._iwdp: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reqs: dict[str, dict] = {}
        self._id = 0
        self._ws = None

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        sock = _find_sim_socket()
        if not sock:
            raise CaptureError("no webinspectord_sim socket found — is a simulator booted "
                               "with Safari open on a real page?")
        log = (self.output_dir / "iwdp.log").open("w")
        self._iwdp = subprocess.Popen(
            ["ios_webkit_debug_proxy", "-F",
             "-c", f"null:{self.device_port},:{self.page_range}",
             "-s", f"unix:{sock}"],
            stdout=log, stderr=subprocess.STDOUT,
        )
        time.sleep(1.5)
        if self._iwdp.poll() is not None:
            raise CaptureError(f"ios_webkit_debug_proxy exited immediately — see {self.output_dir}/iwdp.log")

        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        time.sleep(1.0)  # give the WS time to attach + Network.enable

    def stop(self) -> None:
        self._stopping.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._iwdp and self._iwdp.poll() is None:
            self._iwdp.terminate()
            try:
                self._iwdp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._iwdp.kill()

    # ---- background asyncio worker --------------------------------------
    def _discover_page_ws(self) -> str:
        raw = urllib.request.urlopen(f"http://localhost:{self.page_port}/json", timeout=5).read()
        pages = json.loads(raw)
        if not pages:
            raise CaptureError(f"no inspectable pages at :{self.page_port}/json")
        return pages[0]["webSocketDebuggerUrl"]

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception as e:  # surface in log; don't crash the host process
            print(f"[webkit-capture] worker stopped: {e}")

    async def _async_main(self) -> None:
        import websockets  # imported here so the module loads without the dep present
        self._loop = asyncio.get_event_loop()
        ws_url = self._discover_page_ws()
        async with websockets.connect(ws_url, max_size=None) as ws:
            self._ws = ws
            await self._call("Network.enable")
            print(f"[webkit-capture] attached, Network enabled: {ws_url}")
            while not self._stopping.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                msg = json.loads(raw)
                mid = msg.get("id")
                if mid is not None and mid in self._pending:
                    self._pending.pop(mid).set_result(msg)
                elif "method" in msg:
                    asyncio.create_task(self._on_event(msg["method"], msg.get("params", {})))

    async def _call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        fut = self._loop.create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return await fut

    async def _on_event(self, method: str, p: dict) -> None:
        rid = p.get("requestId")
        if not rid:
            return
        if method == "Network.requestWillBeSent":
            req = p.get("request", {})
            self._reqs[rid] = {"method": req.get("method"), "url": req.get("url"),
                               "req_headers": req.get("headers", {}), "post_data": req.get("postData")}
        elif method == "Network.responseReceived":
            self._reqs.setdefault(rid, {})["response"] = p.get("response", {})
        elif method == "Network.loadingFinished":
            await self._finalize(rid)
        elif method == "Network.loadingFailed":
            self._reqs.pop(rid, None)

    async def _finalize(self, rid: str) -> None:
        meta = self._reqs.pop(rid, None)
        if not meta:
            return
        resp = meta.get("response", {}) or {}
        url = resp.get("url") or meta.get("url") or ""
        u = urlparse(url)
        if not self.writer.matches(u.hostname or "", u.path or ""):
            return
        body = None
        try:
            r = await self._call("Network.getResponseBody", {"requestId": rid})
            res = r.get("result", {})
            body = ({"encoding": "base64", "base64": res.get("body", "")}
                    if res.get("base64Encoded")
                    else {"encoding": "text", "text": res.get("body", "")})
        except Exception as e:
            body = {"error": f"getResponseBody failed: {e}"}
        req_body = ({"encoding": "text", "text": meta["post_data"]}
                    if meta.get("post_data") else None)
        record = {
            "timestamp": time.time(),
            "method": meta.get("method"), "url": url,
            "host": u.hostname, "path": u.path, "status_code": resp.get("status"),
            "request": {"headers": meta.get("req_headers", {}), "body": req_body},
            "response": {"headers": resp.get("headers", {}), "body": body},
        }
        self.writer.write(record)
        print(f"[webkit-capture] {record['status_code']} {record['method']} {url}")
