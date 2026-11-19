---
name: godot-2d-autotile-and-parallax
description: Builds seam-proven 4x4 Wang-16 2D terrain autotile atlases, periodic multi-layer parallax backdrops, spec-driven 2D map layouts with Poisson-disk prop scatter, deterministic BFS navigation reachability proofs, and Godot 4 TileSet/Parallax2D scenes. Use when generating TileSet atlases, validating level reachability/parallax bounds, or exporting 2D maps to Godot 4. Not for 3D terrains.
---

# Godot 2D Autotile and Parallax

Build seamless 2D worlds, periodic parallax layers, mathematically reachable level layouts, and direct Godot 4 scene/TileSet exports locally. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **Generating quick 4x4 Wang-16 atlases, verifying edge seams, or scaffolding a `Parallax2D` scene?** -> Run `autotile_seam_builder.py build|verify|parallax`
- **Building full seam-proven `Wang-16` / `Blob-47` material sets from a spec?** -> Read `references/tiles-and-maps.md` and run `autotile_build.py --material-spec <spec.json>`
- **Building a full top-down 2D map layout + collision solids + BFS reachability proof?** -> Run `layout_build.py --spec <layout.json> --strict-qc` (see `references/layouts-and-parallax.md`)
- **Validating side-scroll controller jump/reachability physics?** -> Run `validate_layout.py --layout <layout.json>`
- **Generating & validating multi-layer periodic parallax backgrounds against camera/zoom extremes?** -> Run `parallax_build.py --spec <parallax.json> --validate` (uses local `validate_parallax.py`)
- **Exporting a `map_bundle.v2` directory straight to Godot 4.3+ `.tscn`/`.tres`?** -> Run `export_godot.py --bundle <map-bundle.json> --output-dir <out>`

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/autotile_seam_builder.py` | Fast Wang-16 atlas generator, edge seam verifier, `Parallax2D` emitter | Exits `1` on neighbor pixel mismatch |
| `scripts/autotile_build.py` | Material-spec terrain autotile generator (Wang-16/81/Blob) with seam QA | Deterministic seeded generator |
| `scripts/layout_build.py` | Spec-driven 2D map builder (`forge_nav.py` BFS reachability & collision solids) | `strict-qc` fails on unreachable spawn/exit |
| `scripts/validate_layout.py` | Side-scroll level grammar validator against player jump/gap physics | Fails on impossible jumps/ceilings |
| `scripts/parallax_build.py` | Periodic wrapping noise ridges/clouds/foreground builder + sweep QA | Verifies zero wrap seam pixels |
| `scripts/validate_parallax.py` | Independent parallax repeat-seam & camera/zoom viewport coverage verifier | Invoked automatically by `parallax_build.py` |
| `scripts/export_godot.py` | Exports `map_bundle.v2` directly to Godot 4.3+ `.tscn`/`.tres` resources | Preserves `forge_nav` blocking shapes |
| `scripts/forge_nav.py`, `forge_core.py`, `codeart_core.py`, `forge_schema.py` | Bundled local collision/BFS solver, imaging, and Draft 2020-12 contract helpers | Zero external dependencies outside skill |
| `references/layouts-and-parallax.md`, `tiles-and-maps.md` | JSON schemas for layouts, parallax plans, and terrain material specs | Schema authoring guides |

## Commands

```bash
python3 .agents/skills/godot-2d-autotile-and-parallax/scripts/autotile_seam_builder.py --help
python3 .agents/skills/godot-2d-autotile-and-parallax/scripts/layout_build.py --spec examples/meadow-layout.json --output-dir out/map --strict-qc
python3 .agents/skills/godot-2d-autotile-and-parallax/scripts/parallax_build.py --spec examples/parallax-gen.json --output-dir out/bg --validate
python3 .agents/skills/godot-2d-autotile-and-parallax/scripts/export_godot.py --help
```
