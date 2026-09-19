# Herdr Model Display

Display the active AI model next to its harness in the Herdr agent sidebar:

```text
codex - gpt-5.6
```

The plugin uses harness lifecycle hooks and Herdr's display-only pane metadata. It does not scrape terminal output or take over Herdr's agent lifecycle state.

## Status

- Codex: automatic model updates and cleanup
- Other harnesses: adapter API available; native adapters are planned
- Platforms: macOS and Linux
- Requirements: Herdr 0.9.0+, Python 3, and Codex hooks enabled

## Install

```sh
herdr plugin install pdalinis/herdr-disp-model
herdr plugin action invoke dev.pdalinis.model-display.setup-codex
```

Restart any running Codex sessions after setup. Codex may ask you to review and trust the newly installed hook before it runs.

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
herdr plugin action invoke dev.pdalinis.model-display.remove-codex
```

Remove the companion hook before uninstalling the plugin:

```sh
herdr plugin action invoke dev.pdalinis.model-display.remove-codex
herdr plugin uninstall dev.pdalinis.model-display
```

## Adapter interface

Additional harness adapters can call the dependency-free reporter directly:

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

Contributions for additional harness adapters are welcome.

## Development

```sh
python3 -m unittest discover -s tests -v
herdr plugin link "$PWD" --disabled
```

## How it works

Codex provides its active model slug to command hooks as the stable `model` input field. The setup action adds separate `SessionStart`, `UserPromptSubmit`, and `SessionEnd` hooks while preserving existing user hooks. The companion hook calls `herdr pane report-metadata` to update the pane's visible agent label and `$model` token.

The hook is copied into Herdr's stable plugin configuration directory, so GitHub-managed plugin reinstalls do not leave Codex pointing at a replaced checkout.

The implementation follows Herdr's [plugin](https://herdr.dev/docs/plugins/) and [pane metadata](https://herdr.dev/docs/socket-api/) APIs. Codex model detection uses the documented `model` field supplied to [Codex hooks](https://developers.openai.com/docs/hooks).

## License

MIT
