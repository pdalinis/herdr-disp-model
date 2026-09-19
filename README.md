# Herdr Model Display

Display the active AI model next to its harness in the Herdr agent sidebar:

```text
codex - gpt-5.6
claude - claude-opus-5
pi - claude-sonnet-4-6
hermes - gpt-5.4
```

The plugin uses harness lifecycle hooks and Herdr's display-only pane metadata. It does not scrape terminal output or take over Herdr's agent lifecycle state.

## Status

- Codex: automatic session and model updates
- Claude: automatic session and live model-switch updates
- Pi: automatic session and live model-switch updates
- Hermes: automatic per-turn model updates
- Platforms: macOS and Linux
- Requirements: Herdr 0.9.0+ and Python 3

## Install

```sh
herdr plugin install pdalinis/herdr-disp-model
herdr plugin action invoke dev.pdalinis.model-display.setup-all
```

Restart running harness sessions after setup. Pi can instead load its adapter immediately with `/reload`. Codex may ask you to review and trust its newly installed hook before it runs.

Claude model-switch tracking uses `PostModelSwitch`, available in Claude Code 2.1.251 and newer. On older Claude versions, the adapter reports the initial model when `SessionStart` provides it but cannot follow `/model` changes.

The default Herdr sidebar works without additional configuration because the plugin reports a display name such as `codex - gpt-5.6`.

## Custom sidebar layout

The plugin also reports the model as a `$model` token. To control placement yourself, add it after `agent` in `~/.config/herdr/config.toml`:

```toml
[ui.sidebar.agents]
rows = [
  ["state_icon", "machine", "workspace", "tab"],
  ["agent", "$model"],
]
```

Herdr separates tokens with `·`, producing `codex · gpt-5.6`. Reload the configuration with:

```sh
herdr server reload-config
```

## Check or remove setup

```sh
herdr plugin action invoke dev.pdalinis.model-display.status
herdr plugin action invoke dev.pdalinis.model-display.remove-all
```

Remove the companion hook before uninstalling the plugin:

```sh
herdr plugin action invoke dev.pdalinis.model-display.remove-all
herdr plugin uninstall dev.pdalinis.model-display
```

## Adapter interface

Unsupported harness adapters can call the dependency-free reporter directly:

```sh
python3 src/model_display.py report \
  --pane "$HERDR_PANE_ID" \
  --harness claude \
  --model opus
```

Clear stale metadata when the harness session ends:

```sh
python3 src/model_display.py clear \
  --pane "$HERDR_PANE_ID" \
  --harness claude
```

Each supported harness can also be managed independently with `setup-codex`, `setup-claude`, `setup-pi`, `setup-hermes`, and the corresponding `remove-*` action.

## Development

```sh
python3 -m unittest discover -s tests -v
herdr plugin link "$PWD" --disabled
```

## How it works

Each adapter uses its harness's native model signal:

- Codex provides `model` to command hooks.
- Claude provides `model` at `SessionStart` and `to_model` at `PostModelSwitch`.
- Pi exposes `ctx.model` and the `model_select` extension event.
- Hermes provides `model` to its `pre_llm_call` Python plugin hook.

The adapters call `herdr pane report-metadata` to update the pane's visible agent label and `$model` token without taking over lifecycle state. Setup preserves existing Codex and Claude hooks.

The command-hook adapters are copied into Herdr's stable plugin configuration directory, so GitHub-managed plugin reinstalls do not leave Codex or Claude pointing at a replaced checkout.

The implementation follows Herdr's [plugin](https://herdr.dev/docs/plugins/) and [pane metadata](https://herdr.dev/docs/socket-api/) APIs. See the native [Codex hooks](https://developers.openai.com/docs/hooks), [Claude hooks](https://code.claude.com/docs/en/hooks), [Pi extensions](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md), and [Hermes hooks](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/hooks.md) documentation.

## License

MIT
