---
trigger: glob
globs: "**/*.gd, **/*.tscn, **/*.tres, **/*.cs, **/project.godot"
---

# Godot 4.x & Game Architecture Standards

## 1. Scene Decoupling ("Call Down, Signal Up")

- **Self-Contained Scenes**: Each `.tscn` scene must be runnable and testable in isolation without crashing when instantiated standalone.
- **Hierarchy Communication**: Parent nodes call methods on direct children ("call down"); child nodes emit typed `signal` events upward ("signal up") or communicate across distant systems via a dedicated Autoload event bus. Avoid brittle relative paths like `get_node("../../OtherNode")`.

## 2. Strict Static Typing (GDScript & C#)

- **GDScript**: Explicitly type all variables, arrays (`Array[Enemy]`), signals, and function signatures (`func calculate_damage(base: float, crit: bool) -> int:`). Enable strict typing warnings/errors in `project.godot`.
- **C#**: Enable `#nullable enable`, use typed `[Export]` and `[Signal]` attributes, and avoid reflection or unboxed `Variant` conversions on hot paths.

## 3. Frame Budget & Runtime Performance

- **Hot-Loop Discipline (`_process` / `_physics_process`)**: Never perform file I/O, node tree searches (`get_node`, `find_child`), string concatenation, or heavy allocations per frame. Cache node references once in `@onready` / `_ready()`.
- **Data-Driven Resources**: Store item stats, enemy definitions, and tuning parameters in custom `Resource` classes (`.tres`) decoupled from scene logic.
