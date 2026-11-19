---
name: long-context-state-manager
description: Maintains and compresses working context during long-running chats by keeping .agents/current_state.md as a bounded, deterministic single source of truth (strict objective, invariant decisions, completed milestones, active files, and next step). Use proactively whenever a conversation grows long, after completing a milestone, or before pivoting tasks to prevent goal drift and context saturation. Not for static documentation publishing.
---

# Long-Context State Manager

Prevent context saturation and goal drift in long conversations by anchoring reasoning to `.agents/current_state.md`. Treat `scripts/state_manager.py` as a black box: run `--help` first instead of reading source internals.

## Decision Tree

- **Starting a new task or multi-step phase?** -> `init --objective "..."`
- **Resuming or turning after a long conversation / compaction?** -> `status` (re-reads anchor + detects git drift)
- **Locked an architectural decision or finished a milestone?** -> `update --add-decision ... --complete ...`
- **`status` warns budget exceeded (`>80` lines)?** -> `compact --keep-completed 5`

## What Lives Where

| Artifact | Purpose | Budget / Lifecycle |
|---|---|---|
| `scripts/state_manager.py` | Deterministic CLI to init, update, compact, and check drift | Python 3.11+ stdlib only |
| `.agents/current_state.md` | Active Single Source of Truth read before major edits | Hard budget: `<= 80` lines / `<= 3,500` chars |
| `.agents/state_history.jsonl` | Append-only archive of compacted milestones | Ignored by Git (`.gitignore`) |

## Operational Workflow

### 1. Anchor on Task Start
Initialize the state file as soon as an objective and key constraints are agreed:

```bash
python3 .agents/skills/long-context-state-manager/scripts/state_manager.py init \
  --objective "Implement exact feature X without breaking contract Y"
```

### 2. Re-Read Before Every Major Step in Long Chats
When the chat has many turns or after any context compaction, read `.agents/current_state.md` (or run `status`) **before** proposing edits. Treat `Invariant Decisions` as hard constraints even if earlier chat messages were noisy.

```bash
python3 .agents/skills/long-context-state-manager/scripts/state_manager.py status
```

### 3. Record Decisions and Milestones Incrementally
Update the state immediately after locking an architectural decision or finishing a milestone:

```bash
python3 .agents/skills/long-context-state-manager/scripts/state_manager.py update \
  --add-decision "Use DuckDB with parameterized SQL; no ORM" \
  --complete "Implemented ingestion pipeline in src/ingest.py" \
  --file "src/ingest.py" \
  --next "Write edge-case tests and run anti-laziness verifier"
```

### 4. Compact Proactively When Budget Warnings Appear
If `status` or `update` warns that the budget (`80` lines / `3,500` chars) is exceeded—or exits with code `2`—compact older milestones into `.agents/state_history.jsonl`:

```bash
python3 .agents/skills/long-context-state-manager/scripts/state_manager.py compact --keep-completed 5
```

## Mandatory Rules

1. Never delete `Invariant Decisions` silently; only update them if the user explicitly reverses a decision.
2. When `status` reports git-modified files missing from `Active Files`, reconcile them before moving to the next task.
3. Never treat chat memory as authoritative when it conflicts with `.agents/current_state.md`.
