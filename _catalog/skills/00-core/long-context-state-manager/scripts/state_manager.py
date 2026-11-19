#!/usr/bin/env python3
"""Deterministic long-context state manager for Antigravity agents.

Maintains `.agents/current_state.md` as a compact, bounded single source of truth
to prevent context degradation and goal drift in long-running conversations.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STATE_PATH = Path(".agents/current_state.md")
DEFAULT_HISTORY_PATH = Path(".agents/state_history.jsonl")
MAX_LINES = 80
MAX_CHARS = 3500

SECTIONS = (
    ("objective", "## Strict Current Objective"),
    ("decisions", "## Invariant Decisions (Do Not Violate)"),
    ("completed", "## Completed Milestones"),
    ("files", "## Active Files & Scope"),
    ("blockers", "## Open Blockers / Risks"),
    ("next", "## Immediate Next Step"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_state() -> dict[str, list[str]]:
    return {key: [] for key, _ in SECTIONS}


def parse_state(path: Path) -> dict[str, list[str]]:
    """Parse `.agents/current_state.md` into structured section lists."""
    state = empty_state()
    if not path.exists():
        return state

    heading_to_key = {heading: key for key, heading in SECTIONS}
    current_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line in heading_to_key:
            current_key = heading_to_key[line]
            continue
        if current_key is None or not line or line.startswith(">") or line.startswith("# "):
            continue
        item = line[2:].strip() if line.startswith("- ") else line
        if item and item != "_None_":
            state[current_key].append(item)
    return state


def render_state(state: dict[str, list[str]]) -> str:
    """Render structured sections into a compact markdown document."""
    lines = [
        "# Current Working State (Single Source of Truth)",
        f"> Last updated: {utc_now()}",
        "",
    ]
    for key, heading in SECTIONS:
        lines.append(heading)
        items = state[key]
        if not items:
            lines.append("- _None_")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def append_unique(items: list[str], values: list[str]) -> None:
    existing = set(items)
    for val in values:
        clean = val.strip()
        if clean and clean not in existing:
            items.append(clean)
            existing.add(clean)


def archive_items(history_path: Path, section: str, items: list[str]) -> None:
    """Append compacted items to `.agents/state_history.jsonl`."""
    if not items:
        return
    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"archived_at": utc_now(), "section": section, "items": items}
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def git_modified_files() -> list[str]:
    """Return untracked or modified paths from git status, or empty if unavailable."""
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip())
    return files


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.state_file)
    if path.exists() and not args.force:
        print(f"State file already exists at {path}. Use --force to overwrite.", file=sys.stderr)
        return 1
    state = empty_state()
    if args.objective:
        state["objective"] = [args.objective.strip()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_state(state), encoding="utf-8")
    print(f"Initialized {path}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    path = Path(args.state_file)
    state = parse_state(path)

    if args.objective is not None:
        state["objective"] = [args.objective.strip()]
    if args.next is not None:
        state["next"] = [args.next.strip()] if args.next.strip() else []

    append_unique(state["decisions"], args.add_decision)
    append_unique(state["completed"], args.complete)
    append_unique(state["files"], args.file)
    append_unique(state["blockers"], args.blocker)

    if args.resolve_blocker:
        to_remove = {b.strip() for b in args.resolve_blocker}
        state["blockers"] = [b for b in state["blockers"] if b not in to_remove]

    rendered = render_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")

    line_count = len(rendered.splitlines())
    char_count = len(rendered)
    print(f"Updated {path} ({line_count}/{MAX_LINES} lines, {char_count}/{MAX_CHARS} chars)")
    if line_count > MAX_LINES or char_count > MAX_CHARS:
        print("WARNING: State budget exceeded. Run `compact` to archive older milestones.", file=sys.stderr)
    return 0


def cmd_compact(args: argparse.Namespace) -> int:
    path = Path(args.state_file)
    if not path.exists():
        print(f"No state file at {path}", file=sys.stderr)
        return 1

    state = parse_state(path)
    history = Path(args.history_file)
    keep = max(1, args.keep_completed)
    archived_count = 0

    if len(state["completed"]) > keep:
        overflow = state["completed"][:-keep]
        state["completed"] = state["completed"][-keep:]
        archive_items(history, "completed", overflow)
        archived_count += len(overflow)

    if len(state["files"]) > args.keep_files:
        overflow_files = state["files"][: -args.keep_files]
        state["files"] = state["files"][-args.keep_files :]
        archive_items(history, "files", overflow_files)
        archived_count += len(overflow_files)

    rendered = render_state(state)
    path.write_text(rendered, encoding="utf-8")
    print(
        f"Compacted {path}: archived {archived_count} items -> "
        f"{len(rendered.splitlines())} lines, {len(rendered)} chars"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.state_file)
    if not path.exists():
        print(f"Missing {path}. Run `init --objective \"...\"` first.", file=sys.stderr)
        return 1

    content = path.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    char_count = len(content)
    state = parse_state(path)

    print(content)
    print(f"--- Budget: {line_count}/{MAX_LINES} lines | {char_count}/{MAX_CHARS} chars ---")

    git_files = git_modified_files()
    tracked_files = set(state["files"])
    untracked_in_state = [f for f in git_files if f not in tracked_files and not f.startswith(".agents/")]
    if untracked_in_state:
        print("Drift warning — git modified files not recorded in Active Files:")
        for item in untracked_in_state[:10]:
            print(f"  - {item}")

    if line_count > MAX_LINES or char_count > MAX_CHARS:
        print("FAIL: State file exceeds context budget. Run `compact`.", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage compact long-context working state.")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize .agents/current_state.md")
    p_init.add_argument("--objective", required=True, help="Strict current objective")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing state file")
    p_init.set_defaults(func=cmd_init)

    p_upd = sub.add_parser("update", help="Update state sections incrementally")
    p_upd.add_argument("--objective", help="Replace strict current objective")
    p_upd.add_argument("--add-decision", action="append", default=[], help="Add invariant architectural decision")
    p_upd.add_argument("--complete", action="append", default=[], help="Record completed milestone")
    p_upd.add_argument("--file", action="append", default=[], help="Record active touched file")
    p_upd.add_argument("--blocker", action="append", default=[], help="Record open blocker")
    p_upd.add_argument("--resolve-blocker", action="append", default=[], help="Remove resolved blocker")
    p_upd.add_argument("--next", help="Set immediate next step")
    p_upd.set_defaults(func=cmd_update)

    p_cmp = sub.add_parser("compact", help="Archive older milestones to keep state compact")
    p_cmp.add_argument("--keep-completed", type=int, default=5)
    p_cmp.add_argument("--keep-files", type=int, default=12)
    p_cmp.set_defaults(func=cmd_compact)

    p_st = sub.add_parser("status", help="Print state, budget usage, and git drift")
    p_st.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
