import type {
  AgentEvent,
  AppSettings,
  AttachmentMeta,
  ChatMessage,
  HistoryItem,
  RoutingMode,
} from "./types";

export const API_BASE =
  (import.meta.env.VITE_AGENT_API_BASE as string | undefined) || "http://127.0.0.1:8765";

export async function createRun(query: string, attachments: AttachmentMeta[], routingMode: RoutingMode = "auto") {
  const response = await fetch(`${API_BASE}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, attachments, routing_mode: routingMode }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { run_id: string; status: string };
}

export function streamRunEvents(
  runId: string,
  onEvent: (event: AgentEvent) => void,
  onError: (error: Error) => void,
) {
  const source = new EventSource(`${API_BASE}/api/runs/${runId}/events`);
  source.addEventListener("agent", (message) => {
    const event = JSON.parse((message as MessageEvent).data) as AgentEvent;
    onEvent(event);
    if (event.kind === "done" || event.kind === "stopped" || event.kind === "error") {
      source.close();
    }
  });
  source.onerror = () => {
    source.close();
    onError(new Error("SSE connection failed"));
  };
  return source;
}

export async function stopRun(runId: string) {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/stop`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ run_id: string; status: string }>;
}

export async function fetchSettings() {
  const response = await fetch(`${API_BASE}/api/settings`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as AppSettings;
}

export async function updateSettings(patch: Partial<Pick<AppSettings, "routing_mode" | "compact_assistant_history" | "autonomous_enabled">>) {
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as AppSettings;
}

export async function resetConversation() {
  const response = await fetch(`${API_BASE}/api/actions/new-chat`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ ok: boolean }>;
}

export async function switchKey(index: number) {
  const response = await fetch(`${API_BASE}/api/actions/switch-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ ok: boolean; backend: string; settings: AppSettings }>;
}

export async function reinjectTools() {
  const response = await fetch(`${API_BASE}/api/actions/reinject-tools`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ ok: boolean; injected: number; tools_injected: boolean }>;
}

export async function triggerAutonomous(mode: "manual" | "idle" = "manual") {
  const response = await fetch(`${API_BASE}/api/autonomous/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { run_id: string; status: string };
}

export async function uploadFiles(files: File[]) {
  const payload = {
    files: await Promise.all(
      files.map(async (file) => ({
        name: file.name,
        mime_type: file.type,
        data_base64: await fileToBase64(file),
      })),
    ),
  };
  const response = await fetch(`${API_BASE}/api/attachments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { attachments: AttachmentMeta[] };
}

export async function fetchHistory() {
  const response = await fetch(`${API_BASE}/api/history`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { items: HistoryItem[] };
}

export async function restoreHistory(filename: string) {
  const response = await fetch(`${API_BASE}/api/history/${encodeURIComponent(filename)}/restore`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as {
    item: HistoryItem;
    messages: Array<Pick<ChatMessage, "role" | "text">>;
    count: number;
    fmt_type: string;
  };
}

export async function distillDeleteHistory(filename: string) {
  const response = await fetch(`${API_BASE}/api/history/${encodeURIComponent(filename)}/distill-delete`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as {
    ok: boolean;
    deleted: boolean;
    filename: string;
    summary?: { title?: string; rounds?: number };
    save_result?: { status?: string; path?: string; msg?: string };
  };
}

export async function fetchMemory() {
  const response = await fetch(`${API_BASE}/api/memory`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { items: Record<string, string> };
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.readAsDataURL(file);
  });
}
