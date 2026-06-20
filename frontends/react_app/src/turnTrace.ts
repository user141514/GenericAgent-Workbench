import type { AgentEvent } from "./types";

export type TurnTraceEntry = {
  kind: AgentEvent["kind"];
  label: string;
  text: string;
};

export type TurnSummary = {
  turn: number;
  state: "running" | "done" | "stopped" | "error";
  text: string;
  chunks: number;
  deltas: number;
  entries: TurnTraceEntry[];
};

const MAX_DETAIL_LINES = 8;

export function buildTurnSummaries(events: AgentEvent[]): TurnSummary[] {
  const byTurn = new Map<number, TurnSummary>();
  for (const event of events) {
    if (!event.turn) continue;
    const current = byTurn.get(event.turn) || {
      turn: event.turn,
      state: "running",
      text: "",
      chunks: 0,
      deltas: 0,
      entries: [],
    };

    if (event.kind === "error") {
      current.state = "error";
    } else if (event.kind === "stopped") {
      current.state = "stopped";
    } else if (event.kind === "turn_end" || event.kind === "done") {
      current.state = "done";
    }

    if (event.kind === "turn_delta") {
      current.deltas += 1;
    }
    if (event.kind === "chunk") {
      current.chunks += 1;
    }

    const text = summarizeEventText(event.error || event.text);
    if (event.kind !== "status" && event.kind !== "thinking_block" && text) {
      current.text = text;
      current.entries = [
        ...current.entries,
        { kind: event.kind, label: labelForEvent(event), text },
      ].slice(-MAX_DETAIL_LINES);
    } else if (event.kind === "turn_start") {
      if (!current.text) current.text = "开始执行";
      current.entries = [
        ...current.entries,
        { kind: event.kind, label: labelForEvent(event), text: "开始执行" },
      ].slice(-MAX_DETAIL_LINES);
    }

    byTurn.set(event.turn, current);
  }
  return [...byTurn.values()].sort((a, b) => a.turn - b.turn);
}

function summarizeEventText(text: string) {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "";
  return clean.length > 110 ? `${clean.slice(0, 110)}...` : clean;
}

export function labelForTurnState(state: TurnSummary["state"]) {
  if (state === "done") return "LLM Done";
  if (state === "stopped") return "LLM Stopped";
  if (state === "error") return "LLM Error";
  return "LLM Running";
}

function labelForEvent(event: AgentEvent) {
  if (event.kind === "turn_start") return "start";
  if (event.kind === "turn_end") return "end";
  if (event.kind === "turn_delta") return "update";
  if (event.kind === "chunk") return "output";
  if (event.kind === "done") return "done";
  if (event.kind === "stopped") return "stopped";
  if (event.kind === "error") return "error";
  return event.kind;
}
