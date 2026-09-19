#!/usr/bin/env python3
"""Herdr Model Display plugin and harness adapter installer."""

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


CODEX_MARKER = "herdr-model-display-codex-hook"
CODEX_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "SessionEnd")
CLAUDE_MARKER = "herdr-model-display-claude-hook"
CLAUDE_HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PostModelSwitch",
    "SessionEnd",
)
EFFORT_ABBREVIATIONS = {
    "none": "off",
    "off": "off",
    "minimal": "min",
    "min": "min",
    "low": "low",
    "medium": "med",
    "med": "med",
    "high": "high",
    "xhigh": "xh",
    "extra-high": "xh",
    "extra_high": "xh",
    "max": "max",
    "ultra": "ult",
    "auto": "auto",
    "default": "auto",
}


def compact_model_name(model: str) -> str:
    """Keep the useful model slug while removing common provider prefixes."""
    value = model.strip()
    for prefix in ("openai/", "anthropic/", "google/"):
        if value.lower().startswith(prefix):
            return value[len(prefix) :]
    return value


def compact_effort_level(effort: Any) -> str:
    """Return a short display value for a harness reasoning effort."""
    if not isinstance(effort, str):
        return ""
    value = effort.strip().lower()
    if not value:
        return ""
    return EFFORT_ABBREVIATIONS.get(value, value[:6])


def payload_effort(payload: dict[str, Any]) -> str:
    """Read effort from the common shapes used by harness hook payloads."""
    for key in ("reasoning_effort", "model_reasoning_effort", "thinking_level"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value

    effort = payload.get("effort")
    if isinstance(effort, str):
        return effort
    if isinstance(effort, dict) and isinstance(effort.get("level"), str):
        return effort["level"]

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), str):
        return reasoning["effort"]
    return ""


def codex_transcript_effort(transcript_path: Any) -> str:
    """Best-effort lookup of the latest per-session Codex effort override."""
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        return ""
    path = Path(transcript_path).expanduser()
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            start = max(0, handle.tell() - 262_144)
            handle.seek(start)
            data = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return ""

    for line in reversed(data.splitlines()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = item.get("payload") if isinstance(item, dict) else None
        if not isinstance(payload, dict):
            continue
        candidates = [payload]
        thread_settings = payload.get("thread_settings")
        if isinstance(thread_settings, dict):
            candidates.append(thread_settings)
        for candidate in candidates:
            collaboration = candidate.get("collaboration_mode")
            if not isinstance(collaboration, dict):
                continue
            settings = collaboration.get("settings")
            if not isinstance(settings, dict) or "reasoning_effort" not in settings:
                continue
            value = settings.get("reasoning_effort")
            return value if isinstance(value, str) else ""
    return ""


def codex_default_effort(model: str) -> str:
    """Read the selected model's default effort from Codex's local catalog."""
    path = codex_home() / "models_cache.json"
    try:
        with path.open(encoding="utf-8") as handle:
            catalog = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list):
        return ""
    compact_model = compact_model_name(model)
    for entry in models:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug")
        if isinstance(slug, str) and compact_model_name(slug) == compact_model:
            value = entry.get("default_reasoning_level")
            return value if isinstance(value, str) else ""
    return ""


def herdr_command() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def report_model(pane_id: str, harness: str, model: str, effort: str = "") -> int:
    model = compact_model_name(model)
    if not model:
        return 0

    effort = compact_effort_level(effort)
    label = f"{harness} - {model}"
    if effort:
        label += f" - {effort}"
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
    if effort:
        command.extend(["--token", f"effort={effort}"])
    else:
        command.extend(["--clear-token", "effort"])
    return subprocess.run(
        command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode


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
        "--clear-token",
        "effort",
    ]
    return subprocess.run(
        command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode


def codex_hook(payload: dict[str, Any]) -> int:
    pane_id = os.environ.get("HERDR_PANE_ID", "").strip()
    if not pane_id:
        return 0

    event = str(payload.get("hook_event_name", ""))
    if event == "SessionEnd":
        return clear_model(pane_id, "codex")

    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        effort = payload_effort(payload)
        if not effort:
            effort = os.environ.get("CODEX_REASONING_EFFORT", "")
        if not effort:
            effort = codex_transcript_effort(payload.get("transcript_path"))
        if not effort:
            effort = codex_default_effort(model)
        return report_model(pane_id, "codex", model, effort)
    return 0


def claude_hook(payload: dict[str, Any]) -> int:
    pane_id = os.environ.get("HERDR_PANE_ID", "").strip()
    if not pane_id or payload.get("agent_id"):
        return 0

    event = str(payload.get("hook_event_name", ""))
    if event == "SessionEnd":
        return clear_model(pane_id, "claude")

    model = (
        payload.get("to_model") if event == "PostModelSwitch" else payload.get("model")
    )
    if isinstance(model, str) and model.strip():
        effort = payload_effort(payload) or os.environ.get("CLAUDE_EFFORT", "")
        return report_model(pane_id, "claude", model, effort)
    return 0


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def claude_home() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def pi_home() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return (
        Path(configured).expanduser() if configured else Path.home() / ".pi" / "agent"
    )


def hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".hermes"


def plugin_config_dir() -> Path:
    configured = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".config" / "herdr" / "plugins" / "dev.pdalinis.model-display"


def plugin_root() -> Path:
    configured = os.environ.get("HERDR_PLUGIN_ROOT")
    return Path(configured) if configured else Path(__file__).resolve().parents[1]


def hook_command(script_path: Path, subcommand: str, marker: str) -> str:
    return f"python3 {shlex.quote(str(script_path))} {subcommand} # {marker}"


def is_our_hook(group: Any, marker: str) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(
        isinstance(item, dict) and marker in str(item.get("command", ""))
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


def remove_managed_groups(data: dict[str, Any], marker: str) -> bool:
    changed = False
    hooks = data.get("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        filtered = [group for group in groups if not is_our_hook(group, marker)]
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
    remove_managed_groups(data, CODEX_MARKER)
    command = hook_command(destination, "codex-hook", CODEX_MARKER)
    for event in CODEX_HOOK_EVENTS:
        data["hooks"].setdefault(event, []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 3 if event == "SessionEnd" else 5,
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
        if remove_managed_groups(data, CODEX_MARKER):
            write_hooks(hooks_path, data)

    adapter = plugin_config_dir() / "codex-hook.py"
    if adapter.exists():
        adapter.unlink()
    print("Removed Codex model-display hooks.")
    return 0


def install_claude() -> int:
    source = Path(__file__).resolve()
    destination_dir = plugin_config_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "claude-hook.py"
    shutil.copy2(source, destination)

    settings_path = claude_home() / "settings.json"
    data = load_hooks(settings_path)
    remove_managed_groups(data, CLAUDE_MARKER)
    command = hook_command(destination, "claude-hook", CLAUDE_MARKER)
    for event in CLAUDE_HOOK_EVENTS:
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
    write_hooks(settings_path, data)
    print(f"Installed Claude hooks in {settings_path}")
    print("Restart Claude sessions to activate model display.")
    return 0


def uninstall_claude() -> int:
    settings_path = claude_home() / "settings.json"
    if settings_path.exists():
        data = load_hooks(settings_path)
        if remove_managed_groups(data, CLAUDE_MARKER):
            write_hooks(settings_path, data)

    adapter = plugin_config_dir() / "claude-hook.py"
    if adapter.exists():
        adapter.unlink()
    print("Removed Claude model-display hooks.")
    return 0


def install_pi() -> int:
    source = plugin_root() / "adapters" / "pi-model-display.ts"
    destination = pi_home() / "extensions" / "herdr-model-display.ts"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    print(f"Installed Pi extension at {destination}")
    print("Run /reload or restart Pi to activate model display.")
    return 0


def uninstall_pi() -> int:
    destination = pi_home() / "extensions" / "herdr-model-display.ts"
    if destination.exists():
        destination.unlink()
    print("Removed Pi model-display extension.")
    return 0


def install_hermes() -> int:
    source = plugin_root() / "adapters" / "hermes"
    destination = hermes_home() / "plugins" / "herdr-model-display"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    hermes = shutil.which("hermes")
    if hermes:
        result = subprocess.run(
            [hermes, "plugins", "enable", "herdr-model-display"], check=False
        )
        if result.returncode != 0:
            print(
                "Hermes plugin was copied but could not be enabled automatically.",
                file=sys.stderr,
            )
            return result.returncode
    else:
        print(
            "Hermes executable not found; enable herdr-model-display after installing Hermes."
        )
    print(f"Installed Hermes plugin at {destination}")
    print("Restart Hermes to activate model display.")
    return 0


def uninstall_hermes() -> int:
    destination = hermes_home() / "plugins" / "herdr-model-display"
    hermes = shutil.which("hermes")
    if hermes and destination.exists():
        subprocess.run(
            [hermes, "plugins", "disable", "herdr-model-display"], check=False
        )
    if destination.exists():
        shutil.rmtree(destination)
    print("Removed Hermes model-display plugin.")
    return 0


def install_all() -> int:
    results = [install_codex(), install_claude(), install_pi(), install_hermes()]
    return 0 if all(result == 0 for result in results) else 1


def uninstall_all() -> int:
    results = [
        uninstall_codex(),
        uninstall_claude(),
        uninstall_pi(),
        uninstall_hermes(),
    ]
    return 0 if all(result == 0 for result in results) else 1


def status() -> int:
    checks: list[tuple[str, bool]] = []

    codex_path = codex_home() / "hooks.json"
    codex_data = load_hooks(codex_path) if codex_path.exists() else {"hooks": {}}
    checks.append(
        (
            "Codex",
            all(
                any(
                    is_our_hook(group, CODEX_MARKER)
                    for group in codex_data["hooks"].get(event, [])
                )
                for event in CODEX_HOOK_EVENTS
            ),
        )
    )

    claude_path = claude_home() / "settings.json"
    claude_data = load_hooks(claude_path) if claude_path.exists() else {"hooks": {}}
    checks.append(
        (
            "Claude",
            all(
                any(
                    is_our_hook(group, CLAUDE_MARKER)
                    for group in claude_data["hooks"].get(event, [])
                )
                for event in CLAUDE_HOOK_EVENTS
            ),
        )
    )
    checks.append(
        ("Pi", (pi_home() / "extensions" / "herdr-model-display.ts").exists())
    )
    checks.append(
        (
            "Hermes",
            (
                hermes_home() / "plugins" / "herdr-model-display" / "plugin.yaml"
            ).exists(),
        )
    )

    for name, configured in checks:
        print(f"{name}: {'configured' if configured else 'not configured'}")
    return 0 if all(configured for _, configured in checks) else 1


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
    commands.add_parser("install-all", help="Install every supported harness adapter")
    commands.add_parser("uninstall-all", help="Remove every supported harness adapter")
    commands.add_parser("install-codex", help="Install the companion Codex hooks")
    commands.add_parser("uninstall-codex", help="Remove the companion Codex hooks")
    commands.add_parser("install-claude", help="Install the companion Claude hooks")
    commands.add_parser("uninstall-claude", help="Remove the companion Claude hooks")
    commands.add_parser("install-pi", help="Install the Pi extension")
    commands.add_parser("uninstall-pi", help="Remove the Pi extension")
    commands.add_parser("install-hermes", help="Install the Hermes plugin")
    commands.add_parser("uninstall-hermes", help="Remove the Hermes plugin")
    commands.add_parser("status", help="Check adapter installation")
    commands.add_parser("codex-hook", help="Handle a Codex hook payload from stdin")
    commands.add_parser("claude-hook", help="Handle a Claude hook payload from stdin")

    report = commands.add_parser("report", help="Report a model from another adapter")
    report.add_argument("--pane", default=os.environ.get("HERDR_PANE_ID"))
    report.add_argument("--harness", required=True)
    report.add_argument("--model", required=True)
    report.add_argument("--effort", default="")

    clear = commands.add_parser(
        "clear", help="Clear a model reported by another adapter"
    )
    clear.add_argument("--pane", default=os.environ.get("HERDR_PANE_ID"))
    clear.add_argument("--harness", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install-all":
        return install_all()
    if args.command == "uninstall-all":
        return uninstall_all()
    if args.command == "install-codex":
        return install_codex()
    if args.command == "uninstall-codex":
        return uninstall_codex()
    if args.command == "install-claude":
        return install_claude()
    if args.command == "uninstall-claude":
        return uninstall_claude()
    if args.command == "install-pi":
        return install_pi()
    if args.command == "uninstall-pi":
        return uninstall_pi()
    if args.command == "install-hermes":
        return install_hermes()
    if args.command == "uninstall-hermes":
        return uninstall_hermes()
    if args.command == "status":
        return status()
    if args.command == "codex-hook":
        return codex_hook(read_stdin_payload())
    if args.command == "claude-hook":
        return claude_hook(read_stdin_payload())
    if args.command == "report":
        if not args.pane:
            raise SystemExit("--pane or HERDR_PANE_ID is required")
        return report_model(args.pane, args.harness, args.model, args.effort)
    if args.command == "clear":
        if not args.pane:
            raise SystemExit("--pane or HERDR_PANE_ID is required")
        return clear_model(args.pane, args.harness)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
