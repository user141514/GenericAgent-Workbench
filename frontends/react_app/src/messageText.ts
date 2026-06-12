type RenderMessageTextOptions = {
  role: string;
  compact: boolean;
  streaming?: boolean;
  latestTraceTurn?: number;
};

const TURN_MARKER_RE = /(\**LLM Running \(Turn (\d+)\) \.\.\.\*\*)/g;

export function renderMessageText(text: string, options: RenderMessageTextOptions) {
  const visible = options.role === "assistant"
    ? stripLegacyTurnResidue(text, options.latestTraceTurn || 0)
    : text;

  if (!visible && options.streaming && options.role !== "assistant") return "Thinking...";
  if (options.role !== "assistant" || !options.compact || visible.length <= 1800) return visible;
  return `${visible.slice(0, 1800)}\n\n[已压缩显示，复制按钮仍复制最后完整回复]`;
}

export function stripLegacyTurnResidue(text: string, latestTraceTurn = 0) {
  const raw = String(text || "");
  const matches = [...raw.matchAll(TURN_MARKER_RE)];
  if (matches.length === 0) return raw;

  const last = matches[matches.length - 1];
  const marker = last[1] || "";
  const markerTurn = Number(last[2] || 0);
  if (latestTraceTurn > 0 && markerTurn < latestTraceTurn) {
    return "";
  }

  const markerStart = last.index || 0;
  return raw.slice(markerStart + marker.length).trimStart();
}
