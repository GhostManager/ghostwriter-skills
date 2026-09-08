#!/usr/bin/env python3
"""Apply the report-readiness skill's mutually exclusive grade rules."""

from __future__ import annotations

import argparse
import sys


def grade_readiness(
    blockers: int,
    warnings: int,
    *,
    essential_unassessed: bool = False,
    fundamental_failure: bool = False,
) -> str:
    """Return A, B, C, or D from reviewed issue counts and coverage state."""

    if blockers < 0 or warnings < 0:
        raise ValueError("issue counts cannot be negative")
    if fundamental_failure or blockers >= 3:
        return "D"
    if blockers or essential_unassessed:
        return "C"
    if warnings:
        return "B"
    return "A"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blockers", type=int, required=True)
    parser.add_argument("--warnings", type=int, required=True)
    parser.add_argument("--essential-unassessed", action="store_true")
    parser.add_argument("--fundamental-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        grade = grade_readiness(
            args.blockers,
            args.warnings,
            essential_unassessed=args.essential_unassessed,
            fundamental_failure=args.fundamental_failure,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(grade)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
