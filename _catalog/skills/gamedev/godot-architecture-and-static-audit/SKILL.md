---
name: godot-architecture-and-static-audit
description: Audits Godot 4 C# (.NET 8+) projects for broken uid:// and Linux case-sensitive res:// paths, circular .tscn dependencies, missing partial class modifiers, unbalanced C# event subscriptions, fragile GetNode paths, and pure C# Domain isolation. Use when refactoring scenes, moving resources, or writing Godot C# gameplay architecture. Not for 2D sprite pixel metrics.
---

# Godot Architecture and Static Audit

Catch broken Godot resource links and C# architectural anti-patterns without launching the editor. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **Moved, renamed, or deleted `.tscn`/`.tres`/`.cs`/asset files?** -> Run `check_godot_project.py . --strict` (`res://` Linux case & `uid://`)
- **Added or refactored C# gameplay/Domain scripts?** -> Run `check_csharp_godot_architecture.py --root .` (`partial`, `-=`, `Domain/` isolation)

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/check_godot_project.py` | Audits `res://` Linux case-sensitivity, `uid://` integrity, `.tscn` trees & cycles | Exits `1` on broken refs |
| `scripts/check_csharp_godot_architecture.py` | Enforces `partial` classes, Domain `using Godot;` isolation, `-=` cleanup, no `/root/` coupling | Exits `1` on CRITICAL/HIGH |
| `references/csharp-domain-and-signals.md` | Pure C# Domain vs Node View patterns, `[Export]`, and typed signals | Architectural reference |

## Commands

### 1. Audit `res://`, `uid://`, and `.tscn` Scene Graph
```bash
python3 .agents/skills/godot-architecture-and-static-audit/scripts/check_godot_project.py . --strict
```

### 2. Audit C# (.NET 8+) Architecture and Signal Safety
```bash
python3 .agents/skills/godot-architecture-and-static-audit/scripts/check_csharp_godot_architecture.py \
  --root . \
  --json-out .agents/godot_arch_report.json
```
