.PHONY: dev lint format test

dev: ## Launch Godot editor (requires godot binary on PATH)
	godot --editor --path .

lint: ## Run Godot static audits (res://, uid://, C# architecture, scene/input)
	python3 .agents/skills/godot-architecture-and-static-audit/scripts/check_godot_project.py . --strict
	python3 .agents/skills/godot-architecture-and-static-audit/scripts/check_csharp_godot_architecture.py --root .
	python3 .agents/skills/godot-scene-and-input-audit/scripts/audit_scene_and_input.py --root .

format: ## Format C# source files using dotnet format
	@if command -v dotnet >/dev/null 2>&1; then dotnet format; else echo "dotnet CLI not installed"; fi

test: ## Run pure C# Domain tests + headless Godot verification
	python3 .agents/skills/godot-headless-testing/scripts/run_godot_tests.py --root .
