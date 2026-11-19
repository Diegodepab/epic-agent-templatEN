# Godot 4 C# Control UI, Menu Stack & Gamepad Focus

## 1. Safe-Area & Stack-Based Menu Manager

Model screens (Title, Gameplay HUD, Pause, Settings, Confirm Modal) as a stack so only the top screen handles input and previous focus is restored on pop:

```csharp
using Godot;
using System.Collections.Generic;

namespace Game.UI;

public partial class UiScreenStack : CanvasLayer
{
    private readonly Stack<(Control Screen, Control? ReturnFocus)> _stack = new();

    public void PushScreen(Control screen, Control initialFocus)
    {
        if (_stack.TryPeek(out var top))
        {
            top.Screen.ProcessMode = ProcessModeEnum.Disabled;
        }

        Control? prevFocus = GetViewport().GuiGetFocusOwner();
        screen.Visible = true;
        screen.ProcessMode = ProcessModeEnum.Inherit;
        _stack.Push((screen, prevFocus));

        initialFocus.GrabFocus();
    }

    public void PopScreen()
    {
        if (_stack.Count == 0) return;

        var (closing, returnFocus) = _stack.Pop();
        closing.Visible = false;
        closing.ProcessMode = ProcessModeEnum.Disabled;

        if (_stack.TryPeek(out var nextTop))
        {
            nextTop.Screen.ProcessMode = ProcessModeEnum.Inherit;
        }

        if (returnFocus is not null && IsInstanceValid(returnFocus) && returnFocus.IsVisibleInTree())
        {
            returnFocus.GrabFocus();
        }
    }
}
```

---

## 2. Container & Layout Checklist

- **Full-Rect Root Panel**: `AnchorsPreset = (int)LayoutPreset.FullRect` (`anchor_right = 1.0`, `anchor_bottom = 1.0`), with `MarginContainer` padding (`theme_override_constants/margin_*`) for safe-area insets.
- **No Hardcoded Pixel Coordinates**: Never position HUD elements with raw `(X, Y)` offsets; use `HBoxContainer` / `VBoxContainer` / `GridContainer` + `SizeFlagsHorizontal = SizeFlags.ExpandFill`.
- **Distinct Focus vs. Hover StyleBoxes**: Ensure `Theme` defines a visible `focus` `StyleBoxFlat` (e.g., high-contrast `2px` border) distinct from `hover` so controller/keyboard users always know which control is selected.
