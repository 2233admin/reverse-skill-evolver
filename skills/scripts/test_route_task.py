"""Unit tests for the deterministic route planner."""

import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from route_task import (
    FALLBACK_CAPABILITIES,
    build_tool_plan,
    capability_status,
    condition_matches,
    dynamic_requirements,
    infer_target_kind,
    is_security_task,
    is_authorized,
    parse_sentrux_observation,
    resolve_sentrux_scope,
    score_route,
    build_parser,
    build_plan,
    collect_project_intelligence,
    parse_task,
)


class RouteTaskTests(unittest.TestCase):
    def test_project_routing_fails_closed_without_aigx_genome(self):
        with tempfile.TemporaryDirectory() as directory:
            intelligence = collect_project_intelligence(directory)
            plan = build_plan(
                {
                    "task": "Rust protocol source cargo test",
                    "target_kind": "source_tree",
                    "project_path": directory,
                }
            )
        self.assertEqual(intelligence["aigx"]["reason"], "aigx_genome_missing")
        self.assertEqual(intelligence["code_intel"]["status"], "not_run")
        self.assertEqual(intelligence["sentrux"]["status"], "not_run")
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("aigx_genome_missing", plan["block_reasons"])
        self.assertFalse(plan["preflight"]["aigx"]["ready"])

    def test_parser_accepts_repeatable_aigx_edit_targets(self):
        task = parse_task(
            build_parser().parse_args(
                [
                    "--task",
                    "route source edit",
                    "--project-path",
                    r"C:\repo",
                    "--aigx-target",
                    "src/a.rs",
                    "--aigx-target",
                    "src/b.rs",
                ]
            )
        )
        self.assertEqual(task["aigx_targets"], ["src/a.rs", "src/b.rs"])

    def test_infers_artifact_types(self):
        self.assertEqual(infer_target_kind({"input_path": r"C:\tmp\sample.apk"}), "apk-android")
        self.assertEqual(infer_target_kind({"input_path": r"C:\tmp\capture.pcapng"}), "protocol-pcap")
        self.assertEqual(infer_target_kind({"target_kind": "安卓"}), "apk-android")
        self.assertEqual(infer_target_kind({"target_kind": "pe"}), "native-binary")
        self.assertEqual(infer_target_kind({"task": "configure IDA Teams git-ida collaboration"}), "native-binary")
        self.assertEqual(
            infer_target_kind({"target_kind": "source_tree", "task": "run a Sentrux architecture check"}),
            "architecture-governance",
        )
        self.assertEqual(infer_target_kind({"task": "use xcmd for workspace search"}), "workspace-search")

    def test_native_binary_route_blocks_when_dispatch_requires_input_path(self):
        plan = build_plan(
            {
                "task": "use IDA for static analysis",
                "target_kind": "pe",
                "authorization_scope": {"kind": "own_asset"},
            }
        )

        self.assertEqual(plan["route"]["base_id"], "native-binary")
        self.assertEqual(plan["dispatch"]["requires"], ["input_path"])
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["preflight"]["status"], "blocked")
        self.assertEqual(plan["preflight"]["input"]["status"], "required")
        self.assertFalse(plan["preflight"]["input"]["ready"])
        self.assertEqual(plan["preflight"]["input"]["reason"], "input_path_required")
        self.assertIn("input_path_required", plan["block_reasons"])

    def test_native_fallback_cannot_bypass_the_input_or_ghidra_gates(self):
        capabilities = {
            "idapro": {"kind": "capability", "service_online": False, "api_ready": False},
            "rabin2": {"kind": "tool", "available": False},
            "analyzeHeadless": {"kind": "tool", "available": False},
            "python": {"kind": "tool", "available": True},
        }
        with patch("route_task.load_capabilities", return_value=capabilities):
            plan = build_plan(
                {
                    "task": "analyze this native PE",
                    "target_kind": "pe",
                    "authorization_scope": {"kind": "own_asset"},
                }
            )

        ghidra_attempt = next(
            attempt
            for attempt in plan["fallback"]["attempts"]
            if attempt["when"] == "ghidra_available_and_ida_missing"
        )
        self.assertFalse(ghidra_attempt["ready"])
        self.assertIn("analyzeHeadless", ghidra_attempt["missing_capabilities"])
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["preflight"]["input"]["status"], "required")
        self.assertIn("input_path_required", plan["block_reasons"])

    def test_native_binary_route_rejects_a_directory_as_input(self):
        capabilities = {
            "idapro": {"kind": "capability", "service_online": True, "api_ready": True},
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("route_task.load_capabilities", return_value=capabilities):
                plan = build_plan(
                    {
                        "task": "use IDA for static analysis",
                        "target_kind": "pe",
                        "input_path": directory,
                        "authorization_scope": {"kind": "own_asset"},
                    }
                )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["preflight"]["input"]["status"], "invalid")
        self.assertFalse(plan["preflight"]["input"]["ready"])
        self.assertEqual(plan["preflight"]["input"]["reason"], "input_path_not_file")

    def test_dynamic_requirements_are_not_ignored(self):
        self.assertEqual(
            dynamic_requirements(
                "protocol-source-implementation",
                {"task": "Rust codec cargo test"},
            ),
            ["cargo", "rustc"],
        )
        self.assertEqual(
            dynamic_requirements(
                "protocol-source-implementation",
                {"task": "Rust protocol source cargo test"},
            ),
            ["cargo", "rustc"],
        )
        self.assertEqual(
            dynamic_requirements(
                "protocol-source-implementation",
                {"task": "Rust protobuf codec cargo test"},
            ),
            ["cargo", "rustc", "protoc"],
        )
        self.assertEqual(
            dynamic_requirements(
                "js-browser-signature",
                {"task": "CDP hook"},
            ),
            ["jshookmcp"],
        )

    def test_fallback_conditions_are_executable(self):
        self.assertTrue(condition_matches("hook_or_cdp_needed", {"task": "CDP hook"}, []))
        self.assertTrue(condition_matches("idapro_unavailable", {"task": "radare2"}, []))
        self.assertTrue(condition_matches("exploit_path_requested", {"task": "ROP exploit"}, []))

    def test_mcp_presence_is_not_service_readiness(self):
        state = {
            "jshookmcp": {
                "kind": "tool",
                "available": True,
                "mcp_registered": False,
            },
            "idapro": {
                "kind": "capability",
                "service_online": True,
                "api_ready": True,
            },
            "frida": {
                "kind": "capability",
                "tool_available": True,
                "mcp_registered": False,
            },
        }
        self.assertFalse(capability_status("jshookmcp", state)["ready"])
        self.assertTrue(capability_status("idapro", state)["ready"])
        self.assertTrue(capability_status("frida", state)["ready"])
        state["idapro"]["api_ready"] = False
        self.assertFalse(capability_status("idapro", state)["ready"])
        self.assertEqual(FALLBACK_CAPABILITIES["jshookmcp"], ("jshookmcp",))

    def test_authorization_gate(self):
        self.assertFalse(is_authorized({}))
        self.assertTrue(is_authorized({"authorization_scope": {"kind": "own_asset"}}))
        self.assertTrue(is_security_task("api-security", {"task": "test API security"}))

    def test_route_score_prefers_target_and_intent(self):
        route = {
            "id": "native-binary",
            "target_kinds": ["pe"],
            "intent_keywords": ["decompile"],
        }
        result = score_route(route, {"task": "decompile this PE"}, "native-binary")
        self.assertGreater(result["score"], 100)
        self.assertIn("target_kind:native-binary", result["signals"])

    def test_short_ascii_alias_does_not_match_inside_a_word(self):
        plan = build_plan({"task": "audit this Python source project", "target_kind": "source_tree"})
        self.assertNotEqual(plan.get("route", {}).get("base_id"), "native-binary")

    def test_tool_plan_separates_ready_tools_from_unverified_ida_plugins(self):
        stages = {
            "native-binary": [
                {"phase": "open", "tools": ["idapro"]},
                {"phase": "export", "tools": ["DeepExtract"]},
                {"phase": "rust", "when_any": ["rust"], "tools": ["HappyIDA"]},
            ]
        }
        states = {
            "idapro": {"kind": "capability", "service_online": True, "api_ready": True},
            "DeepExtract": {"kind": "ida_plugin", "installed": True, "load_state": "installed_unverified"},
            "HappyIDA": {"kind": "ida_plugin", "installed": True, "load_state": "smoke_passed"},
        }
        plan = build_tool_plan("native-binary", stages, {"task": "analyze a Rust binary"}, states)
        self.assertEqual(plan["stages"][0]["status"], "ready")
        self.assertEqual(plan["stages"][1]["status"], "needs_smoke")
        self.assertEqual(plan["stages"][2]["status"], "ready")

    def test_ida94_native_stages_verify_the_mcp_contract_and_gui_boundary(self):
        stages = {
            "native-binary": [
                {
                    "phase": "reachability",
                    "tools": ["idapro", "ida94-navigation"],
                    "mcp_tools": ["xref_query", "callgraph", "trace_data_flow"],
                },
                {
                    "phase": "dyld",
                    "tools": ["ida94-dyld-shared-cache"],
                    "requires_gui": True,
                },
            ]
        }
        states = {
            "idapro": {
                "kind": "capability",
                "service_online": True,
                "api_ready": True,
                "mcp_tools": ["xref_query", "callgraph", "trace_data_flow"],
            },
            "ida94-navigation": {"kind": "ida_native_feature", "available": True, "load_state": "built_in"},
            "ida94-dyld-shared-cache": {"kind": "ida_native_feature", "available": True, "load_state": "built_in"},
        }
        plan = build_tool_plan("native-binary", stages, {"task": "check reachability and Dyld cache"}, states)
        self.assertEqual(plan["stages"][0]["status"], "ready")
        self.assertEqual(plan["stages"][0]["tools"][1]["reason"], "builtin_ida_feature")
        self.assertTrue(all(item["ready"] for item in plan["stages"][0]["mcp_tools"]))
        self.assertEqual(plan["stages"][1]["status"], "deferred")
        self.assertEqual(plan["stages"][1]["activation"], "gui_mode_required")
        gui_plan = build_tool_plan("native-binary", stages, {"task": "Dyld cache", "mode": "gui"}, states)
        self.assertEqual(gui_plan["stages"][1]["status"], "ready")

    def test_unverified_ida_native_feature_needs_an_explicit_smoke(self):
        stages = {"native-binary": [{"phase": "teams", "tools": ["ida-teams"]}]}
        states = {"ida-teams": {"kind": "ida_native_feature", "available": True, "load_state": "installed_unverified"}}
        plan = build_tool_plan("native-binary", stages, {"task": "IDA Teams"}, states)
        self.assertEqual(plan["stages"][0]["status"], "needs_smoke")
        self.assertEqual(plan["stages"][0]["tools"][0]["reason"], "native_feature_requires_explicit_smoke")

    def test_sentrux_observation_preserves_missing_governance_as_a_gate(self):
        observation = parse_sentrux_observation(
            {
                "returncode": 0,
                "summary": (
                    "[resolve] 82 resolved, 0 unresolved\n"
                    "[build_graphs] 27 files | 82 import, 4153 call, 0 inherit edges\n"
                    "No .sentrux/rules.toml found\n"
                    "Sentrux baseline missing at C:\\repo\\.sentrux\\baseline.json"
                ),
            }
        )
        self.assertEqual(observation["status"], "observed")
        self.assertEqual(observation["resolution"], {"resolved": 82, "unresolved": 0})
        self.assertEqual(observation["graph"], {"files": 27, "imports": 82, "calls": 4153})
        self.assertEqual(observation["rules"], "missing")
        self.assertEqual(observation["baseline"], "missing")

    def test_sentrux_scope_uses_the_unique_aigx_governed_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for scope in (project, project / "crates"):
                sentrux_dir = scope / ".sentrux"
                sentrux_dir.mkdir(parents=True)
                (sentrux_dir / "rules.toml").write_text("[constraints]\n", encoding="utf-8")
                (sentrux_dir / "baseline.json").write_text("{}\n", encoding="utf-8")

            def fake_aigx_runner(_command, args, _cwd):
                target = Path(args[args.index("--resolve") + 1]).as_posix()
                found = target == "crates/.sentrux/baseline.json"
                return {
                    "returncode": 0 if found else 2,
                    "data": {
                        "found": found,
                        "domain": "architecture-governance" if found else None,
                    },
                }

            scope = resolve_sentrux_scope(
                project,
                {"validator": {"path": "aigx"}},
                runner=fake_aigx_runner,
            )

        self.assertTrue(scope["ready"])
        self.assertEqual(scope["relative"], "crates")
        self.assertEqual(scope["source"], "aigx_architecture_governance_boundary")

    def test_sentrux_scope_fails_closed_when_missing_or_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = resolve_sentrux_scope(
                Path(directory),
                {"validator": {"path": "aigx"}},
                runner=lambda *_args: self.fail("AIGX resolve must not run without candidates"),
            )

        self.assertFalse(missing["ready"])
        self.assertEqual(missing["reason"], "sentrux_scope_missing")

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for name in ("crates", "plugins"):
                sentrux_dir = project / name / ".sentrux"
                sentrux_dir.mkdir(parents=True)
                (sentrux_dir / "rules.toml").write_text("[constraints]\n", encoding="utf-8")
                (sentrux_dir / "baseline.json").write_text("{}\n", encoding="utf-8")

            ambiguous = resolve_sentrux_scope(
                project,
                {"validator": {"path": "aigx"}},
                runner=lambda *_args: {
                    "returncode": 0,
                    "data": {"found": True, "domain": "architecture-governance"},
                },
            )

        self.assertFalse(ambiguous["ready"])
        self.assertEqual(ambiguous["reason"], "sentrux_scope_ambiguous")
        self.assertEqual(ambiguous["governed"], ["crates", "plugins"])

    def test_project_intelligence_runs_code_intel_against_resolved_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".aigx").mkdir()
            sentrux_dir = project / "crates" / ".sentrux"
            sentrux_dir.mkdir(parents=True)
            (sentrux_dir / "rules.toml").write_text("[constraints]\n", encoding="utf-8")
            (sentrux_dir / "baseline.json").write_text("{}\n", encoding="utf-8")
            aigx = {
                "status": "ready",
                "ready": True,
                "validator": {"path": "aigx"},
                "boundaries": [],
            }

            def fake_aigx_runner(_command, args, _cwd):
                target = Path(args[args.index("--resolve") + 1]).as_posix()
                found = target == "crates/.sentrux/baseline.json"
                return {
                    "returncode": 0 if found else 2,
                    "data": {
                        "found": found,
                        "domain": "architecture-governance" if found else None,
                    },
                }

            commands = []

            def fake_command(command, _cwd, timeout_seconds=30):
                commands.append(command)
                if "artifact" in command:
                    return {"returncode": 1, "summary": "no current artifact"}
                return {
                    "returncode": 0,
                    "summary": (
                        "[resolve] 2530 resolved, 0 unresolved\n"
                        "[build_graphs] 288 files | 700 import, 1800 call, 0 inherit edges\n"
                        "Quality: 3744 -> 3744\nNo degradation"
                    ),
                }

            with (
                patch("route_task.inspect_aigx_project", return_value=aigx),
                patch("route_task.run_aigx_json", side_effect=fake_aigx_runner),
                patch("route_task.shutil.which", side_effect=lambda name: "code-intel" if name == "code-intel" else None),
                patch("route_task.run_readonly_command", side_effect=fake_command),
            ):
                intelligence = collect_project_intelligence(directory)

        self.assertTrue(intelligence["sentrux"]["ready"])
        self.assertEqual(intelligence["sentrux"]["scope"]["relative"], "crates")
        sentrux_commands = [command for command in commands if command[1:3] == ["sentrux", "check"]]
        self.assertEqual(len(sentrux_commands), 1)
        self.assertEqual(Path(sentrux_commands[0][-1]).resolve(), (project / "crates").resolve())
        self.assertNotEqual(Path(sentrux_commands[0][-1]).resolve(), project.resolve())

    def test_failed_sentrux_check_does_not_claim_rules_are_present(self):
        observation = parse_sentrux_observation({"returncode": 2, "summary": "Sentrux command failed"})
        self.assertEqual(observation["status"], "unavailable")
        self.assertEqual(observation["rules"], "unknown")
        self.assertEqual(observation["baseline"], "unknown")

    def test_sentrux_gate_without_baseline_is_an_observation_not_a_missing_cli(self):
        observation = parse_sentrux_observation(
            {
                "returncode": 1,
                "summary": (
                    "[build_graphs] 447 files | maps 0.1ms | 2 import, 7 call, 0 inherit edges\n"
                    "Failed to load baseline at .sentrux/baseline.json\n"
                    "Run `sentrux gate --save` first to create one."
                ),
            }
        )
        self.assertEqual(observation["status"], "observed")
        self.assertEqual(observation["baseline"], "missing")
        self.assertEqual(observation["graph"], {"files": 447, "imports": 2, "calls": 7})

    def test_sentrux_stage_requires_a_project_path(self):
        stages = {
            "architecture-governance": [
                {"phase": "rules", "requires_project_path": True, "tools": ["sentrux"]}
            ]
        }
        states = {"sentrux": {"kind": "tool", "available": True, "version": "sentrux 0.5.7"}}
        no_project = build_tool_plan("architecture-governance", stages, {"task": "sentrux check"}, states)
        with_project = build_tool_plan(
            "architecture-governance",
            stages,
            {"task": "sentrux check", "project_path": r"C:\repo"},
            states,
        )
        self.assertEqual(no_project["stages"][0]["status"], "deferred")
        self.assertEqual(no_project["stages"][0]["activation"], "project_path_required")
        self.assertEqual(with_project["stages"][0]["status"], "ready")

    def test_architecture_route_blocks_when_the_scoped_gate_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            intelligence = {
                "status": "observed",
                "aigx": {"status": "ready", "ready": True, "boundaries": []},
                "code_intel": {"status": "authoritative"},
                "sentrux": {
                    "status": "observed",
                    "ready": False,
                    "exit_code": 1,
                    "rules": "present",
                    "baseline": "present",
                    "scope": {"status": "ready", "ready": True, "relative": "crates"},
                },
            }
            capabilities = {
                "sentrux": {"kind": "tool", "available": True, "version": "sentrux"},
            }
            with (
                patch("route_task.collect_project_intelligence", return_value=intelligence),
                patch("route_task.load_capabilities", return_value=capabilities),
            ):
                plan = build_plan(
                    {
                        "task": "run a Sentrux architecture check",
                        "target_kind": "source_tree",
                        "project_path": directory,
                    }
                )

        self.assertEqual(plan["route"]["base_id"], "architecture-governance")
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("sentrux_gate_failed", plan["block_reasons"])

    def test_architecture_dispatch_reuses_the_aigx_resolved_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            scoped_command = ["code-intel", "sentrux", "check", str(Path(directory) / "crates")]
            intelligence = {
                "status": "observed",
                "aigx": {"status": "ready", "ready": True, "boundaries": []},
                "code_intel": {"status": "authoritative"},
                "sentrux": {
                    "status": "observed",
                    "ready": True,
                    "exit_code": 0,
                    "rules": "present",
                    "baseline": "present",
                    "scope": {"status": "ready", "ready": True, "relative": "crates"},
                    "commands": {"check": scoped_command},
                },
            }
            capabilities = {
                "sentrux": {"kind": "tool", "available": True, "version": "sentrux"},
            }
            with (
                patch("route_task.collect_project_intelligence", return_value=intelligence),
                patch("route_task.load_capabilities", return_value=capabilities),
            ):
                plan = build_plan(
                    {
                        "task": "run a Sentrux architecture check",
                        "target_kind": "source_tree",
                        "project_path": directory,
                    }
                )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["dispatch"]["command"], scoped_command)
        self.assertEqual(plan["dispatch"]["reason"], "controlled_code_intel_sentrux_check")

    def test_teams_preflight_stage_requires_a_repository_path(self):
        stages = {
            "native-binary": [
                {"phase": "teams-git-preflight", "requires_repo_path": True, "tools": ["git-ida"]}
            ]
        }
        states = {"git-ida": {"kind": "tool", "available": True, "version": "git-ida v1.0.9"}}
        no_repo = build_tool_plan("native-binary", stages, {"task": "IDA Teams git-ida"}, states)
        with_repo = build_tool_plan(
            "native-binary",
            stages,
            {"task": "IDA Teams git-ida", "repo_path": r"C:\\repo"},
            states,
        )
        with_contract = build_tool_plan(
            "native-binary",
            stages,
            {"task": "IDA Teams git-ida", "teams_contract_path": r"C:\\private\\collaboration.json"},
            states,
        )
        with_worktree_contract = build_tool_plan(
            "native-binary",
            stages,
            {"task": "IDA Teams worktree", "teams_worktree_contract_path": r"C:\\private\\lab.json"},
            states,
        )
        self.assertEqual(no_repo["stages"][0]["status"], "deferred")
        self.assertEqual(no_repo["stages"][0]["activation"], "teams_context_required")
        self.assertEqual(with_repo["stages"][0]["status"], "ready")
        self.assertEqual(with_contract["stages"][0]["status"], "ready")
        self.assertEqual(with_worktree_contract["stages"][0]["status"], "ready")

    def test_teams_repository_plan_does_not_require_an_artifact_input(self):
        capabilities = {
            "git-ida": {"kind": "tool", "available": True, "version": "git-ida"},
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("route_task.load_capabilities", return_value=capabilities):
                plan = build_plan(
                    {
                        "task": "IDA Teams git-ida collaboration",
                        "target_kind": "pe",
                        "repo_path": directory,
                    }
                )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["preflight"]["input"]["status"], "not_provided")
        self.assertTrue(plan["preflight"]["input"]["ready"])
        self.assertNotIn("requires", plan["dispatch"])

    def test_teams_artifact_analysis_fails_closed_without_losing_analysis_oracles(self):
        capabilities = {
            "git-ida": {"kind": "tool", "available": True, "version": "git-ida"},
        }
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "sample.exe"
            artifact.write_bytes(b"MZ")
            with patch("route_task.load_capabilities", return_value=capabilities):
                plan = build_plan(
                    {
                        "task": "使用 IDA Teams 多 Agent 并行分析这个 PE，要求函数标注和控制流证据",
                        "target_kind": "pe",
                        "input_path": str(artifact),
                        "repo_path": directory,
                        "authorization_scope": {"kind": "own_asset"},
                    }
                )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["preflight"]["status"], "blocked")
        self.assertEqual(plan["preflight"]["composite_workflow"]["reason"], "composite_workflow_not_supported")
        self.assertIn("composite_workflow_not_supported", plan["block_reasons"])
        self.assertFalse(plan["dispatch"]["executable"])
        self.assertIsNone(plan["dispatch"]["command"])
        self.assertIn("target_function_labeled", plan["success_oracles"])
        self.assertIn("control_flow_evidence_recorded", plan["success_oracles"])

    def test_excluded_teams_stage_is_not_described_as_missing_context(self):
        stages = {
            "native-binary": [
                {"phase": "teams-preflight", "requires_repo_path": True, "unless_any": ["teams worktree"], "tools": ["git-ida"]}
            ]
        }
        states = {"git-ida": {"kind": "tool", "available": True, "version": "git-ida v1.0.9"}}
        plan = build_tool_plan("native-binary", stages, {"task": "IDA Teams worktree"}, states)
        self.assertFalse(plan["stages"][0]["active"])
        self.assertEqual(plan["stages"][0]["activation"], "excluded:teams worktree")

    def test_teams_contract_selects_the_collaboration_planner(self):
        from route_task import build_entrypoint

        entrypoint = build_entrypoint(
            "ida-reverse/SKILL.md",
            {
                "task": "IDA Teams git-ida collaboration",
                "teams_contract_path": r"C:\\teams-lab\\collaboration.json",
            },
        )
        self.assertEqual(entrypoint["reason"], "controlled_teams_collaboration_plan")
        self.assertIsNone(entrypoint["script"])
        self.assertEqual(entrypoint["command"][1:5], ["-m", "reverse_skill", "teams", "plan"])
        self.assertNotIn("requires", entrypoint)

    def test_teams_worktree_contract_selects_the_isolated_lab_creator(self):
        from route_task import build_entrypoint

        entrypoint = build_entrypoint(
            "ida-reverse/SKILL.md",
            {
                "task": "IDA Teams worktree lab",
                "teams_worktree_contract_path": r"C:\\private\\lab.json",
                "teams_lab_apply": True,
            },
        )
        self.assertEqual(entrypoint["reason"], "controlled_teams_worktree_lab")
        self.assertIsNone(entrypoint["script"])
        self.assertEqual(entrypoint["command"][1:5], ["-m", "reverse_skill", "teams", "lab"])
        self.assertIn("--apply", entrypoint["command"])
        self.assertNotIn("requires", entrypoint)

    def test_workspace_search_selects_the_health_aware_python_entrypoint(self):
        from route_task import build_entrypoint

        entrypoint = build_entrypoint(
            "reverse-engineering/SKILL.md",
            {
                "task": "workspace search with xcmd",
                "search_path": r"C:\\private\\source",
                "search_query": "needle",
                "search_engine": "auto",
                "search_globs": ["*.rs"],
            },
        )
        self.assertEqual(entrypoint["reason"], "controlled_workspace_search")
        self.assertIsNone(entrypoint["script"])
        self.assertEqual(entrypoint["command"][1:4], ["-m", "reverse_skill", "search"])
        self.assertIn("needle", entrypoint["command"])
        self.assertIn("*.rs", entrypoint["command"])
        self.assertNotIn("requires", entrypoint)

    def test_workspace_search_cli_arguments_route_without_natural_language(self):
        parser = build_parser()
        task = parse_task(parser.parse_args(["--search-path", r"C:\\private\\source", "--search-query", "needle"]))
        self.assertEqual(infer_target_kind(task), "workspace-search")

    def test_worktree_request_without_contract_stays_on_the_isolation_entrypoint(self):
        from route_task import build_entrypoint

        entrypoint = build_entrypoint("ida-reverse/SKILL.md", {"task": "IDA Teams worktree lab"})
        self.assertEqual(entrypoint["reason"], "controlled_teams_worktree_lab")
        self.assertIsNone(entrypoint["script"])
        self.assertEqual(entrypoint["requires"], ["teams_worktree_contract"])
        self.assertIsNone(entrypoint["command"])


if __name__ == "__main__":
    unittest.main()
