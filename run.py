#!/usr/bin/env python3
"""CLI entry point: run a business flow on the iosfarm framework.

    python3 run.py --list
    python3 run.py --flow google_search
    python3 run.py --flow google_search --params '{"query":"anthropic","scrolls":3}'
    python3 run.py --flow google_search --config config.json

Params precedence: --params JSON overrides config.flows[<name>]. The result
(captured count, urls, screenshots) is printed and written to captures/result_<flow>.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from iosfarm import Config, Session
from iosfarm.flows import get_flow, list_flows


def main() -> None:
    ap = argparse.ArgumentParser(description="iosfarm — run an iOS automation+capture flow")
    ap.add_argument("--flow", help="flow name (see --list)")
    ap.add_argument("--config", default="config.json", type=Path)
    ap.add_argument("--params", help="JSON object overriding config.flows[<flow>]")
    ap.add_argument("--list", action="store_true", help="list available flows and exit")
    args = ap.parse_args()

    if args.list or not args.flow:
        print("available flows:", ", ".join(list_flows()))
        return

    cfg = Config.from_file(args.config)
    params = dict(cfg.flows.get(args.flow, {}))
    if args.params:
        params.update(json.loads(args.params))

    flow = get_flow(args.flow)
    with Session(cfg) as session:
        result = flow.run(session, params)

    print("\n=== result ===")
    print(f"  flow:     {result.name}")
    print(f"  params:   {result.params}")
    print(f"  captured: {result.captured} flow(s)")
    for url in result.data.get("urls", [])[:20]:
        print(f"    - {result.data.get('statuses', {}).get(url, '?')}  {url}")

    out = cfg.captures_path / f"result_{result.name}.json"
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved: {out}")


if __name__ == "__main__":
    main()
