#!/usr/bin/env python3
"""Herdr Model Display plugin and Codex hook adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any


SOURCE = "herdr-model-display:codex"
MARKER = "herdr-model-display-codex-hook"
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "SessionEnd")


def compact_model_name(model: str) -> str:
    """Keep the useful model slug while removing common provider prefixes."""
    value = model.strip()
    for prefix in ("openai/", "anthropic/", "google/"):
        if value.lower().startswith(prefix):
            return value[len(prefix) :]
    return value


def herdr_command() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def report_model(pane_id: str, harness: str, model: str) -> int:
    model = compact_model_name(model)
    if not model:
        return 0

    label = f"{harness} - {model}"
    command = [
        herdr_command(),
        "pane",
        "report-metadata",
        pane_id,
        "--source",
        f"herdr-model-display:{harness}",
        "--agent",
        harness,
        "--display-agent",
        label,
        "--token",
        f"model={model}",
    ]
    return subprocess.run(command, check=False).returncode


def clear_model(pane_id: str, harness: str) -> int:
    command = [
        herdr_command(),
        "pane",
        "report-metadata",
        pane_id,
        "--source",
        f"herdr-model-display:{harness}",
        "--agent",
        harness,
        "--clear-display-agent",
        "--clear-token",
        "model",
    ]
    return subprocess.run(command, check=False).returncode


def codex_hook(payload: dict[str, Any]) -> int:
    pane_id = os.environ.get("HERDR_PANE_ID", "").strip()
    if not pane_id:
        return 0

    event = str(payload.get("hook_event_name", ""))
    if event == "SessionEnd":
        return clear_model(pane_id, "codex")

    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        return report_model(pane_id, "codex", model)
    return 0


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def plugin_config_dir() -> Path:
    configured = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".config" / "herdr" / "plugins" / "dev.pdalinis.model-display"


def hook_command(script_path: Path) -> str:
    return f"python3 {shlex.quote(str(script_path))} codex-hook # {MARKER}"


def is_our_hook(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(
        isinstance(item, dict) and MARKER in str(item.get("command", ""))
        for item in hooks
    )


def load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path}: 'hooks' must be a JSON object")
    return data


def write_hooks(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def remove_managed_groups(data: dict[str, Any]) -> bool:
    changed = False
    hooks = data.get("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        filtered = [group for group in groups if not is_our_hook(group)]
        if len(filtered) != len(groups):
            changed = True
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]
    return changed


def install_codex() -> int:
    source = Path(__file__).resolve()
    destination_dir = plugin_config_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "codex-hook.py"
    shutil.copy2(source, destination)

    hooks_path = codex_home() / "hooks.json"
    data = load_hooks(hooks_path)
    remove_managed_groups(data)
    command = hook_command(destination)
    for event in HOOK_EVENTS:
        data["hooks"].setdefault(event, []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 5,
                    }
                ]
            }
        )
    write_hooks(hooks_path, data)
    print(f"Installed Codex hooks in {hooks_path}")
    print("Restart Codex sessions to activate model display.")
    return 0


def uninstall_codex() -> int:
    hooks_path = codex_home() / "hooks.json"
    if hooks_path.exists():
        data = load_hooks(hooks_path)
        if remove_managed_groups(data):
            write_hooks(hooks_path, data)

    adapter = plugin_config_dir() / "codex-hook.py"
    if adapter.exists():
        adapter.unlink()
    print("Removed Codex model-display hooks.")
    return 0


def status() -> int:
    hooks_path = codex_home() / "hooks.json"
    if not hooks_path.exists():
        print("Codex: not configured")
        return 1
    data = load_hooks(hooks_path)
    configured = all(
        any(is_our_hook(group) for group in data["hooks"].get(event, []))
        for event in HOOK_EVENTS
    )
    print(f"Codex: {'configured' if configured else 'not configured'}")
    return 0 if configured else 1


def read_stdin_payload() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(f"Invalid hook JSON: {error}", file=sys.stderr)
        return {}
    return value if isinstance(value, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install-codex", help="Install the companion Codex hooks")
    commands.add_parser("uninstall-codex", help="Remove the companion Codex hooks")
    commands.add_parser("status", help="Check adapter installation")
    commands.add_parser("codex-hook", help="Handle a Codex hook payload from stdin")

    report = commands.add_parser("report", help="Report a model from another adapter")
    report.add_argument("--pane", default=os.environ.get("HERDR_PANE_ID"))
    report.add_argument("--harness", required=True)
    report.add_argument("--model", required=True)

    clear = commands.add_parser("clear", help="Clear a model reported by another adapter")
    clear.add_argument("--pane", default=os.environ.get("HERDR_PANE_ID"))
    clear.add_argument("--harness", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install-codex":
        return install_codex()
    if args.command == "uninstall-codex":
        return uninstall_codex()
    if args.command == "status":
        return status()
    if args.command == "codex-hook":
        return codex_hook(read_stdin_payload())
    if args.command == "report":
        if not args.pane:
            raise SystemExit("--pane or HERDR_PANE_ID is required")
        return report_model(args.pane, args.harness, args.model)
    if args.command == "clear":
        if not args.pane:
            raise SystemExit("--pane or HERDR_PANE_ID is required")
        return clear_model(args.pane, args.harness)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
