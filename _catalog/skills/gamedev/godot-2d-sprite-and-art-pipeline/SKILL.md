---
name: godot-2d-sprite-and-art-pipeline
description: Audits 2D spritesheets via mathematical pixel telemetry (sole-Y jitter, scale popping, edge clipping, islands, alpha halos), keys solid-color AI backgrounds, repairs sheets deterministically with Pillow/NumPy, and exports Godot 4 SpriteFrames (.tres), Scene (.tscn), and C# controllers. Use when importing, cleaning, or rigging 2D sprite animations. Not for 3D skeletal meshes.
---

# Godot 2D Sprite and Art Pipeline

Measure pixel-level defects mathematically, repair spritesheets deterministically, and export clean Godot 4 `.tres`/`.tscn`/`C#` bundles. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script source code.

## Decision Tree

- **AI-generated sprite still has a solid green/blue/magenta background?** -> Run `soft_matte_keyer.py` first (`--bg-color auto`)
- **Evaluating sheet alignment, clipping, islands, or halos?** -> Run `audit_spritesheet_metrics.py <sheet.png> --gate`
- **Fixing sole-Y foot sliding, floating pixels, or bright halos?** -> Run `spritesheet_surgeon.py` (`--defringe --clean-islands`)
- **Ready to drop strips into Godot 4 C#?** -> Export `.tres` + `.tscn` + `partial class` `.cs` via `godot_spriteframes_export.py`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/soft_matte_keyer.py` | Chroma keyer + color despill for solid AI backgrounds | Clean RGBA PNGs + `sprites.json` |
| `scripts/audit_spritesheet_metrics.py` | Computes `sole_y`, `center_x`, clipping, islands, and white halo % | Diagnostic grid PNG + JSON gate |
| `scripts/spritesheet_surgeon.py` | Corner flood-fill, island cleanup, defringe, sole-Y lock, `_flip.png` | Cleaned spritesheet + mirrored `_flip.png` |
| `scripts/godot_spriteframes_export.py` | Generates Godot 4 `SpriteFrames` `.tres`, `.tscn`, shadow strip, and C# controller | Ready-to-load Godot 4 entity folder |
| `references/character-direction-and-shadows.md` | 4-diag vs 8-dir facings, asymmetric gear mirror rules, `ground` vs `soles`, shadow pass & joins | Character sprite pipeline spec |

## Commands

```bash
python3 .agents/skills/godot-2d-sprite-and-art-pipeline/scripts/soft_matte_keyer.py --help
python3 .agents/skills/godot-2d-sprite-and-art-pipeline/scripts/audit_spritesheet_metrics.py assets/player_run.png --cols 8 --rows 1 --gate
python3 .agents/skills/godot-2d-sprite-and-art-pipeline/scripts/spritesheet_surgeon.py assets/player_run.png -o assets/player_clean.png --frame-w 128 --frame-h 128 --defringe
python3 .agents/skills/godot-2d-sprite-and-art-pipeline/scripts/godot_spriteframes_export.py --name PlayerSprite --sheet idle:assets/idle.png:8:loop --frame-w 128 --frame-h 128 --with-shadow --out Scenes/Player
```
