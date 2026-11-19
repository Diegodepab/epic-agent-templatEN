---
name: godot-2d-pixel-art-forge
description: Converts HD art into crisp 1x pixel art using perceptual CIELAB k-means palette locking and binary alpha quantization, renders code-defined PixelSpec sprites and palette-swap variants, and enforces strict pixel-art QA gates with onion-skin contact sheets. Use when producing or auditing real 1x pixel art for 2D Godot games without soft-pixel blur. Not for 3D textures.
---

# Godot 2D Pixel Art Forge

Produce and gate crisp, palette-locked 1x pixel art (`alpha` strictly 0 or 255) without soft-pixel gradients, mixels, or outline breaks. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script source code.

## Decision Tree

- **Have an HD illustration or AI-painted "fake pixel art" image?** -> Downscale cleanly via `pixel_downscale_palette.py --target-height <px> --colors <N>`
- **Need consistent palette across an entire cast?** -> Save `--palette-out cast.json` on the first sprite, then pass `--palette-json cast.json` to subsequent ones
- **Designing crisp UI/icons/enemies with palette swaps from code?** -> Author a `.pixelspec.json` (see `examples/slime.pixelspec.json` and `references/pixelspec.md`) and render via `render_pixelspec.py`
- **Auditing pixel frames for partial alpha, off-palette leaks, outline gaps, >10 L-corners, mixels, or loop-seam pops?** -> Run `pixel_qa.py --strict --review review.png --onion --detect-grid`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/pixel_downscale_palette.py` | Premultiplied BOX downscale + pure-NumPy CIELAB k-means + stray-pixel cleaner | 1x RGBA PNG + optional `palette.json` + `_xN` preview |
| `scripts/render_pixelspec.py` | Renders ASCII/hex PixelSpec JSON grids and variant palette swaps | Frame PNGs, `strip.png`, `preview_xN.png` |
| `scripts/pixel_qa.py` | Audits partial alpha, palette lock, outline gaps, L-corners, integer grid & loop seams | JSON QA report + onion-skin `review.png` |
| `references/pixelspec.md` | Full schema spec for `codeart2d.pixelspec.v1` matrices & variants | Authoring guide |
| `references/pixel-proportions-and-scales.md` | Arcade `32/48/64/96px` proportions, binary alpha, rim closing & prop palette locking | Scale & silhouette spec |
| `examples/slime.pixelspec.json` | Reference PixelSpec showing `base` and `crimson` variants | Copyable starter spec |
| `scripts/codeart_core.py`, `forge_core.py` | Local shared pixel quantization & raster helper modules (imported by forge scripts) | Shared helper modules |

## Commands

```bash
python3 .agents/skills/godot-2d-pixel-art-forge/scripts/pixel_downscale_palette.py --help
python3 .agents/skills/godot-2d-pixel-art-forge/scripts/pixel_downscale_palette.py \
  raw_hero.png -o hero_1x.png --target-height 64 --colors 24 --palette-out cast_palette.json --preview-scale 4
python3 .agents/skills/godot-2d-pixel-art-forge/scripts/render_pixelspec.py \
  --spec examples/slime.pixelspec.json --out out/slime --variant all
python3 .agents/skills/godot-2d-pixel-art-forge/scripts/pixel_qa.py \
  --input "out/slime/base/*.png" --detect-grid --onion --review out/slime/qa_review.png --strict
```
