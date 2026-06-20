import { create } from "zustand";
import type { AgentEvent, AppSettings, AttachmentMeta, ChatMessage, FrontierStateSnapshot, HistoryItem } from "./types";

export type RunStatus = "idle" | "running" | "stopping" | "error";

export interface AppState {
  messages: ChatMessage[];
  events: AgentEvent[];
  attachments: AttachmentMeta[];
  history: HistoryItem[];
  memory: Record<string, string>;
  frontierState: FrontierStateSnapshot | null;
  settings: AppSettings;
  runId: string;
  status: RunStatus;
  error: string;
  setRunStarted: (runId: string, userText: string) => void;
  setStopping: () => void;
  applyEvent: (event: AgentEvent) => void;
  setAttachments: (attachments: AttachmentMeta[]) => void;
  setHistory: (history: HistoryItem[]) => void;
  setMemory: (memory: Record<string, string>) => void;
  setSettings: (settings: AppSettings) => void;
  setError: (error: string) => void;
  restoreConversation: (messages: Array<Pick<ChatMessage, "role" | "text">>) => void;
  clearConversation: () => void;
  clearAttachments: () => void;
}

export function applyAgentEvent(
  messages: ChatMessage[],
  event: AgentEvent,
  currentEvents: AgentEvent[] = [],
): { messages: ChatMessage[]; status: RunStatus; error: string } {
  const next = [...messages];
  const last = next[next.length - 1];
  const terminal = event.kind === "done" || event.kind === "stopped" || event.kind === "error";
  const traceEvents = traceEventsForMessage(currentEvents, event);

  if (event.kind === "chunk") {
    if (!last || last.role !== "assistant" || !last.streaming) {
      next.push({ id: cryptoId(), role: "assistant", text: event.text, streaming: true, traceEvents });
    } else {
      next[next.length - 1] = {
        ...last,
        text: mergeChunkText(last.text, event.text),
        streaming: true,
        traceEvents: appendTraceEvent(last.traceEvents, event),
      };
    }
  } else if (event.kind === "done" || event.kind === "stopped") {
    if (!last || last.role !== "assistant" || !last.streaming) {
      next.push({ id: cryptoId(), role: "assistant", text: event.text, streaming: false, traceEvents });
    } else {
      next[next.length - 1] = {
        ...last,
        text: event.text,
        streaming: false,
        traceEvents: appendTraceEvent(last.traceEvents, event),
      };
    }
  } else if (shouldKeepTraceEvent(event) && last?.role === "assistant" && last.streaming) {
    next[next.length - 1] = { ...last, traceEvents: appendTraceEvent(last.traceEvents, event) };
  }

  if (event.kind === "error") {
    const errorText = friendlyErrorText(event.error || "Run failed.");
    if (!last || last.role !== "assistant" || !last.streaming) {
      next.push({ id: cryptoId(), role: "assistant", text: errorText, streaming: false, traceEvents });
    } else {
      next[next.length - 1] = {
        ...last,
        text: errorText || last.text,
        streaming: false,
        traceEvents: appendTraceEvent(last.traceEvents, event),
      };
    }
    return { messages: next, status: "error", error: errorText };
  }

  return { messages: next, status: terminal ? "idle" : "running", error: "" };
}

export function lastAssistantText(messages: ChatMessage[]) {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "assistant") {
      return messages[i].text;
    }
  }
  return "";
}

export function friendlyErrorText(error: string) {
  const text = error || "Run failed.";
  const lowered = text.toLowerCase();
  const looksLikeNetworkFault = [
    "connection_error",
    "connecttimeout",
    "connect timeout",
    "connection timed out",
    "timed out",
    "httpsconnectionpool",
    "max retries exceeded",
    "connection refused",
    "networkerror",
  ].some((needle) => lowered.includes(needle));
  if (looksLikeNetworkFault && !text.includes("网络连接故障")) {
    return `网络连接故障：${text}`;
  }
  return text;
}

export const useAppStore = create<AppState>((set) => ({
  messages: [],
  events: [],
  attachments: [],
  history: [],
  memory: {},
  frontierState: null,
  settings: {
    routing_mode: "auto",
    compact_assistant_history: true,
    autonomous_enabled: false,
    last_reply_time: 0,
    idle_seconds: 0,
    backend: "",
    current_key_index: 0,
    key_labels: [],
  },
  runId: "",
  status: "idle",
  error: "",
  setRunStarted: (runId, userText) =>
    set((state) => ({
      runId,
      status: "running",
      error: "",
      events: [],
      frontierState: null,
      messages: [...state.messages, { id: cryptoId(), role: "user", text: userText }],
    })),
  setStopping: () => set({ status: "stopping" }),
  applyEvent: (event) =>
    set((state) => {
      if (isStaleRunEvent(state.runId, event)) {
        return {};
      }
      if (event.kind === "frontier_state") {
        const snapshot = event.metadata.frontier_state;
        return {
          frontierState: isFrontierStateSnapshot(snapshot) ? snapshot : state.frontierState,
        };
      }
      const applied = applyAgentEvent(state.messages, event, state.events);
      return {
        messages: applied.messages,
        status: applied.status,
        error: applied.error,
        events: [...state.events, event].slice(-80),
      };
    }),
  setAttachments: (attachments) => set({ attachments }),
  setHistory: (history) => set({ history }),
  setMemory: (memory) => set({ memory }),
  setSettings: (settings) => set({ settings }),
  setError: (error) => set({ error: friendlyErrorText(error), status: "error" }),
  restoreConversation: (messages) =>
    set({
      messages: messages.map((message) => ({
        ...message,
        id: cryptoId(),
        traceEvents: message.role === "assistant" ? synthesizeTraceEvents(message.text) : undefined,
      })),
      events: [],
      frontierState: null,
      runId: "",
      status: "idle",
      error: "",
    }),
  clearConversation: () => set({ messages: [], events: [], frontierState: null, runId: "", status: "idle", error: "" }),
  clearAttachments: () => set({ attachments: [] }),
}));

function isFrontierStateSnapshot(value: unknown): value is FrontierStateSnapshot {
  return Boolean(value && typeof value === "object" && "enabled" in value);
}

function cryptoId() {
  if ("crypto" in globalThis && "randomUUID" in globalThis.crypto) {
    return globalThis.crypto.randomUUID();
  }
  return `id_${Math.random().toString(16).slice(2)}`;
}

function shouldKeepTraceEvent(event: AgentEvent) {
  return Boolean(event.turn) && event.kind !== "status" && event.kind !== "frontier_state";
}

function isStaleRunEvent(runId: string, event: AgentEvent) {
  return Boolean(runId && event.task_id && event.task_id !== runId);
}

function mergeChunkText(existing: string, chunk: string) {
  if (!existing) return chunk;
  if (!chunk) return existing;
  if (chunk.startsWith(existing)) return chunk;
  if (existing.endsWith(chunk)) return existing;
  return `${existing}${chunk}`;
}

function traceEventsForMessage(currentEvents: AgentEvent[], event: AgentEvent) {
  return [...currentEvents, event].filter(shouldKeepTraceEvent);
}

function appendTraceEvent(existing: AgentEvent[] | undefined, event: AgentEvent) {
  if (!shouldKeepTraceEvent(event)) return existing;
  return [...(existing || []), event];
}

function synthesizeTraceEvents(text: string): AgentEvent[] | undefined {
  const raw = String(text || "");
  const events: AgentEvent[] = [];
  const markerRe = /\**LLM Running \(Turn (\d+)\) \.\.\.\**/g;
  const matches = [...raw.matchAll(markerRe)];
  for (const match of matches) {
    const turn = Number(match[1] || 0);
    if (!turn) continue;
    events.push(syntheticEvent("turn_start", turn, "Recovered turn"));
  }

  for (let index = 0; index < matches.length; index += 1) {
    const match = matches[index];
    const turn = Number(match[1] || 0);
    const start = (match.index || 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index || raw.length : raw.length;
    const segment = raw.slice(start, end);
    const detail = firstTraceDetail(segment);
    if (turn && detail) {
      events.push(syntheticEvent("turn_delta", turn, detail));
    }
  }

  return events.length ? events.sort((a, b) => a.turn - b.turn) : undefined;
}

function firstTraceDetail(segment: string) {
  for (const line of String(segment || "").split(/\r?\n/)) {
    const text = line.trim();
    if (!text || text.startsWith("```")) continue;
    if (text.startsWith("Tool:")) return text;
    if (/^\[(?:Action|Status|Stdout|Stderr|Error|Info|Path Guard)\]/.test(text)) return text;
    if (/^[a-z][a-z0-9_]*\(\{.*\}\)\s*$/.test(text)) return text;
    if (text.includes("<tool_use") || text.includes("'type': 'tool_use'") || text.includes('"type": "tool_use"')) {
      return "Recovered tool call";
    }
  }
  return "";
}

function syntheticEvent(kind: AgentEvent["kind"], turn: number, text: string): AgentEvent {
  return {
    kind,
    text,
    error: "",
    source: "history",
    turn,
    task_id: "restored_history",
    metadata: { synthetic: true },
  };
}
