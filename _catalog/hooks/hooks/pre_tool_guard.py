#!/usr/bin/env python3
"""Universal PreToolUse / BeforeTool safety guardrail for Antigravity, Gemini CLI, and Claude Code."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

READ_ONLY_REF_PATTERN = re.compile(r"(?:^|/)_reference/(?:repos|assets)(?:/|$)")
CATASTROPHIC_RM_PATTERN = re.compile(
    r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*[rR]|--recursive\s+--force|--force\s+--recursive)\s+"
    r"(?:/(?:\*|\s|$)|~(?:/|\s|$)|\"?\$HOME\"?(?:/|\s|$)|\"?\$\{HOME\}\"?(?:/|\s|$))"
)
GIT_PUSH_FORCE_PATTERN = re.compile(r"\bgit\b.*\bpush\b.*(?:\s--force\b|\s-[a-zA-Z]*f\b)")
GIT_MAIN_BRANCH_PATTERN = re.compile(r"(?:\s|:)(?:main|master)(?:\s|$)")
GIT_DESTRUCTIVE_PATTERN = re.compile(
    r"\bgit\b.*(?:\breset\s+--hard\b|\bclean\s+-[a-zA-Z]*(?:f[a-zA-Z]*d|d[a-zA-Z]*f|f[a-zA-Z]*x|x[a-zA-Z]*f))"
)
SHELL_MUTATE_REF_PATTERN = re.compile(
    r"(?:\b(?:rm|mv|rmdir|truncate|tee|chmod|chown)\b|\bsed\s+-i\b|>{1,2})\s*[^\n]*_reference/(?:repos|assets)(?:/|\s|$)"
)

FILE_TOOLS = {"edit_file", "write_file", "replace", "Edit", "Write", "MultiEdit"}
CMD_TOOLS = {"run_command", "run_shell_command", "Bash"}
CLAUDE_ONLY_TOOLS = {"Bash", "Edit", "Write", "MultiEdit"}


def _format_output(dialect: str, decision: str, reason: str = "") -> dict[str, object]:
    if dialect == "claude":
        out: dict[str, object] = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                **({"permissionDecisionReason": reason} if reason else {}),
            }
        }
        return out
    payload: dict[str, object] = {"decision": decision}
    if reason:
        payload["reason"] = reason
    return payload


def _evaluate_file_tool(raw_path: str) -> tuple[str, str]:
    if not raw_path:
        return "allow", ""
    normalized = Path(raw_path).as_posix()
    if READ_ONLY_REF_PATTERN.search(normalized):
        return (
            "ask",
            "Target path is inside read-only _reference/{repos,assets}/. Confirm if modifying reference material is intentional.",
        )
    return "allow", ""


def _evaluate_command_tool(command: str) -> tuple[str, str]:
    cmd = command.strip()
    if not cmd:
        return "allow", ""
    if CATASTROPHIC_RM_PATTERN.search(cmd):
        return "deny", "Blocked catastrophic recursive deletion targeting filesystem root or home directory."
    if GIT_PUSH_FORCE_PATTERN.search(cmd):
        if GIT_MAIN_BRANCH_PATTERN.search(cmd):
            return "deny", "Blocked force-push to main/master branch."
        return "ask", "Confirm force-pushing branch history to remote."
    if GIT_DESTRUCTIVE_PATTERN.search(cmd):
        return "ask", "Confirm destructive Git working-tree command (git reset --hard or git clean)."
    if SHELL_MUTATE_REF_PATTERN.search(cmd):
        return "ask", "Command mutates read-only _reference/{repos,assets}/. Confirm if intentional."
    return "allow", ""


def _extract_normalized_call(payload: object, forced_dialect: str) -> tuple[str, str, str, str]:
    if not isinstance(payload, dict):
        return "antigravity" if forced_dialect == "auto" else forced_dialect, "", "", ""

    # 1. Antigravity IDE shape (`toolCall: {name, args}`)
    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        dialect = "antigravity" if forced_dialect == "auto" else forced_dialect
        name = str(tool_call.get("name") or "")
        raw_args = tool_call.get("args")
        args = raw_args if isinstance(raw_args, dict) else {}
        path_val = str(args.get("Path") or args.get("file_path") or args.get("path") or "")
        cmd_val = str(args.get("CommandLine") or args.get("command") or "")
        return dialect, name, path_val, cmd_val

    # 2. Gemini CLI BeforeTool & Claude Code PreToolUse (`tool_name`, `tool_input`)
    name = str(payload.get("tool_name") or "")
    raw_input = payload.get("tool_input")
    inp = raw_input if isinstance(raw_input, dict) else {}
    if forced_dialect == "auto":
        if payload.get("hook_event_name") == "PreToolUse" or name in CLAUDE_ONLY_TOOLS:
            dialect = "claude"
        else:
            dialect = "gemini"
    else:
        dialect = forced_dialect
    path_val = str(inp.get("file_path") or inp.get("path") or inp.get("Path") or "")
    cmd_val = str(inp.get("command") or inp.get("CommandLine") or "")
    return dialect, name, path_val, cmd_val


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal safety PreToolUse/BeforeTool hook guardrail.")
    parser.add_argument("--dialect", default="auto", choices=["auto", "antigravity", "gemini", "claude"])
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(_format_output("antigravity" if args.dialect == "auto" else args.dialect, "allow")))
        return 0

    dialect, tool_name, file_path, command = _extract_normalized_call(payload, args.dialect)
    if tool_name in FILE_TOOLS:
        decision, reason = _evaluate_file_tool(file_path)
    elif tool_name in CMD_TOOLS:
        decision, reason = _evaluate_command_tool(command)
    else:
        decision, reason = "allow", ""

    print(json.dumps(_format_output(dialect, decision, reason)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
