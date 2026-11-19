#!/usr/bin/env python3
"""Exports spritesheet strips into Godot 4 SpriteFrames (.tres), Scene (.tscn), and C# Controller (.cs)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:
    print(f"Missing imaging dependency (pillow): {exc}", file=sys.stderr)
    raise SystemExit(2)


def generate_ellipse_shadow_strip(sheet_path: Path, fw: int, fh: int, out_path: Path) -> None:
    """Create a matching soft contact-shadow strip proportional to each frame's opaque footprint."""
    im = Image.open(sheet_path).convert("RGBA")
    cols = max(1, im.width // fw)
    rows = max(1, im.height // fh)
    sh_h = max(8, fh // 5)
    strip = Image.new("RGBA", (cols * rows * fw, sh_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)

    idx = 0
    for r in range(rows):
        for c in range(cols):
            cell = im.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
            bbox = cell.getchannel("A").getbbox()
            if bbox:
                span_w = max(8, int((bbox[2] - bbox[0]) * 0.7))
                cx = idx * fw + (bbox[0] + bbox[2]) // 2
                cy = sh_h // 2
                rx = span_w // 2
                ry = max(3, sh_h // 3)
                draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(0, 0, 0, 120))
            idx += 1
    strip.save(out_path)


def build_spriteframes_tres(anims: list[dict[str, object]], is_shadow: bool = False) -> str:
    ext_lines: list[str] = []
    sub_lines: list[str] = []
    anim_entries: list[str] = []
    sub_idx = 1

    for i, a in enumerate(anims, start=1):
        tex_file = str(a["shadow_png"] if is_shadow else a["png"])
        ext_id = f"tex_{i}"
        ext_lines.append(f'[ext_resource type="Texture2D" path="{tex_file}" id="{ext_id}"]')

        fw, fh = int(a["fw"]), int(a["sh_h"] if is_shadow else a["fh"])  # type: ignore[arg-type]
        cols, rows = int(a["cols"]), int(a["rows"])  # type: ignore[arg-type]
        total = int(a["total"]) if not is_shadow else cols * rows  # type: ignore[arg-type]

        frame_refs: list[str] = []
        for idx in range(total):
            c = idx if is_shadow else idx % cols
            r = 0 if is_shadow else idx // cols
            sub_id = f"AtlasTexture_{sub_idx}"
            sub_idx += 1
            sub_lines.append(
                f'[sub_resource type="AtlasTexture" id="{sub_id}"]\n'
                f'atlas = ExtResource("{ext_id}")\n'
                f"region = Rect2({c * fw}, {r * fh}, {fw}, {fh})\n"
            )
            frame_refs.append(f'{{\n"duration": 1.0,\n"texture": SubResource("{sub_id}")\n}}')

        loop_str = "true" if a["loop"] else "false"
        anim_entries.append(
            f'{{\n"frames": [{", ".join(frame_refs)}],\n'
            f'"loop": {loop_str},\n"name": &"{a["name"]}",\n"speed": {float(a["fps"]):.1f}\n}}'
        )

    load_steps = len(ext_lines) + len(sub_lines) + 1
    parts = [f'[gd_resource type="SpriteFrames" load_steps={load_steps} format=3]', ""]
    parts.extend(ext_lines)
    parts.append("")
    parts.extend(sub_lines)
    parts.append("[resource]")
    parts.append(f"animations = [{', '.join(anim_entries)}]")
    return "\n".join(parts) + "\n"


def parse_sheet_spec(raw: str) -> tuple[str, Path, float, bool]:
    parts = raw.split(":")
    if len(parts) < 2:
        raise ValueError(f"Expected `action:path.png[:fps[:loop|once]]`, got `{raw}`")
    action = parts[0].strip()
    path = Path(parts[1].strip())
    fps = float(parts[2]) if len(parts) >= 3 and parts[2] else 10.0
    loop = (parts[3].strip().lower() != "once") if len(parts) >= 4 else True
    return action, path, fps, loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Export 2D spritesheets to Godot 4 SpriteFrames (.tres), Scene (.tscn), and C# Controller.")
    parser.add_argument("--name", required=True, help="Entity PascalCase name, e.g. PlayerSprite")
    parser.add_argument("--sheet", action="append", required=True, help="Spec `action:path.png[:fps[:loop|once]]`")
    parser.add_argument("--frame-w", type=int, required=True, help="Frame width in pixels")
    parser.add_argument("--frame-h", type=int, required=True, help="Frame height in pixels")
    parser.add_argument("--out", required=True, help="Output folder inside Godot project")
    parser.add_argument("--with-shadow", action="store_true", help="Generate synchronized ground shadow strip and Shadow node")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    anims: list[dict[str, object]] = []

    for raw_spec in args.sheet:
        action, src_path, fps, loop = parse_sheet_spec(raw_spec)
        if not src_path.is_file():
            print(f"Sheet not found: {src_path}", file=sys.stderr)
            return 1
        im = Image.open(src_path)
        cols = max(1, im.width // args.frame_w)
        rows = max(1, im.height // args.frame_h)
        total = cols * rows
        dest_png = f"{args.name}_{action}.png"
        shutil.copy2(src_path, out_dir / dest_png)

        shadow_png = f"{args.name}_{action}_shadow.png"
        sh_h = max(8, args.frame_h // 5)
        if args.with_shadow:
            generate_ellipse_shadow_strip(src_path, args.frame_w, args.frame_h, out_dir / shadow_png)

        anims.append(
            {
                "name": action,
                "png": dest_png,
                "shadow_png": shadow_png,
                "fw": args.frame_w,
                "fh": args.frame_h,
                "sh_h": sh_h,
                "cols": cols,
                "rows": rows,
                "total": total,
                "fps": fps,
                "loop": loop,
            }
        )

    (out_dir / f"{args.name}.tres").write_text(build_spriteframes_tres(anims, is_shadow=False), encoding="utf-8")
    if args.with_shadow:
        (out_dir / f"{args.name}_shadow.tres").write_text(build_spriteframes_tres(anims, is_shadow=True), encoding="utf-8")

    default_anim = anims[0]["name"]
    cs_code = f"""using Godot;

public partial class {args.name} : Node2D
{{
    private AnimatedSprite2D _body = null!;
    private AnimatedSprite2D? _shadow;

    public override void _Ready()
    {{
        _body = GetNode<AnimatedSprite2D>("Body");
        _shadow = GetNodeOrNull<AnimatedSprite2D>("Shadow");
        _body.FrameChanged += SyncShadowFrame;
        Play("{default_anim}");
    }}

    public override void _ExitTree()
    {{
        if (_body != null)
            _body.FrameChanged -= SyncShadowFrame;
    }}

    public void Play(StringName animationName)
    {{
        if (_body.Animation == animationName && _body.IsPlaying())
            return;
        _body.Play(animationName);
        if (_shadow != null && _shadow.SpriteFrames != null && _shadow.SpriteFrames.HasAnimation(animationName))
            _shadow.Play(animationName);
    }}

    private void SyncShadowFrame()
    {{
        if (_shadow != null)
            _shadow.Frame = _body.Frame;
    }}
}}
"""
    (out_dir / f"{args.name}.cs").write_text(cs_code, encoding="utf-8")

    if args.with_shadow:
        tscn = f"""[gd_scene load_steps=4 format=3]

[ext_resource type="SpriteFrames" path="{args.name}_shadow.tres" id="1_shadow"]
[ext_resource type="SpriteFrames" path="{args.name}.tres" id="2_body"]
[ext_resource type="Script" path="{args.name}.cs" id="3_script"]

[node name="{args.name}" type="Node2D"]
script = ExtResource("3_script")

[node name="Shadow" type="AnimatedSprite2D" parent="."]
modulate = Color(1, 1, 1, 0.3)
position = Vector2(0, {int(args.frame_h * 0.42)})
sprite_frames = ExtResource("1_shadow")
animation = &"{default_anim}"

[node name="Body" type="AnimatedSprite2D" parent="."]
sprite_frames = ExtResource("2_body")
animation = &"{default_anim}"
"""
    else:
        tscn = f"""[gd_scene load_steps=3 format=3]

[ext_resource type="SpriteFrames" path="{args.name}.tres" id="1_body"]
[ext_resource type="Script" path="{args.name}.cs" id="2_script"]

[node name="{args.name}" type="Node2D"]
script = ExtResource("2_script")

[node name="Body" type="AnimatedSprite2D" parent="."]
sprite_frames = ExtResource("1_body")
animation = &"{default_anim}"
"""
    (out_dir / f"{args.name}.tscn").write_text(tscn, encoding="utf-8")
    print(f"[godot-export] Exported {args.name} ({len(anims)} anims) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
