"""Hermes adapter for Herdr Model Display."""

from __future__ import annotations

import os
import shutil
import subprocess


_EFFORT_ABBREVIATIONS = {
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


def _herdr() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def _run(args: list[str]) -> None:
    pane_id = os.environ.get("HERDR_PANE_ID", "").strip()
    if not pane_id:
        return
    try:
        subprocess.Popen(
            [_herdr(), "pane", "report-metadata", pane_id, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def _compact_effort(effort) -> str:
    if not isinstance(effort, str):
        return ""
    value = effort.strip().lower()
    return _EFFORT_ABBREVIATIONS.get(value, value[:6]) if value else ""


def _request_effort(request) -> str:
    if not isinstance(request, dict):
        return ""
    direct = request.get("reasoning_effort")
    if isinstance(direct, str):
        return direct
    for container_name in ("reasoning", "output_config"):
        container = request.get(container_name)
        if isinstance(container, dict) and isinstance(container.get("effort"), str):
            return container["effort"]
    extra_body = request.get("extra_body")
    if isinstance(extra_body, dict):
        reasoning = extra_body.get("reasoning")
        if isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), str):
            return reasoning["effort"]
    return ""


def _report(*, model: str = "", effort: str = "", **_kwargs) -> None:
    if not isinstance(model, str) or not model.strip():
        return
    value = model.strip()
    for prefix in ("openai/", "anthropic/", "google/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
            break
    compact_effort = _compact_effort(effort)
    label = f"hermes - {value}"
    if compact_effort:
        label += f" - {compact_effort}"
    args = [
        "--source",
        "herdr-model-display:hermes",
        "--agent",
        "hermes",
        "--display-agent",
        label,
        "--token",
        f"model={value}",
    ]
    if compact_effort:
        args.extend(["--token", f"effort={compact_effort}"])
    else:
        args.extend(["--clear-token", "effort"])
    _run(args)


def _report_request(*, model: str = "", request=None, **_kwargs) -> None:
    _report(model=model, effort=_request_effort(request))


def _clear(**_kwargs) -> None:
    _run(
        [
            "--source",
            "herdr-model-display:hermes",
            "--agent",
            "hermes",
            "--clear-display-agent",
            "--clear-token",
            "model",
            "--clear-token",
            "effort",
        ]
    )


def register(ctx) -> None:
    ctx.register_hook("pre_api_request", _report_request)
    ctx.register_hook("on_session_end", _clear)
