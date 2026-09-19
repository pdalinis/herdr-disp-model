"""Hermes adapter for Herdr Model Display."""

from __future__ import annotations

import os
import shutil
import subprocess


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


def _report(*, model: str = "", **_kwargs) -> None:
    if not isinstance(model, str) or not model.strip():
        return
    value = model.strip()
    for prefix in ("openai/", "anthropic/", "google/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
            break
    _run(
        [
            "--source",
            "herdr-model-display:hermes",
            "--agent",
            "hermes",
            "--display-agent",
            f"hermes - {value}",
            "--token",
            f"model={value}",
        ]
    )


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
        ]
    )


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", _report)
    ctx.register_hook("on_session_end", _clear)
