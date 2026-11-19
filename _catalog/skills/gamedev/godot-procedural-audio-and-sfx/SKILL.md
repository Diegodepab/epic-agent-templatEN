---
name: godot-procedural-audio-and-sfx
description: Synthesizes license-free, peak-normalized 16-bit WAV game sound effects (impacts, UI clicks, footsteps, coins, lasers, whooshes, chimes, risers) with pitch variations ready for Godot 4 AudioStreamRandomizer. Use when adding game feel audio without hunting external asset packs. Not for multi-track adaptive music composition.
---

# Godot Procedural Audio and SFX

Generate deterministic, clip-free `.wav` sound effects ready to wire into Godot 4 `AudioStreamPlayer` / `AudioStreamRandomizer`. Treat `scripts/synth_sfx.py` as a black box: run `--help` first instead of reading source code.

## Decision Tree

- **Need UI feedback (`tick`, `pop`, `chime`, `coin`)?** -> Generate single clip (`--variations 1`)
- **Need combat, footsteps, or repeated actions (`step`, `thud`, `whoosh`, `clang`, `laser`)?** -> Pass `--variations 4` to avoid ear fatigue via `AudioStreamRandomizer`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/synth_sfx.py` | Pure-NumPy + stdlib `wave` DSP synthesizer normalized to `-1 dBFS` | 44.1 kHz 16-bit mono `.wav` clips |

## Commands

```bash
python3 .agents/skills/godot-procedural-audio-and-sfx/scripts/synth_sfx.py --help
python3 .agents/skills/godot-procedural-audio-and-sfx/scripts/synth_sfx.py \
  --preset step --variations 4 --out-dir Assets/audio/sfx
python3 .agents/skills/godot-procedural-audio-and-sfx/scripts/synth_sfx.py \
  --preset coin --out-dir Assets/audio/ui
```
