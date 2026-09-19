import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "src" / "model_display.py"
SPEC = importlib.util.spec_from_file_location("model_display", MODULE_PATH)
model_display = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(model_display)

HERMES_MODULE_PATH = Path(__file__).parents[1] / "adapters" / "hermes" / "__init__.py"
HERMES_SPEC = importlib.util.spec_from_file_location(
    "hermes_model_display", HERMES_MODULE_PATH
)
hermes_model_display = importlib.util.module_from_spec(HERMES_SPEC)
assert HERMES_SPEC.loader is not None
HERMES_SPEC.loader.exec_module(hermes_model_display)


class Completed:
    returncode = 0


class ModelDisplayTests(unittest.TestCase):
    def test_compacts_known_provider_prefix(self):
        self.assertEqual(model_display.compact_model_name("openai/gpt-5.6"), "gpt-5.6")

    def test_preserves_unknown_provider_prefix(self):
        self.assertEqual(model_display.compact_model_name("acme/model"), "acme/model")

    def test_compacts_effort_levels(self):
        self.assertEqual(model_display.compact_effort_level("medium"), "med")
        self.assertEqual(model_display.compact_effort_level("xhigh"), "xh")
        self.assertEqual(model_display.compact_effort_level("ultra"), "ult")

    @patch.object(model_display.subprocess, "run", return_value=Completed())
    def test_reports_display_name_and_token(self, run):
        with patch.dict(os.environ, {"HERDR_BIN_PATH": "/bin/herdr"}):
            result = model_display.report_model(
                "1-2", "codex", "openai/gpt-5.6", "medium"
            )
        self.assertEqual(result, 0)
        command = run.call_args.args[0]
        self.assertIn("codex - gpt-5.6 - med", command)
        self.assertIn("model=gpt-5.6", command)
        self.assertIn("effort=med", command)

    @patch.object(model_display.subprocess, "run", return_value=Completed())
    def test_report_without_effort_clears_stale_effort_token(self, run):
        with patch.dict(os.environ, {"HERDR_BIN_PATH": "/bin/herdr"}):
            model_display.report_model("1-2", "codex", "gpt-5.6")
        command = run.call_args.args[0]
        clear_index = command.index("--clear-token")
        self.assertEqual(command[clear_index + 1], "effort")

    @patch.object(model_display.subprocess, "run", return_value=Completed())
    def test_clear_removes_model_and_effort_tokens(self, run):
        with patch.dict(os.environ, {"HERDR_BIN_PATH": "/bin/herdr"}):
            model_display.clear_model("1-2", "codex")
        command = run.call_args.args[0]
        cleared = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--clear-token"
        ]
        self.assertEqual(cleared, ["model", "effort"])

    @patch.object(model_display, "report_model", return_value=0)
    def test_codex_hook_reports_model_and_effort(self, report):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-5.6",
            "reasoning_effort": "high",
        }
        with patch.dict(os.environ, {"HERDR_PANE_ID": "1-2"}, clear=True):
            self.assertEqual(model_display.codex_hook(payload), 0)
        report.assert_called_once_with("1-2", "codex", "gpt-5.6", "high")

    def test_codex_reads_session_effort_from_transcript(self):
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "session.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {
                            "collaboration_mode": {
                                "settings": {"reasoning_effort": "xhigh"}
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                model_display.codex_transcript_effort(str(transcript)), "xhigh"
            )

    def test_codex_reads_default_effort_from_model_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            codex = Path(temporary)
            (codex / "models_cache.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "slug": "gpt-5.6",
                                "default_reasoning_level": "medium",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"CODEX_HOME": str(codex)}, clear=True):
                self.assertEqual(
                    model_display.codex_default_effort("openai/gpt-5.6"), "medium"
                )

    @patch.object(model_display, "clear_model", return_value=0)
    def test_session_end_clears_model(self, clear):
        payload = {"hook_event_name": "SessionEnd", "model": "gpt-5.6"}
        with patch.dict(os.environ, {"HERDR_PANE_ID": "1-2"}, clear=True):
            self.assertEqual(model_display.codex_hook(payload), 0)
        clear.assert_called_once_with("1-2", "codex")

    @patch.object(model_display, "report_model", return_value=0)
    def test_hook_outside_herdr_is_noop(self, report):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(model_display.codex_hook({"model": "gpt-5.6"}), 0)
        report.assert_not_called()

    def test_install_preserves_existing_hooks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex = root / "codex"
            plugin = root / "plugin"
            codex.mkdir()
            existing = {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "existing-hook"}]}
                    ]
                }
            }
            (codex / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")
            environment = {
                "CODEX_HOME": str(codex),
                "HERDR_PLUGIN_CONFIG_DIR": str(plugin),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(model_display.install_codex(), 0)
            installed = json.loads((codex / "hooks.json").read_text(encoding="utf-8"))
            commands = [
                hook["command"]
                for group in installed["hooks"]["SessionStart"]
                for hook in group["hooks"]
            ]
            self.assertIn("existing-hook", commands)
            self.assertTrue(
                any(model_display.CODEX_MARKER in command for command in commands)
            )
            session_end_hook = installed["hooks"]["SessionEnd"][0]["hooks"][0]
            self.assertEqual(session_end_hook["timeout"], 3)

    def test_install_is_idempotent_and_uninstall_preserves_others(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "CODEX_HOME": str(root / "codex"),
                "HERDR_PLUGIN_CONFIG_DIR": str(root / "plugin"),
            }
            with patch.dict(os.environ, environment, clear=True):
                model_display.install_codex()
                model_display.install_codex()
                data = model_display.load_hooks(root / "codex" / "hooks.json")
                for event in model_display.CODEX_HOOK_EVENTS:
                    managed = [
                        g
                        for g in data["hooks"][event]
                        if model_display.is_our_hook(g, model_display.CODEX_MARKER)
                    ]
                    self.assertEqual(len(managed), 1)
                model_display.uninstall_codex()
                data = model_display.load_hooks(root / "codex" / "hooks.json")
                self.assertFalse(any(data["hooks"].values()))

    @patch.object(model_display, "report_model", return_value=0)
    def test_claude_session_start_reports_model(self, report):
        payload = {
            "hook_event_name": "SessionStart",
            "model": "claude-sonnet-4-6",
            "effort": {"level": "high"},
        }
        with patch.dict(os.environ, {"HERDR_PANE_ID": "1-3"}, clear=True):
            self.assertEqual(model_display.claude_hook(payload), 0)
        report.assert_called_once_with("1-3", "claude", "claude-sonnet-4-6", "high")

    @patch.object(model_display, "report_model", return_value=0)
    def test_claude_model_switch_reports_target(self, report):
        payload = {
            "hook_event_name": "PostModelSwitch",
            "from_model": "claude-sonnet-4-6",
            "to_model": "claude-opus-5",
        }
        with patch.dict(os.environ, {"HERDR_PANE_ID": "1-3"}, clear=True):
            self.assertEqual(model_display.claude_hook(payload), 0)
        report.assert_called_once_with("1-3", "claude", "claude-opus-5", "")

    @patch.object(model_display, "report_model", return_value=0)
    def test_claude_subagent_does_not_replace_root_model(self, report):
        payload = {
            "hook_event_name": "SessionStart",
            "model": "claude-haiku-4-5",
            "agent_id": "child-1",
        }
        with patch.dict(os.environ, {"HERDR_PANE_ID": "1-3"}, clear=True):
            self.assertEqual(model_display.claude_hook(payload), 0)
        report.assert_not_called()

    def test_claude_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "CLAUDE_CONFIG_DIR": str(root / "claude"),
                "HERDR_PLUGIN_CONFIG_DIR": str(root / "plugin"),
            }
            with patch.dict(os.environ, environment, clear=True):
                model_display.install_claude()
                model_display.install_claude()
                data = model_display.load_hooks(root / "claude" / "settings.json")
                for event in model_display.CLAUDE_HOOK_EVENTS:
                    managed = [
                        g
                        for g in data["hooks"][event]
                        if model_display.is_our_hook(g, model_display.CLAUDE_MARKER)
                    ]
                    self.assertEqual(len(managed), 1)

    def test_pi_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "PI_CODING_AGENT_DIR": str(root / "pi"),
                "HERDR_PLUGIN_ROOT": str(Path(__file__).parents[1]),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(model_display.install_pi(), 0)
                destination = root / "pi" / "extensions" / "herdr-model-display.ts"
                self.assertIn('pi.on("model_select"', destination.read_text())
                self.assertIn('pi.on("thinking_level_select"', destination.read_text())
                self.assertEqual(model_display.uninstall_pi(), 0)
                self.assertFalse(destination.exists())

    @patch.object(model_display.shutil, "which", return_value=None)
    def test_hermes_install_and_uninstall(self, _which):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "HERMES_HOME": str(root / "hermes"),
                "HERDR_PLUGIN_ROOT": str(Path(__file__).parents[1]),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(model_display.install_hermes(), 0)
                destination = root / "hermes" / "plugins" / "herdr-model-display"
                self.assertTrue((destination / "plugin.yaml").exists())
                self.assertEqual(model_display.uninstall_hermes(), 0)
                self.assertFalse(destination.exists())

    @patch.object(hermes_model_display, "_run")
    def test_hermes_reports_request_effort(self, run):
        hermes_model_display._report_request(
            model="anthropic/claude-opus-5",
            request={"output_config": {"effort": "xhigh"}},
        )
        command = run.call_args.args[0]
        self.assertIn("hermes - claude-opus-5 - xh", command)
        self.assertIn("effort=xh", command)


if __name__ == "__main__":
    unittest.main()
