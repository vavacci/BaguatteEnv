"""SimulatorManager — create / boot / shutdown / erase / resolve one simulator.

Uses `xcrun simctl` (the portable, stable path). A single manager owns one device,
identified by udid ("booted" auto-resolves to the currently booted device). For a
multi-device farm, create one SimulatorManager per udid.
"""
from __future__ import annotations

import json
import subprocess
import time

from ..errors import LifecycleError


def _simctl(*args: str, check: bool = True, capture: bool = True) -> str:
    proc = subprocess.run(["xcrun", "simctl", *args], capture_output=capture, text=True)
    if check and proc.returncode != 0:
        raise LifecycleError(f"simctl {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout if capture else ""


class SimulatorManager:
    def __init__(self, udid: str = "booted",
                 device_type: str | None = None,
                 runtime: str | None = None) -> None:
        self._udid_cfg = udid
        self.device_type = device_type
        self.runtime = runtime
        self._udid: str | None = None if udid == "booted" else udid

    # ---- discovery -------------------------------------------------------
    @staticmethod
    def list_devices() -> dict:
        return json.loads(_simctl("list", "devices", "-j"))

    @staticmethod
    def booted_udids() -> list[str]:
        data = SimulatorManager.list_devices()
        return [d["udid"] for devs in data.get("devices", {}).values()
                for d in devs if d.get("state") == "Booted"]

    @staticmethod
    def find(name: str | None = None, state: str | None = None,
             runtime: str | None = None, available_only: bool = True) -> list[dict]:
        """List devices, optionally filtered by name substring / state / runtime.

        Returns dicts: {"udid","name","state","runtime"}. `runtime` matches a
        substring of the runtime key (e.g. "iOS-17-5"); `state` is exact (e.g. "Booted").
        """
        out: list[dict] = []
        for rt, devs in SimulatorManager.list_devices().get("devices", {}).items():
            if runtime and runtime not in rt:
                continue
            for d in devs:
                if available_only and not d.get("isAvailable", True):
                    continue
                if name and name.lower() not in d.get("name", "").lower():
                    continue
                if state and d.get("state") != state:
                    continue
                out.append({"udid": d["udid"], "name": d.get("name"),
                            "state": d.get("state"), "runtime": rt})
        return out

    @staticmethod
    def find_udid(name: str | None = None, state: str | None = None,
                  runtime: str | None = None) -> str:
        """Return the udid of the first device matching the filters, or raise."""
        matches = SimulatorManager.find(name=name, state=state, runtime=runtime)
        if not matches:
            raise LifecycleError(
                f"no simulator matches name={name!r} state={state!r} runtime={runtime!r}")
        return matches[0]["udid"]

    @property
    def udid(self) -> str:
        """Resolve and cache the concrete udid."""
        if self._udid:
            return self._udid
        booted = self.booted_udids()
        if not booted:
            raise LifecycleError(
                "no booted simulator; boot one (Simulator.app or `xcrun simctl boot <UDID>`) "
                "or set simulator.udid to a concrete UDID in the config")
        self._udid = booted[0]
        return self._udid

    def is_booted(self) -> bool:
        try:
            return self.udid in self.booted_udids()
        except LifecycleError:
            return False

    # ---- lifecycle -------------------------------------------------------
    def create(self, name: str) -> str:
        if not (self.device_type and self.runtime):
            raise LifecycleError("create() needs device_type and runtime in config")
        udid = _simctl("create", name, self.device_type, self.runtime).strip()
        self._udid = udid
        return udid

    def boot(self, wait: bool = True, timeout: float = 120) -> None:
        if self.is_booted():
            return
        _simctl("boot", self.udid, check=False)
        if wait:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.is_booted():
                    return
                time.sleep(1.0)
            raise LifecycleError(f"simulator {self.udid} did not reach Booted within {timeout}s")

    def ensure_booted(self) -> str:
        self.boot(wait=True)
        return self.udid

    def shutdown(self) -> None:
        _simctl("shutdown", self.udid, check=False)

    def erase(self) -> None:
        """Erase device content. NOTE: also drops any trusted proxy CA — reinstall after."""
        was = self.is_booted()
        if was:
            self.shutdown()
        _simctl("erase", self.udid)
        if was:
            self.boot()

    def open_url(self, url: str) -> None:
        _simctl("openurl", self.udid, url, capture=False)
