from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import (
    AppConfig,
    load_config,
    merge_cli_overrides,
    parse_inline_mapping,
    parse_inline_replacement,
)
from .engine import run_sync
from .report import render_console_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-rerooter")
    parser.add_argument("--src", help="source root path")
    parser.add_argument("--dst", help="destination root path")
    parser.add_argument("--mapconfig", help="path to .json/.yaml/.yml config")
    parser.add_argument("--map", action="append", default=[], help="path mapping: from=to")
    parser.add_argument("--replace", action="append", default=[], help="content replacement: from=to")
    parser.add_argument("--include", action="append", default=[], help="include glob (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], help="exclude glob (repeatable)")
    parser.add_argument("--apply", action="store_true", help="apply changes (default dry-run)")
    parser.add_argument("--syncback", action="store_true", help="reverse sync target back to source")
    parser.add_argument("--no-verify", action="store_true", help="skip verification steps")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colored console output")
    parser.add_argument(
        "--log-level",
        choices=["summary", "normal", "debug"],
        default="debug",
        help="console logging detail level (default: debug)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.mapconfig).resolve() if args.mapconfig else None

    config = _build_config(
        config_path=config_path,
        map_values=args.map,
        replace_values=args.replace,
        include_values=args.include,
        exclude_values=args.exclude,
        no_verify=args.no_verify,
    )

    src_value, dst_value = _resolve_paths(args.src, args.dst, config, parser)
    src_root = Path(src_value).resolve()
    dst_root = Path(dst_value).resolve()

    if not src_root.exists() or not src_root.is_dir():
        parser.error(f"--src not found or not a directory: {src_root}")

    dry_run = not args.apply
    report = run_sync(
        src_root=src_root,
        dst_root=dst_root,
        config=config,
        dry_run=dry_run,
        syncback=args.syncback,
    )
    print(
        render_console_report(
            report,
            dry_run=dry_run,
            use_color=(not args.no_color),
            log_level=args.log_level,
        )
    )

    if report.errors:
        return 1
    if any(not result.ok for result in report.verify_results):
        return 2
    return 0


def _build_config(
    config_path: Path | None,
    map_values: list[str],
    replace_values: list[str],
    include_values: list[str],
    exclude_values: list[str],
    no_verify: bool,
) -> AppConfig:
    base = load_config(config_path)
    inline_mappings = parse_inline_mapping(map_values)
    inline_replacements = parse_inline_replacement(replace_values)
    config = merge_cli_overrides(
        base=base,
        inline_mappings=inline_mappings,
        inline_replacements=inline_replacements,
        includes=include_values,
        excludes=exclude_values,
    )
    if no_verify:
        config.verify.enabled = False
    return config


def _resolve_paths(
    src_arg: str | None,
    dst_arg: str | None,
    config: AppConfig,
    parser: argparse.ArgumentParser,
) -> tuple[str, str]:
    src_value = src_arg or config.source
    dst_value = dst_arg or config.target

    if not src_value:
        parser.error("missing source path: pass --src or set 'source' in --mapconfig")
    if not dst_value:
        parser.error("missing target path: pass --dst or set 'target' in --mapconfig")

    return src_value, dst_value


if __name__ == "__main__":
    sys.exit(main())