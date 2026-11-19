# Finite State Machines (FSM), Data-Driven Resources & 2D Systems

## 1. Clean C# Finite State Machine (FSM)

Works identically for gameplay loops (Inspecting -> Deciding -> Resolving), AI behaviors, or minigames:

```csharp
using Godot;
using System.Collections.Generic;

namespace Game.Core.State;

public abstract partial class GameState : Node
{
    public virtual void Enter() { }
    public virtual void Exit() { }
    public virtual void Update(double delta) { }
    public virtual void PhysicsUpdate(double delta) { }
}

public partial class StateMachine : Node
{
    [Export] public NodePath? InitialStatePath { get; set; }

    private readonly Dictionary<string, GameState> _states = new();
    private GameState? _currentState;

    public override void _Ready()
    {
        foreach (Node child in GetChildren())
        {
            if (child is GameState state)
            {
                _states[state.Name] = state;
            }
        }

        if (InitialStatePath is not null && !InitialStatePath.IsEmpty)
        {
            TransitionTo(GetNode<GameState>(InitialStatePath).Name);
        }
    }

    public override void _Process(double delta) => _currentState?.Update(delta);
    public override void _PhysicsProcess(double delta) => _currentState?.PhysicsUpdate(delta);

    public void TransitionTo(string stateName)
    {
        if (!_states.TryGetValue(stateName, out GameState? nextState) || nextState == _currentState)
        {
            return;
        }
        _currentState?.Exit();
        _currentState = nextState;
        _currentState.Enter();
    }
}
```

---

## 2. Modular Paper-Doll 2D Sprite Synchronization

When assembling characters or inspectable objects from swappable layers (base body, outfit, expression, held prop):

```csharp
using Godot;

namespace Game.Visuals;

public partial class ModularSpriteRig : Node2D
{
    [Export] public Sprite2D? BaseLayer { get; set; }
    [Export] public Sprite2D? OutfitLayer { get; set; }
    [Export] public Sprite2D? ExpressionLayer { get; set; }

    public void ApplyAppearance(Texture2D? outfit, Texture2D? expression, bool flipH)
    {
        if (BaseLayer is not null) BaseLayer.FlipH = flipH;
        if (OutfitLayer is not null)
        {
            OutfitLayer.Texture = outfit;
            OutfitLayer.FlipH = flipH;
        }
        if (ExpressionLayer is not null)
        {
            ExpressionLayer.Texture = expression;
            ExpressionLayer.FlipH = flipH;
        }
    }
}
```

---

## 3. `CharacterBody2D` & `TileMapLayer` Essentials (C#)

- **`CharacterBody2D`**: Read `Velocity` into a local `Vector2`, modify it, assign `Velocity = v;`, and call `MoveAndSlide()` once per `_PhysicsProcess`. Read `IsOnFloor()`, `IsOnWall()`, and `GetSlideCollision(i)` *after* `MoveAndSlide()`.
- **`TileMapLayer`**: Use separate `TileMapLayer` nodes per depth layer (`Ground`, `Walls`, `Foreground`) sharing a single `.tres` `TileSet`. Convert world positions with `LocalToMap(ToLocal(worldPos))` and edit cells via `SetCell(coords, sourceId, atlasCoords)`.
- **`InputMap` Actions**: Never poll raw keys (`Input.IsKeyPressed`). Always bind named actions (`interact`, `inspect`, `jump`) in `project.godot` and read via `Input.IsActionJustPressed(...)` or `Input.GetVector(...)` (which applies a radial deadzone automatically).
