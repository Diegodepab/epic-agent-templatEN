// Zero-dependency Godot 4 (.NET 8+) headless SceneTree test runner.
// Build first, then run:
//   dotnet build && godot --headless --path . --script res://tests/TestRunnerTemplate.cs
using Godot;
using System;
using System.Collections.Generic;

namespace Game.Tests;

public partial class TestRunnerTemplate : SceneTree
{
    private int _passed;
    private int _failed;

    public override void _Initialize()
    {
        var tests = new (string Name, Action Body)[]
        {
            ("SanityCheck", TestSanityCheck),
            // Register additional scene/integration tests here
        };

        foreach (var (name, body) in tests)
        {
            try
            {
                body();
                _passed++;
                GD.Print($"PASS: {name}");
            }
            catch (Exception ex)
            {
                _failed++;
                GD.PushError($"FAIL: {name} -> {ex.Message}");
            }
        }

        GD.Print($"Test summary: {_passed} passed, {_failed} failed.");
        Quit(_failed > 0 ? 1 : 0);
    }

    private static void AssertTrue(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private static void TestSanityCheck()
    {
        AssertTrue(2 + 2 == 4, "Arithmetic sanity check failed.");
    }
}
