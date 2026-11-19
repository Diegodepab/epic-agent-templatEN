"""CLI entrypoint for {{PROJECT_NAME}}."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{{PROJECT_NAME}}", description="{{PROJECT_DESCRIPTION}}")
    parser.add_argument("--version", action="store_true", help="Show version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from {{PACKAGE_NAME}} import __version__

        print(__version__)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
