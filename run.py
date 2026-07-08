#!/usr/bin/env python3
"""iosfarm CLI entry point.

    python3 run.py sim  list | udid | boot | shutdown | erase
    python3 run.py app  install | uninstall | launch | terminate | list | container
    python3 run.py flow <name> [--params '{...}']

Equivalent to `python3 -m iosfarm ...`. See `python3 run.py -h` and iosfarm/cli.py.
"""
from iosfarm.cli import main

if __name__ == "__main__":
    main()
