"""AppManager — install / uninstall / launch / terminate a custom app on one sim.

All operations target a single device by udid (via `xcrun simctl`). "booted" is
resolved to the concrete udid, so with multiple booted simulators pass an explicit
udid (see SimulatorManager.find_udid).

Only SIMULATOR-sliced .app bundles install here (no signing needed); real-device
.ipa / App Store apps cannot be installed on the simulator.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..errors import ControlError
from ..lifecycle.simulator import SimulatorManager


def _simctl(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["xcrun", "simctl", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise ControlError(f"simctl {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


class AppManager:
    def __init__(self, udid: str = "booted") -> None:
        # resolve "booted" -> concrete udid once
        self.udid = SimulatorManager(udid).udid

    # ---- install / uninstall --------------------------------------------
    def install(self, app_path: str | Path) -> None:
        app_path = Path(app_path)
        if not app_path.exists():
            raise ControlError(f"app bundle not found: {app_path}")
        _simctl("install", self.udid, str(app_path))

    def uninstall(self, bundle_id: str) -> None:
        _simctl("uninstall", self.udid, bundle_id)

    # ---- launch / terminate ---------------------------------------------
    def launch(self, bundle_id: str, args: list[str] | None = None) -> int | None:
        out = _simctl("launch", self.udid, bundle_id, *(args or []))
        # simctl prints "com.you.app: 12345"
        m = re.search(r":\s*(\d+)", out)
        return int(m.group(1)) if m else None

    def terminate(self, bundle_id: str) -> None:
        _simctl("terminate", self.udid, bundle_id, check=False)

    def relaunch(self, bundle_id: str, args: list[str] | None = None) -> int | None:
        self.terminate(bundle_id)
        return self.launch(bundle_id, args)

    # ---- query -----------------------------------------------------------
    def app_container(self, bundle_id: str, kind: str = "app") -> str:
        """Path to the app's container (kind: app|data|groups). Errors if not installed."""
        return _simctl("get_app_container", self.udid, bundle_id, kind).strip()

    def is_installed(self, bundle_id: str) -> bool:
        proc = subprocess.run(
            ["xcrun", "simctl", "get_app_container", self.udid, bundle_id],
            capture_output=True, text=True)
        return proc.returncode == 0

    def list_apps_raw(self) -> str:
        """Raw `simctl listapps` output (a plist)."""
        return _simctl("listapps", self.udid)

    def installed_bundle_ids(self) -> list[str]:
        """Bundle identifiers currently installed (parsed from listapps)."""
        raw = self.list_apps_raw()
        return sorted(set(re.findall(r'CFBundleIdentifier\s*=\s*"([^"]+)"', raw)))
