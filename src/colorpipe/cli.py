"""Command-line entry point.

v1 is intentionally small: one input, one new output, an explicit profile.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .types import Settings
from .decode import describe_raw, load_raw
from .pipeline import convert_raw


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="orf2dng",
        description="Color-only ORF -> DNG converter (route B, visually equivalent).",
    )
    p.add_argument("input", type=Path, help="input .orf/.ori")
    p.add_argument("output", type=Path, nargs="?", help="output .dng (required unless --inspect)")
    p.add_argument("--profile", type=Path, default=None, help="user-supplied DCP (required for conversion)")
    p.add_argument("--algorithm", choices=("hifi", "v3"), default="hifi", help="hifi only; v3 is reserved")
    p.add_argument("--v3-mode", type=int, choices=(0, 1), default=0, help="reserved; must remain 0")
    p.add_argument("--threads", type=int, default=1, help="reserved; v1 is single-threaded")
    p.add_argument("--plan", action="store_true", help="print the requested plan without decoding or validating a profile")
    p.add_argument("--inspect", action="store_true", help="decode and print M0 metadata as JSON")
    p.add_argument("--version", action="version", version=f"colorpipe {__version__}")
    return p


def _plan(args: argparse.Namespace) -> dict:
    settings = Settings(
        algorithm=args.algorithm,
        v3_mode=args.v3_mode,
        profile=str(args.profile) if args.profile else None,
    )
    settings.validate()
    return {
        "input": str(args.input),
        "output": str(args.output),
        "settings": {
            "algorithm": settings.algorithm,
            "v3_mode": settings.v3_mode,
            "bit_depth": settings.bit_depth,
            "compression": settings.compression,
            "profile": settings.profile,
        },
        "threads": args.threads,
        "note": "Default HiFi camera-linear DNG; conversion requires a user-supplied DCP profile.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.threads != 1:
        parser.error("only --threads 1 is supported")
    if args.algorithm != 'hifi' or args.v3_mode != 0:
        print('error: only default HiFi is implemented; v3 and nonzero --v3-mode are unsupported', file=sys.stderr)
        return 2
    if args.inspect:
        if args.output is not None or args.plan:
            parser.error("--inspect accepts one input and cannot be combined with --plan")
        try:
            print(json.dumps(describe_raw(load_raw(args.input)), indent=2, ensure_ascii=False, allow_nan=False))
        except (ValueError, OSError, ImportError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.output is None:
        parser.error("output is required unless --inspect is used")

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2
    if args.input.suffix.lower() not in ('.orf', '.ori') or args.output.suffix.lower() != '.dng':
        print('error: conversion requires .orf/.ori input and .dng output', file=sys.stderr)
        return 2
    if args.output.exists() or args.output.is_symlink():
        print(f"error: refusing to overwrite: {args.output}", file=sys.stderr)
        return 2

    if args.plan:
        print(json.dumps(_plan(args), indent=2, ensure_ascii=False))
        return 0

    settings = Settings(
        algorithm=args.algorithm,
        v3_mode=args.v3_mode,
        profile=str(args.profile) if args.profile else None,
    )
    try:
        output = convert_raw(args.input, args.output, settings)
    except (ValueError, OSError, ImportError, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
