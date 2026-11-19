# 2D `CanvasItem` Shaders, Dynamic Audio & Trauma Game Feel

## 1. Branchless 2D `CanvasItem` Shader Pattern (`.gdshader`)

Avoid dynamic `if/else` branching in `fragment()`. Use `step()`, `smoothstep()`, and `mix()` for GPU-friendly transitions (e.g., highlight/outline or hit-flash):

```glsl
shader_type canvas_item;

uniform vec4 flash_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float flash_amount : hint_range(0.0, 1.0) = 0.0;
uniform float vignette_strength : hint_range(0.0, 1.0) = 0.0;

void fragment() {
    vec4 tex = texture(TEXTURE, UV);
    vec3 flashed = mix(tex.rgb, flash_color.rgb, flash_amount);

    vec2 centered = UV - vec2(0.5);
    float dist = length(centered);
    float vig = smoothstep(0.35, 0.75, dist) * vignette_strength;

    COLOR = vec4(flashed * (1.0 - vig), tex.a);
}
```

Update from C# safely:
```csharp
if (Material is ShaderMaterial mat)
{
    mat.SetShaderParameter("flash_amount", 0.85f);
}
```

- For screen-wide post-processing (CRT, grain, color grading), place a full-rect `ColorRect` inside a dedicated `CanvasLayer` and sample `uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;`.

---

## 2. Dynamic Audio (`AudioServer` & State Crossfades)

```csharp
using Godot;

namespace Game.Audio;

public partial class AudioController : Node
{
    public void SetBusVolumeLinear(StringName busName, float linear01)
    {
        int idx = AudioServer.GetBusIndex(busName);
        if (idx == -1)
        {
            GD.PushError($"Audio bus '{busName}' does not exist in bus layout.");
            return;
        }
        bool mute = linear01 <= 0.0001f;
        AudioServer.SetBusMute(idx, mute);
        if (!mute)
        {
            AudioServer.SetBusVolumeDb(idx, Mathf.LinearToDb(linear01));
        }
    }
}
```

- **Adaptive Music**: For multi-layered or state-driven music (calm -> tension -> climax), use Godot 4.3+'s `AudioStreamInteractive` (clip transitions synced to beats/bars) or `AudioStreamSynchronized` (layered stems faded by bus/stream volume) instead of manual timer hacks.
- **SFX Variation**: Wrap repetitive footsteps/UI clicks in `AudioStreamRandomizer` (`RandomPitch = 1.08f`, `RandomVolumeOffsetDb = 1.5f`) and set `MaxPolyphony >= 4` on `AudioStreamPlayer`.

---

## 3. Real-Time Trauma Screen Shake (Survives Hit-Stop)

```csharp
using Godot;

namespace Game.Camera;

public partial class TraumaCamera2D : Camera2D
{
    [Export] public float DecayPerSecond { get; set; } = 1.4f;
    [Export] public Vector2 MaxOffset { get; set; } = new(12f, 8f);
    [Export] public float MaxRollRadians { get; set; } = 0.06f;
    [Export(PropertyHint.Range, "0,1,0.05")] public float AccessibilityStrength { get; set; } = 1.0f;

    private float _trauma;
    private float _elapsed;

    public override void _Ready() => IgnoreRotation = false;

    public void AddTrauma(float amount) => _trauma = Mathf.Clamp(_trauma + amount, 0f, 1f);

    public override void _Process(double delta)
    {
        if (_trauma <= 0f) return;

        float realDt = (float)delta / Mathf.Max((float)Engine.TimeScale, 0.0001f);
        _trauma = Mathf.Max(_trauma - DecayPerSecond * realDt, 0f);
        _elapsed += realDt * 30f;

        float shake = _trauma * _trauma * AccessibilityStrength;
        Offset = new Vector2(
            MaxOffset.X * shake * Mathf.Sin(_elapsed * 1.7f),
            MaxOffset.Y * shake * Mathf.Sin(_elapsed * 2.3f)
        );
        Rotation = MaxRollRadians * shake * Mathf.Sin(_elapsed * 1.1f);

        if (_trauma == 0f)
        {
            Offset = Vector2.Zero;
            Rotation = 0f;
        }
    }
}
```
