---
name: godot-scene-and-input-audit
description: Audits Godot 4 scenes (.tscn), C# gameplay loops, Control UI focus, atomic save systems, and 2D .gdshader files: prints 2D CollisionLayer/CollisionMask matrices, catches physics in _Process or FPS-dependent Lerp, flags controls breaking gamepad focus, verifies atomic versioned user:// saves, and detects Godot 3 shader idioms. Use when implementing 2D gameplay, HUDs, or persistence in Godot 4 C#. Not for sprite pixel alignment.
---

# Godot Scene and Input Audit

Verify 2D physics matrices, frame-rate independent C# movement, full keyboard/gamepad UI navigation, atomic save writes, and Godot 4 shaders automatically. Treat `scripts/audit_scene_and_input.py` as a black box: run `--help` first.

## Decision Tree

- **Modified `.tscn` collision layers, UI `Control` focus, C# `_Process`, `user://` saves, or `.gdshader`?** -> Run `audit_scene_and_input.py --root .`
- **Need implementation patterns?** -> Read the targeted file under `references/` matching the failing check

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/audit_scene_and_input.py` | Audits `.tscn` layers/focus, C# `_Process`/saves, `.gdshader` idioms | Exits `1` on CRITICAL/HIGH + collision matrix |
| `references/fsm-and-data-driven-resources.md` | C# state machines & custom `Resource` definitions | Implementation reference |
| `references/shaders-2d-and-audio.md` | Godot 4 `canvas_item` shaders & polyphonic `AudioStreamPlayer2D` | Implementation reference |
| `references/control-ui-and-gamepad-focus.md` | Responsive `Control` anchors & focus neighbor routing | UI reference |
| `references/atomic-versioned-saves.md` | Atomic `.tmp` -> `.bak` -> rename + schema migration pattern | Persistence reference |

## Commands

```bash
python3 .agents/skills/godot-scene-and-input-audit/scripts/audit_scene_and_input.py \
  --root . \
  --json-out .agents/godot_scene_report.json
```
