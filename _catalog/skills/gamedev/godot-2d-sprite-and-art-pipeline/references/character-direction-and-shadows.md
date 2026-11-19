# Multi-Direction Character Framing, Foot Anchors & Shadows

Distilled from `spritecast` (`character.md`) 2D character sprite pipeline conventions.

## 1. Directional Facing & Mirror Symmetry Rules

- **4 Diagonals vs. 8 Facings:** Use 8 facings (`south`, `south-east`, `east`, `north-east`, `north`, `north-west`, `west`, `south-west`) for full omnidirectional clarity, or 4 diagonals (`south-east`, `south-west`, `north-east`, `north-west`) to cut sprite sheet count in half while mapping cardinal inputs to the nearest facing.
- **Never Blindly Mirror Asymmetric Gear:** East/west horizontal flip works only for symmetrical silhouettes and shifts stride phase by `n/2` frames (left leg <-> right leg swap). Characters carrying asymmetric props, capes, eye patches, or held weapons must keep per-side sheets or separate hand overlays (`mirror: never`).

## 2. Anchoring & Head/Torso Stability Across Strides

- **Upper-Body Scale Lock (`above ~47%` height):** Compute scale normalization per facing from the upper torso/head silhouette, allowing only legs to extend/compress during stride extremes. Fitting the full frame bounding box causes the head to grow/shrink on crouched frames.
- **Crown Exclusion:** Detect head top by row width (`>= 40%` of head width) rather than antennas, horns, or tall hats so headgear does not skew neck alignment.
- **`ground` vs. `soles` Anchoring:** Choose one world convention and stick to it across all cast members:
  - `ground` (center footprint beneath character center at `30 deg` isometric pitch) sits `4–7 px` higher than shoe bottoms in perspective views.
  - `soles` places the anchor `2 px` below the lowest opaque standing front pixel (ideal for side-scrolling platformers via `audit_spritesheet_metrics.py --gate`).

## 3. Separate Shadow Pass & Transition Joins

- **Dedicated Shadow Strip (~30% alpha black):** Keep floor shadows out of character frames (`Sprite2D` Shadow child rendered underneath Body). Shadows track foot lift and swing offset cleanly even when background tiles change.
- **Action Join Frames:** Add `2–4` explicit transition frames (`ready`, `recover`) between locomotion cycles and attack/skill clips so silhouettes do not pop abruptly on state transitions.
- **Animation VFX Layering:** Center swing trails/splashes around the active stroke frames (`frames_x = 2..3x` body FPS when fast) rather than lagging behind fast weapon arcs.
