// Herdr Model Display adapter for Pi.
import { spawn } from "node:child_process";

const paneId = process.env.HERDR_PANE_ID;
const herdr = process.env.HERDR_BIN_PATH || "herdr";
const source = "herdr-model-display:pi";

function run(args: string[]): void {
  if (!paneId) return;
  const child = spawn(herdr, args, {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

function abbreviateEffort(effort: unknown): string {
  if (typeof effort !== "string") return "";
  const value = effort.trim().toLowerCase();
  const abbreviations: Record<string, string> = {
    none: "off", off: "off", minimal: "min", min: "min", low: "low",
    medium: "med", med: "med", high: "high", xhigh: "xh",
    "extra-high": "xh", extra_high: "xh", max: "max", ultra: "ult",
    auto: "auto", default: "auto",
  };
  return abbreviations[value] ?? value.slice(0, 6);
}

function report(model: unknown, effort: unknown): void {
  if (!model || typeof model !== "object") return;
  const id = (model as { id?: unknown }).id;
  if (typeof id !== "string" || !id.trim()) return;
  const value = id.trim();
  const compactEffort = abbreviateEffort(effort);
  const args = [
    "pane", "report-metadata", paneId!,
    "--source", source,
    "--agent", "pi",
    "--display-agent", `pi - ${value}${compactEffort ? ` - ${compactEffort}` : ""}`,
    "--token", `model=${value}`,
  ];
  args.push(
    compactEffort ? "--token" : "--clear-token",
    compactEffort ? `effort=${compactEffort}` : "effort",
  );
  run(args);
}

function clear(): void {
  run([
    "pane", "report-metadata", paneId!,
    "--source", source,
    "--agent", "pi",
    "--clear-display-agent",
    "--clear-token", "model",
    "--clear-token", "effort",
  ]);
}

export default function modelDisplay(pi: any): void {
  pi.on("session_start", (_event: unknown, ctx: any) => {
    if (ctx?.mode === "tui") report(ctx.model, ctx.thinkingLevel);
  });
  pi.on("session_switch", (_event: unknown, ctx: any) => {
    if (ctx?.mode === "tui") report(ctx.model, ctx.thinkingLevel);
  });
  pi.on("model_select", (event: any, ctx: any) => {
    if (ctx?.mode === "tui") report(event?.model ?? ctx.model, ctx.thinkingLevel);
  });
  pi.on("thinking_level_select", (event: any, ctx: any) => {
    if (ctx?.mode === "tui") report(ctx.model, event?.level ?? ctx.thinkingLevel);
  });
  pi.on("session_shutdown", clear);
}
