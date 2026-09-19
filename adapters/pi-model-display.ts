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

function report(model: unknown): void {
  if (!model || typeof model !== "object") return;
  const id = (model as { id?: unknown }).id;
  if (typeof id !== "string" || !id.trim()) return;
  const value = id.trim();
  run([
    "pane", "report-metadata", paneId!,
    "--source", source,
    "--agent", "pi",
    "--display-agent", `pi - ${value}`,
    "--token", `model=${value}`,
  ]);
}

function clear(): void {
  run([
    "pane", "report-metadata", paneId!,
    "--source", source,
    "--agent", "pi",
    "--clear-display-agent",
    "--clear-token", "model",
  ]);
}

export default function modelDisplay(pi: any): void {
  pi.on("session_start", (_event: unknown, ctx: any) => {
    if (ctx?.mode === "tui") report(ctx.model);
  });
  pi.on("session_switch", (_event: unknown, ctx: any) => {
    if (ctx?.mode === "tui") report(ctx.model);
  });
  pi.on("model_select", (event: any, ctx: any) => {
    if (ctx?.mode === "tui") report(event?.model ?? ctx.model);
  });
  pi.on("session_shutdown", clear);
}
