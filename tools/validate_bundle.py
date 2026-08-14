#!/usr/bin/env python3
"""Validate one or more paper bundles against docs/bundle.md.

Prints every problem for every bundle named, and exits nonzero if any
bundle is invalid. Gate 1 of the route runs this in a loop until it
passes clean.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alteksto.bundle import validate_bundle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_bundle.py",
        description="Validate paper bundle directories against the format "
                    "specification in docs/bundle.md.",
    )
    parser.add_argument("bundles", nargs="+", type=Path,
                        help="one or more bundle directories")
    args = parser.parse_args(argv)

    failed = 0
    for bundle in args.bundles:
        problems = validate_bundle(bundle)
        if problems:
            failed += 1
            for problem in problems:
                print(f"validate-bundle: {bundle}: {problem}",
                      file=sys.stderr)
        else:
            print(f"validate-bundle: {bundle}: valid", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
