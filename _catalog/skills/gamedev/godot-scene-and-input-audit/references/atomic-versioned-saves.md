# Crash-Safe Atomic Versioned Save System (C#)

## 1. Plain Save DTO (Zero Node References)

```csharp
using System.Collections.Generic;

namespace Game.Persistence;

public sealed class SaveGameDto
{
    public int Version { get; set; } = 1;
    public int Day { get; set; } = 1;
    public ulong RngSeed { get; set; }
    public float[] PlayerPos { get; set; } = [0f, 0f];
    public Dictionary<string, int> Inventory { get; set; } = new();
    public HashSet<string> Flags { get; set; } = new();
}
```

---

## 2. Atomic Write (`.tmp` -> `.bak` -> Rename) & Defensive Load

```csharp
using Godot;
using System;
using System.Text.Json;

namespace Game.Persistence;

public static class SaveStorage
{
    public const int CurrentVersion = 1;
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public static bool WriteAtomic(string userRelativePath, SaveGameDto dto)
    {
        string absDir = ProjectSettings.GlobalizePath("user://saves");
        DirAccess.MakeDirRecursiveAbsolute(absDir);

        string absTarget = ProjectSettings.GlobalizePath(userRelativePath);
        string absTmp = absTarget + ".tmp";
        string absBak = absTarget + ".bak";

        try
        {
            string json = JsonSerializer.Serialize(dto, JsonOptions);
            using (var file = FileAccess.Open(absTmp, FileAccess.ModeFlags.Write))
            {
                if (file is null) return false;
                file.StoreString(json);
                file.Flush();
            }

            if (FileAccess.FileExists(absTarget))
            {
                if (FileAccess.FileExists(absBak))
                {
                    DirAccess.RemoveAbsolute(absBak);
                }
                DirAccess.RenameAbsolute(absTarget, absBak);
            }

            return DirAccess.RenameAbsolute(absTmp, absTarget) == Error.Ok;
        }
        catch (Exception ex)
        {
            GD.PushError($"Atomic save failed for '{userRelativePath}': {ex.Message}");
            return false;
        }
    }

    public static SaveGameDto? LoadWithFallback(string userRelativePath)
    {
        return TryParseAndMigrate(userRelativePath) ?? TryParseAndMigrate(userRelativePath + ".bak");
    }

    private static SaveGameDto? TryParseAndMigrate(string path)
    {
        if (!FileAccess.FileExists(path)) return null;

        try
        {
            using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
            if (file is null) return null;

            var dto = JsonSerializer.Deserialize<SaveGameDto>(file.GetAsText());
            if (dto is null || dto.Version > CurrentVersion) return null;

            // Apply sequential migrations here if dto.Version < CurrentVersion
            dto.Version = CurrentVersion;
            return dto;
        }
        catch (Exception ex)
        {
            GD.PushWarning($"Failed to load save '{path}': {ex.Message}");
            return null;
        }
    }
}
```
