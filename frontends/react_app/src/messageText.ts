type RenderMessageTextOptions = {
  role: string;
  compact: boolean;
  streaming?: boolean;
  latestTraceTurn?: number;
};

const TURN_MARKER_RE = /(\**LLM Running \(Turn (\d+)\) \.\.\.\*\*)/g;
const TOOL_CALL_BLOCK_RE = /^Tool:\s*`[^`]+`\s+args:\s*\n`{3,}[^\n]*\n[\s\S]*?\n`{3,}\s*/gm;
const RUNTIME_FENCE_BLOCK_RE = /^`{3,}\s*\n\[(?:Action|Status|Stdout|Stderr|Error|Path Guard|Info)\][\s\S]*?\n`{3,}\s*/gm;
const RUNTIME_LINE_RE = /^\[(?:Action|Status|Stdout|Stderr|Error|Path Guard|Info)\].*$/gm;
const SUMMARY_TAG_RE = /<summary>[\s\S]*?<\/summary>/gi;

export function renderMessageText(text: string, options: RenderMessageTextOptions) {
  const visible = options.role === "assistant"
    ? stripLegacyTurnResidue(text, options.latestTraceTurn || 0)
    : text;

  if (!visible && options.streaming && options.role !== "assistant") return "Thinking...";
  return visible;
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

export function copyableMessageText(text: string) {
  const visibleTail = stripLegacyTurnResidue(text, 0);
  return normalizeCopyText(
    visibleTail
      .replace(SUMMARY_TAG_RE, "")
      .replace(TOOL_CALL_BLOCK_RE, "")
      .replace(RUNTIME_FENCE_BLOCK_RE, "")
      .replace(RUNTIME_LINE_RE, "")
      .replace(TURN_MARKER_RE, ""),
  );
}

function normalizeCopyText(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/^\s*---+\s*/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
