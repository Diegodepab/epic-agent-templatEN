# Godot 4 C# Domain Separation, Signals & Resource Patterns

## 1. Pure C# Domain Class vs. Thin `Node` Adapter

Keep game rules independent of the Godot SceneTree so they can be unit-tested with `dotnet test` in milliseconds:

```csharp
// Domain/Economy/InventoryLedger.cs (Pure C# — zero Godot.Node dependency)
namespace Game.Domain.Economy;

public sealed class InventoryLedger
{
    public const int MaxStack = 99;
    private readonly Dictionary<string, int> _counts = new();

    public int AddItem(string itemId, int amount)
    {
        if (amount <= 0) return 0;
        int current = _counts.GetValueOrDefault(itemId, 0);
        int added = Math.Min(amount, MaxStack - current);
        if (added <= 0) return 0;

        _counts[itemId] = current + added;
        return added;
    }

    public int GetCount(string itemId) => _counts.GetValueOrDefault(itemId, 0);
}
```

---

## 2. Typed `[Signal]`, `[Export]`, and `_ExitTree()` Cleanup

Every Godot node script **must** be `public partial class`. Always pair every `+=` subscription with `-=` in `_ExitTree()`:

```csharp
using Godot;

namespace Game.Actors;

public partial class HealthComponent : Node
{
    [Signal]
    public delegate void HealthChangedEventHandler(int current, int maximum);

    [Signal]
    public delegate void DiedEventHandler();

    [Export]
    public int MaxHealth { get; set; } = 100;

    public int CurrentHealth { get; private set; }

    public override void _Ready()
    {
        CurrentHealth = MaxHealth;
    }

    public void ApplyDamage(int amount)
    {
        if (amount <= 0 || CurrentHealth <= 0) return;

        CurrentHealth = Mathf.Max(0, CurrentHealth - amount);
        EmitSignal(SignalName.HealthChanged, CurrentHealth, MaxHealth);

        if (CurrentHealth == 0)
        {
            EmitSignal(SignalName.Died);
        }
    }
}
```

```csharp
// Consumer node subscribing safely with _ExitTree cleanup
public partial class PlayerHudBridge : Node
{
    private HealthComponent _health = null!;

    public override void _Ready()
    {
        _health = GetNode<HealthComponent>("%HealthComponent");
        _health.HealthChanged += OnHealthChanged;
    }

    public override void _ExitTree()
    {
        if (IsInstanceValid(_health))
        {
            _health.HealthChanged -= OnHealthChanged;
        }
    }

    private void OnHealthChanged(int current, int maximum)
    {
        // Forward to UI
    }
}
```

---

## 3. Custom Data-Driven `[GlobalClass]` Resources

Use `[GlobalClass]` on `Resource` subclasses so designers and `.tres` files can configure entities cleanly in the Inspector without hardcoding constants:

```csharp
using Godot;

namespace Game.Data;

[GlobalClass]
public partial class CharacterProfileResource : Resource
{
    [Export] public string CharacterId { get; set; } = string.Empty;
    [Export] public string DisplayName { get; set; } = string.Empty;
    [Export(PropertyHint.Range, "0,100,1")] public int BaseMood { get; set; } = 50;
    [Export] public Texture2D? Portrait { get; set; }
}
```
