import type { AgentEvent } from "./types";

export function thinkingMapForEvents(events: AgentEvent[]) {
  const buffers = new Map<number, string>();
  for (const event of events) {
    if (event.kind !== "thinking_block" || !event.text) continue;
    buffers.set(event.turn, `${buffers.get(event.turn) || ""}${event.text}`);
  }

  const map = new Map<number, string[]>();
  for (const [turn, text] of buffers.entries()) {
    const segments = thinkingSegments(text);
    if (segments.length) map.set(turn, segments);
  }
  return map;
}

function thinkingSegments(text: string) {
  const normalized = text
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\u0000/g, "")
    .trim();
  if (!normalized) return [];

  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((part) => part.replace(/[ \t]+\n/g, "\n").trim())
    .filter(Boolean);

  const segments = paragraphs.flatMap((paragraph) => splitLongThinkingSegment(paragraph));
  return limitSegments(segments);
}

function splitLongThinkingSegment(text: string) {
  const maxChars = 900;
  if (text.length <= maxChars) return [text];

  const sentences = text.match(/[^。！？!?；;]+[。！？!?；;]?/g) || [];
  if (sentences.length <= 1) {
    const chunks = [];
    for (let index = 0; index < text.length; index += maxChars) {
      chunks.push(text.slice(index, index + maxChars));
    }
    return chunks;
  }

  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && current.length + sentence.length > maxChars) {
      chunks.push(current.trim());
      current = "";
    }
    current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function limitSegments(segments: string[]) {
  const maxSegments = 6;
  if (segments.length <= maxSegments) return segments;
  return [
    ...segments.slice(0, maxSegments - 1),
    segments.slice(maxSegments - 1).join("\n\n"),
  ];
}

export function maxTraceTurn(events: AgentEvent[]) {
  return events.reduce(
    (maxTurn, event) => (event.kind === "status" ? maxTurn : Math.max(maxTurn, event.turn || 0)),
    0,
  );
}

export function hasVisibleTurnTrace(events: AgentEvent[]) {
  return events.some((event) => event.turn > 0 && event.kind !== "status");
}
