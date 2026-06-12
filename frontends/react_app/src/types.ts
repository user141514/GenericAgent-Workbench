export type AgentEventKind =
  | "chunk"
  | "done"
  | "status"
  | "turn_start"
  | "turn_end"
  | "turn_delta"
  | "frontier_state"
  | "stopped"
  | "error";

export interface AgentEvent {
  kind: AgentEventKind;
  text: string;
  source: string;
  turn: number;
  task_id: string;
  error: string;
  metadata: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  streaming?: boolean;
}

export interface FrontierStateSnapshot {
  enabled: boolean;
  mode: string;
  run_id: string;
  intent_state: Record<string, unknown>;
  evidence_state: Record<string, unknown>;
  strategy_state: Record<string, unknown>;
  execution_state: Record<string, unknown>;
  synthesis_state: Record<string, unknown>;
  confidence_state: Record<string, unknown>;
}

export interface AttachmentMeta {
  id: string;
  name: string;
  size_label: string;
  kind: string;
  status: string;
  warning?: string;
  preview_text?: string;
  distilled_text?: string;
}

export interface HistoryItem {
  filepath: string;
  filename: string;
  mtime_str: string;
  size_kb: number;
  title: string;
}

export type RoutingMode = "auto" | "classic" | "multi_agent";

export interface AppSettings {
  routing_mode: RoutingMode;
  compact_assistant_history: boolean;
  autonomous_enabled: boolean;
  last_reply_time: number;
  idle_seconds: number;
  backend: string;
  current_key_index: number;
  key_labels: string[];
}
