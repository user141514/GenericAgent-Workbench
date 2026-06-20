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
const INTERNAL_TAG_BLOCK_RE = /<\s*(?:thinking|summary|tool_use|tool_result|tool_call)\b[^>]*>[\s\S]*?<\s*\/\s*(?:thinking|summary|tool_use|tool_result|tool_call)\s*>\s*/gi;
const FUNCTION_TOOL_CALL_RE = /^[a-z][a-z0-9_]*\(\{.*\}\)\s*$/;
const PYTHON_INTERNAL_BLOCK_RE = /^\s*(?:\[\s*)?\{.*(?:['"]type['"]\s*:\s*['"](?:thinking|tool_use|tool_call)['"]).*\}\s*(?:\])?\s*$/;
const FUNCTION_TOOL_CALL_START_RE = /^[a-z][a-z0-9_]*\s*\(\s*\{/i;
const INTERNAL_TYPE_RE = /['"]type['"]\s*:\s*['"](?:thinking|tool_use|tool_call)['"]/i;
const INTERNAL_TAG_START_RE = /<\s*(thinking|summary|tool_use|tool_result|tool_call)\b/i;
const RUNTIME_LABEL_RE = /^\[(?:Action|Status|Stdout|Stderr|Error|Path Guard|Info)\]/;
const TOOL_ARGS_LINE_RE = /^Tool:\s*`[^`]+`\s+args:/;

export function renderMessageText(text: string, options: RenderMessageTextOptions) {
  const visible = options.role === "assistant"
    ? cleanAssistantReplyText(text, options.latestTraceTurn || 0)
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
  return cleanAssistantReplyText(text, 0);
}

function cleanAssistantReplyText(text: string, latestTraceTurn = 0) {
  const visibleTail = stripLeadingInternalTranscript(stripLegacyTurnResidue(text, latestTraceTurn));
  return normalizeCopyText(
    visibleTail
      .replace(INTERNAL_TAG_BLOCK_RE, "")
      .replace(SUMMARY_TAG_RE, "")
      .replace(TOOL_CALL_BLOCK_RE, "")
      .replace(RUNTIME_FENCE_BLOCK_RE, "")
      .replace(RUNTIME_LINE_RE, "")
      .replace(TURN_MARKER_RE, ""),
  );
}

function stripLeadingInternalTranscript(text: string) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  let sawInternal = false;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (FUNCTION_TOOL_CALL_RE.test(line)) {
      sawInternal = true;
      index += 1;
      continue;
    }

    if (FUNCTION_TOOL_CALL_START_RE.test(line)) {
      sawInternal = true;
      index = skipBalancedCall(lines, index);
      continue;
    }

    const pythonBlockEnd = skipPythonInternalBlock(lines, index);
    if (pythonBlockEnd > index) {
      sawInternal = true;
      index = pythonBlockEnd;
      continue;
    }

    if (isRuntimeFenceAt(lines, index)) {
      sawInternal = true;
      index = skipFence(lines, index);
      continue;
    }

    if (line.startsWith("<") && INTERNAL_TAG_START_RE.test(line)) {
      sawInternal = true;
      index = skipInternalTagBlock(lines, index);
      continue;
    }

    if (TOOL_ARGS_LINE_RE.test(line)) {
      sawInternal = true;
      index = skipLegacyToolBlock(lines, index);
      continue;
    }

    if (RUNTIME_LABEL_RE.test(line)) {
      sawInternal = true;
      index += 1;
      continue;
    }

    if (line === "---" && sawInternal) {
      index += 1;
      continue;
    }

    break;
  }

  return sawInternal ? lines.slice(index).join("\n") : text;
}

function isRuntimeFenceAt(lines: string[], index: number) {
  if (!lines[index]?.trim().startsWith("```")) return false;
  const next = lines[index + 1]?.trim() || "";
  return RUNTIME_LABEL_RE.test(next);
}

function skipFence(lines: string[], index: number) {
  let cursor = index + 1;
  while (cursor < lines.length) {
    if (lines[cursor].trim().startsWith("```")) {
      return cursor + 1;
    }
    cursor += 1;
  }
  return lines.length;
}

function skipLegacyToolBlock(lines: string[], index: number) {
  let cursor = index + 1;
  while (cursor < lines.length && !lines[cursor].trim()) {
    cursor += 1;
  }
  if (lines[cursor]?.trim().startsWith("```")) {
    return skipFence(lines, cursor);
  }

  const literalEnd = skipBalancedLiteral(lines, cursor);
  if (literalEnd > cursor) return literalEnd;
  return cursor;
}

function skipInternalTagBlock(lines: string[], index: number) {
  const first = lines[index].trim();
  const match = first.match(INTERNAL_TAG_START_RE);
  if (!match) return index + 1;
  const tag = match[1];
  const closeRe = new RegExp(`<\\s*\\/\\s*${tag}\\s*>`, "i");
  if (closeRe.test(first)) return index + 1;

  let cursor = index + 1;
  while (cursor < lines.length) {
    if (closeRe.test(lines[cursor])) return cursor + 1;
    cursor += 1;
  }
  return index + 1;
}

function skipPythonInternalBlock(lines: string[], index: number) {
  const line = lines[index].trim();
  if (PYTHON_INTERNAL_BLOCK_RE.test(line)) return index + 1;
  if (!line.startsWith("[") && !line.startsWith("{")) return index;

  const literalEnd = skipBalancedLiteral(lines, index);
  if (literalEnd <= index) return index;

  const block = lines.slice(index, literalEnd).join("\n");
  return INTERNAL_TYPE_RE.test(block) ? literalEnd : index;
}

function skipBalancedCall(lines: string[], index: number) {
  let depth = 0;
  let quote = "";
  let escaped = false;
  let started = false;

  for (let cursor = index; cursor < lines.length; cursor += 1) {
    const line = lines[cursor];
    for (const char of line) {
      if (quote) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === quote) {
          quote = "";
        }
        continue;
      }

      if (char === "\"" || char === "'" || char === "`") {
        quote = char;
      } else if (char === "(") {
        depth += 1;
        started = true;
      } else if (char === ")" && started) {
        depth -= 1;
        if (depth <= 0) return cursor + 1;
      }
    }

    if (cursor > index && /^\s*\}\)\s*;?\s*$/.test(line)) {
      return cursor + 1;
    }
  }

  return index + 1;
}

function skipBalancedLiteral(lines: string[], index: number) {
  if (index >= lines.length) return index;

  const stack: string[] = [];
  let quote = "";
  let escaped = false;
  let started = false;

  for (let cursor = index; cursor < lines.length; cursor += 1) {
    const line = lines[cursor];
    for (const char of line) {
      if (quote) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === quote) {
          quote = "";
        }
        continue;
      }

      if (char === "\"" || char === "'") {
        quote = char;
      } else if (char === "{" || char === "[") {
        stack.push(char === "{" ? "}" : "]");
        started = true;
      } else if (started && stack[stack.length - 1] === char) {
        stack.pop();
        if (stack.length === 0) return cursor + 1;
      }
    }
  }

  return index;
}

function normalizeCopyText(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/^\s*---+\s*/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
