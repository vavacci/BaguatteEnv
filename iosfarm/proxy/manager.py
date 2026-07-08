"""ProxyManager — set / clear / rotate the Mac system proxy.

Because the iOS Simulator uses the Mac's network stack, the Mac system proxy IS the
simulator's proxy (there is no reliable per-simulator proxy; all booted sims + the
Mac share one egress). So this manager is machine-wide by nature:
  - set_http / set_socks: point the machine (and thus the sim) at a proxy
  - clear: restore (ALWAYS call on teardown, or the Mac keeps routing through a dead proxy)
  - rotate: cycle config.proxy.upstreams to change egress IP between runs

Tip: a non-MITM SOCKS/HTTP upstream changes the egress IP WITHOUT touching TLS, so
pairing WebKit capture + a rotating SOCKS upstream keeps a real-ish Safari TLS while
varying IP (serial, not parallel — one IP at a time for the whole machine).
"""
from __future__ import annotations

import subprocess

from ..errors import ProxyError


def _netsetup(*args: str) -> None:
    proc = subprocess.run(["networksetup", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProxyError(f"networksetup {' '.join(args)} failed: {proc.stderr.strip()}")


class ProxyManager:
    def __init__(self, network_service: str = "Wi-Fi", upstreams=None) -> None:
        self.service = network_service
        self.upstreams = list(upstreams or [])
        self._rotate_idx = -1

    # ---- set individual proxy types -------------------------------------
    def set_http(self, host: str, port: int) -> None:
        _netsetup("-setwebproxy", self.service, host, str(port))
        _netsetup("-setsecurewebproxy", self.service, host, str(port))
        _netsetup("-setwebproxystate", self.service, "on")
        _netsetup("-setsecurewebproxystate", self.service, "on")

    def set_socks(self, host: str, port: int) -> None:
        _netsetup("-setsocksfirewallproxy", self.service, host, str(port))
        _netsetup("-setsocksfirewallproxystate", self.service, "on")

    def apply(self, upstream) -> None:
        """Apply one upstream (http or socks), clearing the other type."""
        if upstream.type == "socks":
            self.set_socks(upstream.host, upstream.port)
            _netsetup("-setwebproxystate", self.service, "off")
            _netsetup("-setsecurewebproxystate", self.service, "off")
        else:
            self.set_http(upstream.host, upstream.port)
            _netsetup("-setsocksfirewallproxystate", self.service, "off")

    def rotate(self):
        """Apply the next configured upstream (round-robin). Returns it, or None."""
        if not self.upstreams:
            return None
        self._rotate_idx = (self._rotate_idx + 1) % len(self.upstreams)
        up = self.upstreams[self._rotate_idx]
        self.apply(up)
        return up

    # ---- teardown / status ----------------------------------------------
    def clear(self) -> None:
        for state in ("-setwebproxystate", "-setsecurewebproxystate", "-setsocksfirewallproxystate"):
            subprocess.run(["networksetup", state, self.service, "off"],
                           capture_output=True, text=True)

    def status(self) -> dict:
        def get(kind: str) -> str:
            return subprocess.run(["networksetup", kind, self.service],
                                  capture_output=True, text=True).stdout.strip()
        return {
            "web": get("-getwebproxy"),
            "secure": get("-getsecurewebproxy"),
            "socks": get("-getsocksfirewallproxy"),
        }

    # ---- CA trust (for MITM capture) ------------------------------------
    @staticmethod
    def trust_ca(udid: str, pem_path: str) -> None:
        """Install a root CA into the simulator trust store (redo after erase)."""
        subprocess.run(["xcrun", "simctl", "keychain", udid, "add-root-cert", pem_path],
                       check=False)
