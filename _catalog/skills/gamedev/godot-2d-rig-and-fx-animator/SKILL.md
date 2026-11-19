---
name: godot-2d-rig-and-fx-animator
description: Generates hierarchical 2D SVG bone-rig keyframe animations with two-bone IK and ground clamping, portable SVG renders, seamless ambient plate motion loops, deterministic 2D VFX strips & JS runtime modules with verification, harmonic gait-loop selection, Godot 4 canvas_item shaders, and spring curves. Use when animating 2D characters, ambient plates, combat juice, or 2D shaders in Godot 4. Not for 3D meshes.
---

# Godot 2D Rig and FX Animator

Build articulated 2D animations, ambient motion loops, deterministic VFX strips, and Godot 4 shaders locally with zero external path dependencies. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **Animating an articulated 2D character/boss with two-bone IK and ground clamping?** -> Author rig (`references/rig-animation.md`) and run `rig_animate.py --rig <rig.svg> --anim <anim.json> --build-clips --strict-qc`
- **Baking code-drawn VFX animations (`slash`, `sparks`, `ring`, `dust`, `smoke`) + verified JS runtime?** -> Author spec (`references/fx-language.md`) and run `fx_build.py --spec <fx.json> --build-clips --export-runtime`
- **Packaging RGBA frames into verified sprite clips & spritesheets?** -> Run `build_animation_clips.py --manifest clips.json --output-dir out/clips`
- **Finding the cleanest loop interval from gait/idle/hover RGBA frames?** -> Run `gait_loop.py select --frames-dir frames/ --fps 12 --output-dir out/loop --kind gait`
- **Baking seamless water/foliage/shimmer loops or emitting Godot `.gdshader` presets?** -> Run `ambient_bake.py` or `fx_and_shader_kit.py`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/rig_animate.py` | Hierarchical SVG bone keyframe + IK + ground-clamp animator (`--build-clips` calls local builder) | `frames/*.png`, `clips.json`, `rig-report.json` |
| `scripts/fx_build.py` | Deterministic code-drawn combat VFX baker + optional `fx-runtime.mjs` export | Frames, `clips.json`, `fx-report.json` |
| `scripts/fx_verify.mjs` | Trapped sandbox verifier for exported `fx.v1` canvas runtimes (`Node 18+`) | `fx-verify.json` determinism & bounds report |
| `scripts/build_animation_clips.py` | Packages keyed RGBA frames into compiled `animation-clips.json`, strips & preview sheets | Compiled clip bundle + seam metrics |
| `scripts/gait_loop.py` | Harmonic least-squares gait/idle loop selector avoiding half-period snaps | Seam-ranked clip intervals JSON |
| `scripts/svg_render.py` | Portable SVG linter & crisp pixel/vector rasterizer (`references/svg-profile.md`) | Variant PNGs + `codeart-meta.json` |
| `scripts/ambient_bake.py`, `fx_and_shader_kit.py` | Ambient plate loop baker, quick FX strips, Godot 4 `.gdshader`, damped springs | PNG strips, `.gdshader`, JSON curves |
| `scripts/assemble_frames.py`, `forge_matte.py`, `forge_core.py`, `codeart_core.py`, `forge_schema.py` | Local frame utils, chroma keyer, imaging & schema validators | Pure local helpers |
| `references/` | `rig-animation.md`, `svg-profile.md`, `fx-language.md`, `fx-runtime-contract.md`, `runtime/fx-template.mjs` | Contract & authoring specs |

## Commands

```bash
python3 .agents/skills/godot-2d-rig-and-fx-animator/scripts/rig_animate.py --help
python3 .agents/skills/godot-2d-rig-and-fx-animator/scripts/fx_build.py --help
python3 .agents/skills/godot-2d-rig-and-fx-animator/scripts/build_animation_clips.py --help
python3 .agents/skills/godot-2d-rig-and-fx-animator/scripts/gait_loop.py --help
python3 .agents/skills/godot-2d-rig-and-fx-animator/scripts/fx_and_shader_kit.py shader --preset hit_flash --out Shaders/hit_flash.gdshader
```
