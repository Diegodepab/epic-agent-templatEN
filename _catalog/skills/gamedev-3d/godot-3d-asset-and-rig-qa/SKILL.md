---
name: godot-3d-asset-and-rig-qa
description: Audits binary GLB/glTF 3D meshes, primitive draw-call budgets, packed ORM textures, and skeleton animations for Godot 4 3D projects. Use when importing or reviewing 3D models and rigs. Never include or use in 2D game projects.
---

# Godot 3D Asset and Rig QA (3D Only)

Inspect 3D `.glb`/`.gltf` assets deterministically before importing heavy meshes into Godot 4 3D scenes. Treat `scripts/audit_glb_assets.py` as a black box: run `--help` first instead of reading source code.

## Decision Tree

- **Importing character rigs, props, or environment `.glb` files?** -> Run `audit_glb_assets.py --root Assets/`
- **High primitive counts (`>24`)?** -> Merge static geometry or generate LODs in Blender before export

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/audit_glb_assets.py` | Pure-stdlib binary GLB/glTF chunk parser & draw-call/texture budget gate | Normalized JSON report + exit `0`/`1` |

## Commands

```bash
python3 .agents/skills/godot-3d-asset-and-rig-qa/scripts/audit_glb_assets.py --help
python3 .agents/skills/godot-3d-asset-and-rig-qa/scripts/audit_glb_assets.py \
  --root Assets/models \
  --max-primitives 24 \
  --json-out .agents/godot_3d_qa.json
```
