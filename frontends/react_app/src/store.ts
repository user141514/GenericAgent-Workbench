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
): { messages: ChatMessage[]; status: RunStatus; error: string } {
  const next = [...messages];
  const last = next[next.length - 1];
  const terminal = event.kind === "done" || event.kind === "stopped" || event.kind === "error";

  if (event.kind === "chunk" || event.kind === "turn_delta" || event.kind === "done" || event.kind === "stopped") {
    if (!last || last.role !== "assistant" || !last.streaming) {
      next.push({ id: cryptoId(), role: "assistant", text: event.text, streaming: !terminal });
    } else {
      next[next.length - 1] = { ...last, text: event.text, streaming: !terminal };
    }
  }

  if (event.kind === "error") {
    if (!last || last.role !== "assistant" || !last.streaming) {
      next.push({ id: cryptoId(), role: "assistant", text: event.error || "Run failed.", streaming: false });
    } else {
      next[next.length - 1] = { ...last, text: event.error || last.text, streaming: false };
    }
    return { messages: next, status: "error", error: event.error || "Run failed." };
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
      if (event.kind === "frontier_state") {
        const snapshot = event.metadata.frontier_state;
        return {
          frontierState: isFrontierStateSnapshot(snapshot) ? snapshot : state.frontierState,
        };
      }
      const applied = applyAgentEvent(state.messages, event);
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
  setError: (error) => set({ error, status: "error" }),
  restoreConversation: (messages) =>
    set({
      messages: messages.map((message) => ({ ...message, id: cryptoId() })),
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
