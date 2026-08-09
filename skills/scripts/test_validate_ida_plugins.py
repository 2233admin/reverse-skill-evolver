"""Regression tests for the read-only IDA plugin compatibility validator."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from validate_ida_plugins import validate_plugin_tree
from refresh_ida_capabilities import plugin_load_state


class ValidateIdaPluginsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_plugin(
        self,
        name: str,
        source: str = "VALUE = 1\n",
        *,
        entry_point: str = "plugin.py",
        ida_versions: object = ">=9.0",
    ) -> Path:
        plugin_dir = self.root / name
        plugin_dir.mkdir()
        plugin = {
            "name": name,
            "entryPoint": entry_point,
            "version": "1.2.3",
        }
        if ida_versions is not None:
            plugin["idaVersions"] = ida_versions
        (plugin_dir / "ida-plugin.json").write_text(
            json.dumps({"IDAMetadataDescriptorVersion": 1, "plugin": plugin}),
            encoding="utf-8",
        )
        (plugin_dir / entry_point).write_text(source, encoding="utf-8")
        return plugin_dir

    def validate(self, *, python_version: tuple[int, int, int] = (3, 14, 0)):
        return validate_plugin_tree(
            self.root,
            ida_version="9.4",
            python_executable=Path(sys.executable),
            python_version=python_version,
        )

    def test_removed_readfp_is_runtime_incompatible_on_python_312_plus(self):
        self.add_plugin(
            "legacy-config",
            "import configparser\nconfigparser.RawConfigParser().readfp(open('x'))\n",
        )

        report = self.validate(python_version=(3, 12, 0))

        plugin = report["plugins"][0]
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(plugin["runtime_compatible"])
        self.assertIn("python_removed_api_readfp", {issue["code"] for issue in plugin["issues"]})

    def test_read_file_is_compatible_in_static_runtime_preflight(self):
        self.add_plugin(
            "modern-config",
            "import configparser\nconfigparser.RawConfigParser().read_file(open('x'))\n",
        )

        report = self.validate()

        plugin = report["plugins"][0]
        self.assertEqual(report["status"], "observed")
        self.assertTrue(plugin["runtime_compatible"])
        self.assertEqual(plugin["runtime_loaded"], "not_run")
        self.assertEqual(plugin["action_verified"], "not_run")

    def test_native_entrypoint_resolves_platform_suffix(self):
        plugin_dir = self.add_plugin("native", entry_point="native_ida64")
        (plugin_dir / "native_ida64").unlink()
        (plugin_dir / "native_ida64.dll").write_bytes(b"MZ")

        report = self.validate()

        plugin = report["plugins"][0]
        self.assertTrue(plugin["entrypoint_exists"])
        self.assertEqual(plugin["entrypoint_kind"], "native")
        self.assertIsNone(plugin["runtime_compatible"])
        self.assertNotIn("entrypoint_missing", {issue["code"] for issue in plugin["issues"]})

    def test_ida_version_list_is_alternative_not_conjunction(self):
        self.add_plugin("versions", ida_versions=["8.4", "9.4"])

        report = self.validate()

        self.assertTrue(report["plugins"][0]["ida_version_compatible"])
        self.assertEqual(report["status"], "observed")

    def test_version_list_accepts_a_match_after_a_service_pack_label(self):
        self.add_plugin("versions", ida_versions=["9.0sp1", "9.4"])

        report = self.validate()

        self.assertTrue(report["plugins"][0]["ida_version_compatible"])
        self.assertEqual(report["status"], "observed")

    def test_incompatible_ida_version_blocks(self):
        self.add_plugin("old", ida_versions=["8.4", "9.2"])

        report = self.validate()

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["plugins"][0]["ida_version_compatible"])
        self.assertTrue(report["plugins"][0]["runtime_compatible"])

    def test_malformed_manifest_fails_closed(self):
        plugin_dir = self.root / "bad"
        plugin_dir.mkdir()
        (plugin_dir / "ida-plugin.json").write_text("{", encoding="utf-8")

        report = self.validate()

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["summary"]["invalid"], 1)
        self.assertIn("manifest_invalid_json", {issue["code"] for issue in report["plugins"][0]["issues"]})

    def test_missing_entrypoint_fails_closed(self):
        plugin_dir = self.add_plugin("missing")
        (plugin_dir / "plugin.py").unlink()

        report = self.validate()

        self.assertEqual(report["status"], "blocked")
        self.assertIn("entrypoint_missing", {issue["code"] for issue in report["plugins"][0]["issues"]})

    def test_validation_does_not_write_plugin_tree(self):
        self.add_plugin("no-write")
        before = {
            path.relative_to(self.root): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }

        self.validate()

        after = {
            path.relative_to(self.root): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_capability_state_keeps_preflight_distinct_from_gui_smoke(self):
        compatible = {
            "ida_version_compatible": True,
            "runtime_compatible": True,
            "status": "compatible_preflight",
        }
        runtime_bad = {**compatible, "runtime_compatible": False, "status": "incompatible"}
        ida_bad = {**compatible, "ida_version_compatible": False, "status": "incompatible"}

        self.assertEqual(plugin_load_state(True, compatible), "compatible_preflight")
        self.assertEqual(plugin_load_state(True, runtime_bad), "runtime_incompatible")
        self.assertEqual(plugin_load_state(True, ida_bad), "manifest_incompatible")
        self.assertEqual(plugin_load_state(True, None), "installed_unverified")
        self.assertEqual(plugin_load_state(False, None), "missing")


if __name__ == "__main__":
    unittest.main()
