"""Summarise class code counts from a results JSON file."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Count cases per class code from results_all.json")
    parser.add_argument("path", type=Path, default=Path("results_all.json"), nargs="?",
                        help="Path to results JSON (default: results_all.json)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    data = json.loads(args.path.read_text(encoding="utf-8"))
    counter = collections.Counter()
    for case in data.get("cases", []):
        counter.update(case.get("class_codes", []))

    if not counter:
        print("No class codes found in the provided file.")
        return 1

    for code, count in counter.most_common():
        print(f"{code}\t{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
