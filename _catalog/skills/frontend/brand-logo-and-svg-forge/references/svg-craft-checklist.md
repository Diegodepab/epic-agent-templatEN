# Vector Logo & SVG Craft Checklist

1. **Grid & ViewBox:** Author symbols on `viewBox="0 0 256 256"` (lockups keep height `256`). Round path coordinates to `0-2` decimals.
2. **No Blind Coding:** Always rasterize drafts via `render_png.py` (`--size 512`) and open the PNGs to inspect silhouettes visually before delivering.
3. **Production Geometry Rules:**
   - Zero live `<text>` nodes in final logos (outline letterforms into `<path>` primitives).
   - Zero embedded `<image>` bitmaps, `<filter>` blurs/glows, or `<foreignObject>` tags in master marks.
   - Use real negative-space holes (`fill-rule="evenodd"` or boolean path subtraction), never white shapes painted atop colored fills.
   - Snap near-miss straight angles (`0.3-3 deg` off `0/15/30/45/60/75/90 deg`).
4. **Discipline & Optical Corrections:**
   - Keep palette flat (`<= 3` colors; provide `-black`, `-white`, and `-mono` variants).
   - Apply `1-3%` overshoot on curved/pointed vertices past flat baselines; optically nudge circles/arrows upward by `~2%`.
   - Test readability at `16 px` and `32 px` (`preview_sheet.py` / `concept_sheet.py`), and supply a simplified `--favicon-source` if hairlines collapse.
