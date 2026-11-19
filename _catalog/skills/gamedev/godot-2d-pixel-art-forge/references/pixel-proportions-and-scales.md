# Arcade Pixel-Art Proportions & Scales

Distilled from `spritecast` (`pixel.md`) pixel-art sprite engineering rules.

## 1. Resolution Ladder & Chibi / Normal Ratios

| Target Sprite Height | Character Silhouette | Rule |
| :--- | :--- | :--- |
| **`96 px`** | Normal proportions (~6–7 heads tall) | Default readable arcade character scale (94–100 px figure inside cell) |
| **`64 px`** | Compact / chibi (~3 heads tall) | Required super-deformed design: larger head, short thick limbs separated from torso, larger footwear; scaling down normal proportions loses facial readability |
| **`32 px` / `48 px`** | Ultra-compact retro | Author cleanly at `64 px` first (or PixelSpec grid directly) and integer-reduce downward; never rasterize blurry features below 64 px directly |

## 2. Alpha, Outlines & Palette Discipline

- **Binary Alpha (`0` or `255`) for Solid Geometry:** Keep character bodies hard-edged (`alpha 0` or `255`). Reserve stepped semi-transparency (`~28%`, `47%`, `69%`) strictly for soft atmospheric FX (mist, smoke, fading trails) and never apply semi-alpha to isolated `<= 4px` droplets or sparks.
- **Rim Outline Closing:** Any boundary pixel touching transparent background that is noticeably brighter than the dark outline leaks background bleed (paper halo). Quantize/lock rim pixels to the silhouette outline color.
- **Held-Prop Palette Locking:** Thin held props (blades, staves, handles) shift color across angles unless explicitly locked to a shared ramp (`<= 40` total colors: ~24 body, ~13 face, plus explicit prop ramp).
- **Interior vs. Exterior Background White:** Distinguish background flood-fill (connected to frame borders) from shut-in gaps (between legs or raised arms) so highlight sclera/shirt details are preserved while empty paper pockets are keyed cleanly.
