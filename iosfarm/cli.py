"""iosfarm command-line interface.

    python3 run.py sim  list [--state Booted] [--name "iPhone 15"] [--runtime iOS-17]
    python3 run.py sim  udid  --name "iPhone 15" [--state Booted]     # print one udid
    python3 run.py sim  boot     --udid <UDID>
    python3 run.py sim  shutdown --udid <UDID>
    python3 run.py sim  erase    --udid <UDID>

    python3 run.py app  install   --udid <UDID> --app /path/YourApp.app
    python3 run.py app  uninstall --udid <UDID> --bundle com.you.app
    python3 run.py app  launch    --udid <UDID> --bundle com.you.app [--arg foo --arg bar]
    python3 run.py app  terminate --udid <UDID> --bundle com.you.app
    python3 run.py app  list      --udid <UDID>                       # installed bundle ids
    python3 run.py app  container --udid <UDID> --bundle com.you.app

    python3 run.py flow <name> [--params '{"query":"x"}'] [--config config.json]
    python3 run.py flow --list

--udid defaults to "booted" (fails if multiple are booted — pass an explicit UDID).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .apps import AppManager
from .lifecycle import SimulatorManager


# ---- sim subcommands ----------------------------------------------------
def _cmd_sim(a: argparse.Namespace) -> None:
    if a.sim_cmd == "list":
        rows = SimulatorManager.find(name=a.name, state=a.state, runtime=a.runtime)
        for r in rows:
            print(f"{r['state']:<10} {r['udid']}  {r['name']}  [{r['runtime'].split('.')[-1]}]")
        if not rows:
            print("(no matching devices)")
    elif a.sim_cmd == "udid":
        print(SimulatorManager.find_udid(name=a.name, state=a.state, runtime=a.runtime))
    elif a.sim_cmd in ("boot", "shutdown", "erase"):
        sm = SimulatorManager(a.udid)
        getattr(sm, {"boot": "boot", "shutdown": "shutdown", "erase": "erase"}[a.sim_cmd])()
        print(f"{a.sim_cmd}: {sm.udid}")


# ---- app subcommands ----------------------------------------------------
def _cmd_app(a: argparse.Namespace) -> None:
    app = AppManager(a.udid)
    if a.app_cmd == "install":
        app.install(a.app)
        print(f"installed {a.app} -> {app.udid}")
    elif a.app_cmd == "uninstall":
        app.uninstall(a.bundle)
        print(f"uninstalled {a.bundle}")
    elif a.app_cmd == "launch":
        pid = app.launch(a.bundle, a.arg)
        print(f"launched {a.bundle} (pid={pid})")
    elif a.app_cmd == "terminate":
        app.terminate(a.bundle)
        print(f"terminated {a.bundle}")
    elif a.app_cmd == "list":
        for b in app.installed_bundle_ids():
            print(b)
    elif a.app_cmd == "container":
        print(app.app_container(a.bundle, a.kind))


# ---- flow subcommand ----------------------------------------------------
def _cmd_flow(a: argparse.Namespace) -> None:
    from . import Config, Session
    from .flows import get_flow, list_flows

    if a.list or not a.name:
        print("available flows:", ", ".join(list_flows()))
        return
    cfg = Config.from_file(a.config)
    params = dict(cfg.flows.get(a.name, {}))
    if a.params:
        params.update(json.loads(a.params))
    flow = get_flow(a.name)
    with Session(cfg) as session:
        result = flow.run(session, params)
    print("\n=== result ===")
    print(f"  flow={result.name} params={result.params} captured={result.captured}")
    for url in result.data.get("urls", [])[:20]:
        print(f"    - {result.data.get('statuses', {}).get(url, '?')}  {url}")
    out = cfg.captures_path / f"result_{result.name}.json"
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved: {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iosfarm", description="iOS simulator automation + capture")
    sub = p.add_subparsers(dest="group", required=True)

    # sim
    sp = sub.add_parser("sim", help="simulator lifecycle / udid lookup")
    ssub = sp.add_subparsers(dest="sim_cmd", required=True)
    for c in ("list", "udid"):
        q = ssub.add_parser(c)
        q.add_argument("--name"); q.add_argument("--state"); q.add_argument("--runtime")
    for c in ("boot", "shutdown", "erase"):
        q = ssub.add_parser(c)
        q.add_argument("--udid", default="booted")
    sp.set_defaults(func=_cmd_sim)

    # app
    ap = sub.add_parser("app", help="install/uninstall/launch/terminate a custom app")
    asub = ap.add_subparsers(dest="app_cmd", required=True)
    inst = asub.add_parser("install"); inst.add_argument("--udid", default="booted"); inst.add_argument("--app", required=True)
    for c in ("uninstall", "launch", "terminate", "container"):
        q = asub.add_parser(c)
        q.add_argument("--udid", default="booted"); q.add_argument("--bundle", required=True)
        if c == "launch":
            q.add_argument("--arg", action="append", default=[])
        if c == "container":
            q.add_argument("--kind", default="app", choices=["app", "data", "groups"])
    lst = asub.add_parser("list"); lst.add_argument("--udid", default="booted")
    ap.set_defaults(func=_cmd_app)

    # flow
    fp = sub.add_parser("flow", help="run a business flow")
    fp.add_argument("name", nargs="?")
    fp.add_argument("--config", default="config.json", type=Path)
    fp.add_argument("--params")
    fp.add_argument("--list", action="store_true")
    fp.set_defaults(func=_cmd_flow)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
