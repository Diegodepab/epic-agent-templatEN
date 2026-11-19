"""End-to-end verification suite for epic-agent-templatEN & init_project.py v2."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


class TemplateInitEndToEndTests(unittest.TestCase):
    """Test initialization of all 6 stacks, 2D vs 3D separation, doc levels, and spec routing."""

    def _init_copy(self, tmp_dir: Path, stack: str | None, extra_args: list[str], folder_name: str | None = None) -> Path:
        dest = tmp_dir / (folder_name or f"proj_{stack or 'spec'}")
        shutil.copytree(
            TEMPLATE_ROOT,
            dest,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".venv"),
        )
        cmd = ["python3", "init_project.py", "--root", ".", "--name", "demo-app", "--yes", *extra_args]
        if stack:
            cmd.extend(["--stack", stack])
        proc = _run(cmd, dest)
        self.assertEqual(proc.returncode, 0, f"init_project failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertFalse((dest / "_catalog").exists(), "_catalog/ must be removed after init")
        self.assertFalse((dest / "evals").exists(), "evals/ must be removed after init")
        self.assertFalse((dest / "docs/assets/brand").exists(), "template brand assets must be removed after init")
        self.assertFalse((dest / "TEMPLATE_GUIDE.md").exists(), "TEMPLATE_GUIDE.md must be removed after init")
        self.assertFalse((dest / "init_project.py").exists(), "init_project.py must self-delete after init")
        self.assertFalse((dest / "tests/test_init_project.py").exists())
        self.assertFalse((dest / ".github/workflows/template-ci.yml").exists())

        skill_mds = list((dest / ".agents/skills").rglob("SKILL.md"))
        self.assertGreater(len(skill_mds), 0)
        for smd in skill_mds:
            self.assertEqual(len(smd.relative_to(dest / ".agents/skills").parts), 2, f"Not 1-level flat: {smd}")

        gi = (dest / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("\n_reference/\n", gi)
        self.assertNotIn("!_reference/SPEC.md", gi)

        readme = (dest / "README.md").read_text(encoding="utf-8")
        self.assertIn("# demo-app", readme)
        self.assertNotIn("TEMPLATE_GUIDE.md", readme)
        self.assertNotIn("{{", readme)
        return dest

    def test_list_catalog_and_dry_run(self) -> None:
        proc_cat = _run(["python3", "init_project.py", "--list-catalog"], TEMPLATE_ROOT)
        self.assertEqual(proc_cat.returncode, 0)
        catalog = json.loads(proc_cat.stdout)
        self.assertEqual(len(catalog["skills"]), 33)

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dry_copy"
            shutil.copytree(TEMPLATE_ROOT, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            proc = _run(["python3", "init_project.py", "--stack", "gamedev-godot", "--dim", "2d", "--dry-run"], dest)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["dimension"], "2d")
            self.assertNotIn("godot-3d-asset-and-rig-qa", payload["skills"])
            self.assertTrue((dest / "_catalog").is_dir())
            self.assertTrue((dest / "TEMPLATE_GUIDE.md").is_file())

    def test_web_frontend_profiles_and_optin_dataviz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            min_proj = self._init_copy(t, "web-frontend", ["--ui-profile", "minimalist", "--features", "dataviz,brand-logo"])
            self.assertIn("7-Rung", (min_proj / ".agents/rules/code-philosophy.md").read_text(encoding="utf-8"))
            min_skills = {p.name for p in (min_proj / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("frontend-quality-and-design-gate", min_skills)
            self.assertIn("ui-design-tokens-and-presets", min_skills)
            self.assertIn("frontend-dataviz-and-charts", min_skills)
            self.assertIn("brand-logo-and-svg-forge", min_skills)
            self.assertNotIn("ui-fluid-novel-system", min_skills)
            self.assertNotIn("godot-2d-pixel-art-forge", min_skills)

            fluid_proj = self._init_copy(t, "web-frontend", ["--ui-profile", "fluid"], "proj_web_fluid")
            fluid_skills = {p.name for p in (fluid_proj / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("ui-fluid-novel-system", fluid_skills)
            self.assertNotIn("ui-design-tokens-and-presets", fluid_skills)
            self.assertNotIn("frontend-dataviz-and-charts", fluid_skills)
            self.assertNotIn("brand-logo-and-svg-forge", fluid_skills)

    def test_python_cli_minimal_doc_level_and_arch_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            proj = self._init_copy(t, "python-cli", [])
            # python-cli defaults to doc-level minimal
            self.assertTrue((proj / "README.md").is_file())
            self.assertTrue((proj / "docs/ARCHITECTURE.md").is_file())
            self.assertFalse((proj / "docs/USER_GUIDE.md").exists())
            self.assertFalse((proj / "docs/adr").exists())
            self.assertFalse((proj / "docs/README.es.md").exists())

            sync_sc = ".agents/skills/architecture-knowledge-and-docs-sync/scripts/sync_arch_graph.py"
            self.assertEqual(_run(["python3", sync_sc, "--root", ".", "--write"], proj).returncode, 0)
            self.assertEqual(_run(["python3", sync_sc, "--root", ".", "--check-drift"], proj).returncode, 0)
            self.assertIn("src/demo_app", (proj / "docs/ARCHITECTURE.md").read_text(encoding="utf-8"))
            self.assertEqual(
                _run(["python3", ".agents/skills/architecture-knowledge-and-docs-sync/scripts/audit_docs_integrity.py", "--root", "."], proj).returncode,
                0,
            )

    def test_python_backend_full_gates_and_zero_game_ui_bloat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._init_copy(Path(tmp), "python-backend", ["--doc-level", "full", "--with-meta-skills"])
            skills = {p.name for p in (proj / ".agents/skills").iterdir() if p.is_dir()}
            self.assertNotIn("frontend-quality-and-design-gate", skills)
            self.assertNotIn("godot-architecture-and-static-audit", skills)
            self.assertTrue((proj / "src/AGENTS.md").is_file())
            self.assertTrue((proj / "docs/README.es.md").is_file())
            self.assertTrue((proj / "docs/BENCHMARKS.md").is_file())
            self.assertEqual(_run(["python3", ".agents/skills/backend-quality-and-contracts/scripts/quality_and_contracts.py", "--target", "src", "--no-wrappers"], proj).returncode, 0)
            self.assertEqual(_run(["python3", ".agents/skills/backend-security-and-owasp-gate/scripts/security_gate.py", "--target", "src", "--no-wrappers"], proj).returncode, 0)
            self.assertEqual(_run(["python3", ".agents/skills/docker-and-env-auditor/scripts/docker_env_linter.py", "--root", "."], proj).returncode, 0)
            self.assertEqual(_run(["python3", ".agents/skills/architecture-knowledge-and-docs-sync/scripts/audit_docs_integrity.py", "--root", "."], proj).returncode, 0)

    def test_multi_module_and_ml_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            mm = self._init_copy(t, "multi-module", ["--ui-profile", "minimalist"])
            self.assertTrue((mm / "backend/AGENTS.md").is_file())
            self.assertFalse((mm / "frontend/AGENTS.md").exists())
            ml = self._init_copy(t, "ml-gpu", [])
            self.assertTrue((ml / "docs/BENCHMARKS.md").is_file())
            self.assertIn("ml-gpu-workload-harness", {p.name for p in (ml / ".agents/skills").iterdir()})

    def test_gamedev_2d_vs_3d_strict_isolation_and_spec_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # 1. Default 2D gets all 2D art/pixel/fx/autotile/audio skills and ZERO 3D skills
            g2d = self._init_copy(t, "gamedev-godot", ["--dim", "2d"], "proj_godot_2d")
            s2d = {p.name for p in (g2d / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("godot-2d-pixel-art-forge", s2d)
            self.assertIn("godot-2d-rig-and-fx-animator", s2d)
            self.assertIn("godot-2d-autotile-and-parallax", s2d)
            self.assertIn("godot-procedural-audio-and-sfx", s2d)
            self.assertNotIn("godot-3d-asset-and-rig-qa", s2d)
            self.assertNotIn("test-and-mutation-gate", s2d)

            # 2. 3D gets godot-3d-asset-and-rig-qa and excludes 2D-only art skills
            g3d = self._init_copy(t, "gamedev-godot", ["--dim", "3d"], "proj_godot_3d")
            s3d = {p.name for p in (g3d / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("godot-3d-asset-and-rig-qa", s3d)
            self.assertIn("godot-procedural-audio-and-sfx", s3d)
            self.assertNotIn("godot-2d-pixel-art-forge", s3d)
            self.assertNotIn("godot-2d-autotile-and-parallax", s3d)

            # 3. Granular --features selection in 2D
            gfeat = self._init_copy(t, "gamedev-godot", ["--dim", "2d", "--features", "pixel-art,sfx"], "proj_godot_feat")
            sfeat = {p.name for p in (gfeat / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("godot-2d-pixel-art-forge", sfeat)
            self.assertIn("godot-procedural-audio-and-sfx", sfeat)
            self.assertNotIn("godot-2d-autotile-and-parallax", sfeat)
            self.assertNotIn("godot-3d-asset-and-rig-qa", sfeat)

            # 4. --from-spec routing directly from checked _reference/SPEC.md
            spec_dest = t / "proj_from_spec"
            shutil.copytree(TEMPLATE_ROOT, spec_dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            spec_f = spec_dest / "_reference/SPEC.md"
            spec_txt = spec_f.read_text(encoding="utf-8").replace("- [ ] `gamedev-godot`", "- [x] `gamedev-godot`")
            spec_f.write_text(spec_txt, encoding="utf-8")
            proc = _run(["python3", "init_project.py", "--from-spec", "_reference/SPEC.md", "--name", "spec-game", "--yes"], spec_dest)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((spec_dest / ".agents/skills/godot-2d-pixel-art-forge").is_dir())

    def test_four_axes_rules_spec_and_multiagent_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # 1. CLI 5-step flags: clean-ddd + web-frontend + neobrutalist + full + multi-agent projection
            proj = self._init_copy(
                t,
                "web-frontend",
                ["--code-style", "clean-ddd", "--ui-style", "neobrutalist", "--doc-level", "full", "--agents", "all"],
                "proj_axes_cli",
            )
            self.assertIn("Clean Architecture", (proj / ".agents/rules/code-philosophy.md").read_text(encoding="utf-8"))
            self.assertIn("clean-code-and-architecture-gate", {p.name for p in (proj / ".agents/skills").iterdir()})
            self.assertIn("`neobrutalist`", (proj / ".agents/rules/ui-aesthetic.md").read_text(encoding="utf-8"))
            self.assertIn("Docs Exhaustive", (proj / ".agents/rules/docs-discipline.md").read_text(encoding="utf-8"))
            contract = json.loads((proj / ".agents/ui-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["visual_style"], "neobrutalist")
            self.assertTrue((proj / ".gemini/settings.json").is_file())
            self.assertTrue((proj / ".claude/settings.json").is_file())
            self.assertTrue((proj / "GEMINI.md").is_file())
            self.assertTrue((proj / "CLAUDE.md").is_file())
            self.assertTrue((proj / ".gemini/skills/frontend-quality-and-design-gate/SKILL.md").is_file())
            self.assertTrue((proj / ".claude/skills/frontend-quality-and-design-gate/SKILL.md").is_file())

            # 2. --from-spec parsing across all 4 axes
            spec_dest = t / "proj_axes_spec"
            shutil.copytree(TEMPLATE_ROOT, spec_dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            spec_f = spec_dest / "_reference/SPEC.md"
            spec_txt = spec_f.read_text(encoding="utf-8")
            for old, new in (
                ("- [ ] `functional-dod`", "- [x] `functional-dod`"),
                ("- [ ] `web-frontend`", "- [x] `web-frontend`"),
                ("- [ ] `terminal`", "- [x] `terminal`"),
                ("- [ ] `minimal`", "- [x] `minimal`"),
            ):
                self.assertIn(old, spec_txt)
                spec_txt = spec_txt.replace(old, new, 1)
            spec_f.write_text(spec_txt, encoding="utf-8")
            proc = _run(["python3", "-B", "init_project.py", "--from-spec", "_reference/SPEC.md", "--name", "spec-web", "--yes"], spec_dest)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Functional", (spec_dest / ".agents/rules/code-philosophy.md").read_text(encoding="utf-8"))
            self.assertIn("`terminal`", (spec_dest / ".agents/rules/ui-aesthetic.md").read_text(encoding="utf-8"))
            self.assertIn("Docs Basic", (spec_dest / ".agents/rules/docs-discipline.md").read_text(encoding="utf-8"))
            spec_contract = json.loads((spec_dest / ".agents/ui-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(spec_contract["visual_style"], "terminal")

            # 3. Universal pre_tool_guard.py across Antigravity, Gemini CLI, and Claude Code payloads
            guard = proj / ".agents/hooks/pre_tool_guard.py"
            cases = [
                (["--dialect", "auto"], {"toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /"}}}, "antigravity", "deny"),
                (["--dialect", "gemini"], {"tool_name": "run_shell_command", "tool_input": {"command": "rm -rf /"}}, "gemini", "deny"),
                (["--dialect", "claude"], {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, "claude", "deny"),
                (["--dialect", "gemini"], {"tool_name": "run_shell_command", "tool_input": {"command": "ls -la"}}, "gemini", "allow"),
            ]
            for flags, payload, kind, expected_dec in cases:
                res = subprocess.run(
                    ["python3", "-B", str(guard), *flags],
                    cwd=proj,
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(res.returncode, 0, res.stderr)
                out = json.loads(res.stdout)
                if kind == "claude":
                    self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
                    self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], expected_dec)
                else:
                    self.assertEqual(out["decision"], expected_dec)

    def test_modular_scope_infra_split_and_doc_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # 1. --scope api ONLY: gets api-openapi-contract-gate, excludes db-migration-and-schema-gate and frontend
            api_only = self._init_copy(t, None, ["--scope", "api", "--docs", "minimal"], "proj_scope_api")
            api_skills = {p.name for p in (api_only / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("api-openapi-contract-gate", api_skills)
            self.assertNotIn("db-migration-and-schema-gate", api_skills)
            self.assertNotIn("frontend-quality-and-design-gate", api_skills)
            self.assertNotIn("TEMPLATE_BOOTSTRAP_INTERVIEW", (api_only / "AGENTS.md").read_text(encoding="utf-8"))

            # 2. --nature app-system --scope api,db,ml-gpu --infra split-cpu-gpu --docs user-guide,agent-guide
            dist = self._init_copy(
                t,
                None,
                ["--nature", "app-system", "--scope", "api,db,ml-gpu", "--infra", "split-cpu-gpu", "--docs", "user-guide,agent-guide"],
                "proj_scope_split",
            )
            dist_skills = {p.name for p in (dist / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("api-openapi-contract-gate", dist_skills)
            self.assertIn("db-migration-and-schema-gate", dist_skills)
            self.assertIn("ml-gpu-workload-harness", dist_skills)
            self.assertIn("runtime-profiling-and-observability", dist_skills)
            self.assertIn("docker-and-env-auditor", dist_skills)
            self.assertTrue((dist / "src/demo_app/device.py").is_file())
            self.assertTrue((dist / ".agents/rules/infra-topology.md").is_file())
            compose_txt = (dist / "compose.yaml").read_text(encoding="utf-8")
            self.assertIn("app-cpu", compose_txt)
            self.assertIn("gpu-worker", compose_txt)
            env_txt = (dist / ".env.example").read_text(encoding="utf-8")
            self.assertIn("REMOTE_WORKER_URL", env_txt)
            self.assertIn("DB_NODE_HOST", env_txt)
            self.assertIn("DATABASE_URL=", env_txt)
            self.assertNotIn("{{PROJECT_SLUG}}", env_txt)
            self.assertNotIn("postgres:postgres", env_txt)
            self.assertNotIn("REDIS_URL", env_txt)
            self.assertNotIn("http://localhost:", env_txt)
            self.assertTrue((dist / "docs/USER_GUIDE.md").is_file())
            self.assertNotIn("{{PROJECT_SLUG}}", (dist / "docs/USER_GUIDE.md").read_text(encoding="utf-8"))
            self.assertTrue((dist / "docs/AGENT_GUIDE.md").is_file())
            self.assertFalse((dist / "docs/adr").exists())
            self.assertEqual(
                _run(["python3", ".agents/skills/architecture-knowledge-and-docs-sync/scripts/audit_docs_integrity.py", "--root", "."], dist).returncode,
                0,
            )

            # 3. --scope frontend --ui-style minimalist --ui-tone dark --with-dataviz --with-brand-logo
            fe_dark = self._init_copy(
                t,
                None,
                ["--scope", "frontend", "--ui-style", "minimalist", "--ui-tone", "dark", "--with-dataviz", "--with-brand-logo"],
                "proj_scope_fe_dark",
            )
            fe_skills = {p.name for p in (fe_dark / ".agents/skills").iterdir() if p.is_dir()}
            self.assertIn("ui-design-tokens-and-presets", fe_skills)
            self.assertIn("frontend-dataviz-and-charts", fe_skills)
            self.assertIn("brand-logo-and-svg-forge", fe_skills)
            self.assertNotIn("db-migration-and-schema-gate", fe_skills)
            self.assertTrue((fe_dark / "assets/tokens/minimalist.tokens.json").is_file())
            self.assertIn("#141517", (fe_dark / "assets/tokens/design-tokens.css").read_text(encoding="utf-8"))

    def test_gamedev_shared_core_parity(self) -> None:
        gamedev_root = TEMPLATE_ROOT / "_catalog/skills/gamedev"
        for shared_name in ("codeart_core.py", "forge_core.py"):
            copies = sorted(gamedev_root.rglob(shared_name))
            self.assertGreaterEqual(len(copies), 2, f"Expected >=2 copies of {shared_name}")
            digests = {p.read_bytes() for p in copies}
            self.assertEqual(len(digests), 1, f"Shared module drift detected across: {[str(p) for p in copies]}")

    def test_template_workflows_pin_actions(self) -> None:
        pin_script = TEMPLATE_ROOT / "_catalog/skills/github/git-commit-and-pr-gate/scripts/verify-action-pins.sh"
        res = _run(["bash", str(pin_script), str(TEMPLATE_ROOT)], TEMPLATE_ROOT)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
