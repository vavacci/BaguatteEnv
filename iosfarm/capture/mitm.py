"""MitmproxyCapture — capture via a system-proxy MITM (mitmdump + addon).

Starts mitmdump with addon.py, which writes the same record format. This backend
can also REWRITE requests (mitmproxy's strength), but note it re-originates the
upstream TLS, so egress JA3/JA4 becomes the proxy's (see docs/PLAN_A / COMPARISON).

The proxy's system-wide wiring (networksetup) and CA trust are handled here on
start()/stop(); IP-rotation upstreams are handled by proxy.ProxyManager.

Requires: `pip install mitmproxy`.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from ..errors import CaptureError
from ..proxy.manager import ProxyManager
from .base import CaptureBackend

_ADDON = Path(__file__).with_name("addon.py")
_MITM_CA = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"


class MitmproxyCapture(CaptureBackend):
    def __init__(self, cfg, base_dir: Path) -> None:
        self.cfg = cfg
        self.base_dir = base_dir
        self.output_dir = cfg.captures_path
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.output_dir / "_index.jsonl"
        self.host = cfg.proxy.host
        self.port = cfg.proxy.port
        self.proxy = ProxyManager(cfg.proxy.network_service)
        self._mitm: subprocess.Popen | None = None

    def _ensure_ca(self) -> None:
        if _MITM_CA.exists():
            return
        # first run: bounce mitmdump briefly to generate the CA
        p = subprocess.Popen(["mitmdump", "--quiet"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        time.sleep(3)
        p.terminate()
        if not _MITM_CA.exists():
            raise CaptureError("failed to generate mitmproxy CA; run `mitmdump` once manually")

    def start(self) -> None:
        self._ensure_ca()
        # trust CA in the simulator (must be redone after erase)
        udid = self.cfg.simulator.udid
        subprocess.run(["xcrun", "simctl", "keychain", udid, "add-root-cert", str(_MITM_CA)],
                       check=False)
        # point the whole machine's proxy at mitmdump
        self.proxy.set_http(self.host, self.port)
        # launch mitmdump with the addon (addon reads its filter/output from env)
        env = dict(os.environ)
        env["IOSFARM_CONFIG"] = str(self.base_dir / "config.json")
        log = (self.output_dir / "mitm.log").open("w")
        self._mitm = subprocess.Popen(
            ["mitmdump", "--listen-host", self.host, "--listen-port", str(self.port),
             "-s", str(_ADDON)],
            stdout=log, stderr=subprocess.STDOUT, env=env, cwd=self.base_dir,
        )
        time.sleep(1.5)
        if self._mitm.poll() is not None:
            raise CaptureError(f"mitmdump exited immediately — see {self.output_dir}/mitm.log")

    def stop(self) -> None:
        if self._mitm and self._mitm.poll() is None:
            self._mitm.terminate()
            try:
                self._mitm.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._mitm.kill()
        self.proxy.clear()
