import type { FrontierStateSnapshot } from "./types";

type FrontierStatePanelProps = {
  snapshot: FrontierStateSnapshot | null;
};

type Section = {
  title: string;
  lines: string[];
  warning: boolean;
};

export function FrontierStatePanel({ snapshot }: FrontierStatePanelProps) {
  if (!snapshot?.enabled) return null;
  const sections = buildSections(snapshot);
  const warningCount = sections.filter((section) => section.warning).length;

  return (
    <details className={`frontier-panel ${warningCount ? "frontier-panel-warning" : ""}`}>
      <summary>
        <span>Frontier State</span>
        <small>{snapshot.mode || "research"}{warningCount ? ` / ${warningCount} warnings` : ""}</small>
      </summary>
      <div className="frontier-section-grid">
        {sections.map((section) => (
          <section
            key={section.title}
            className={`frontier-section ${section.warning ? "frontier-section-warning" : ""}`}
          >
            <h3>{section.title}</h3>
            <ul>
              {section.lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}

function buildSections(snapshot: FrontierStateSnapshot): Section[] {
  const intent = asRecord(snapshot.intent_state);
  const evidence = asRecord(snapshot.evidence_state);
  const strategy = asRecord(snapshot.strategy_state);
  const execution = asRecord(snapshot.execution_state);
  const synthesis = asRecord(snapshot.synthesis_state);
  const confidence = asRecord(snapshot.confidence_state);

  const synthesisWarnings = asStringList(synthesis.warnings);
  const strategyWarnings = asStringList(strategy.bad_strategy_flags);
  const unsupported = asStringList(evidence.unsupported);
  const unexecuted = asStringList(execution.unexecuted_commitments);
  const judgment = String(confidence.current_judgment || "medium");

  return [
    {
      title: "Intent",
      warning: false,
      lines: compact([
        `Task: ${String(intent.task_type || snapshot.mode || "research")}`,
        maybeLine("Goal", intent.user_goal),
        ...asStringList(intent.constraints).slice(0, 2).map((item) => `Constraint: ${item}`),
      ]),
    },
    {
      title: "Evidence",
      warning: unsupported.length > 0,
      lines: compact([
        ...asStringList(evidence.verified).slice(0, 2).map((item) => `Verified: ${item}`),
        ...asStringList(evidence.user_provided).slice(0, 2).map((item) => `User-provided: ${item}`),
        ...unsupported.slice(0, 2).map((item) => `Needs proof: ${item}`),
      ]),
    },
    {
      title: "Strategy",
      warning: strategyWarnings.length > 0,
      lines: compact([
        ...asCandidateLines(strategy.selected).slice(0, 3),
        ...strategyWarnings.slice(0, 2).map((item) => `Flag: ${item}`),
      ]),
    },
    {
      title: "Execution",
      warning: unexecuted.length > 0,
      lines: compact([
        ...executionLines(execution).slice(0, 4),
        ...unexecuted.slice(0, 2).map((item) => `Unexecuted: ${item}`),
      ]),
    },
    {
      title: "Synthesis",
      warning: synthesisWarnings.length > 0,
      lines: compact([
        `Gate: ${String(synthesis.gate_action || "pass")}`,
        ...synthesisWarnings.slice(0, 3).map((item) => `Warning: ${item}`),
        ...asStringList(synthesis.missing_sections).slice(0, 2).map((item) => `Missing: ${item}`),
      ]),
    },
    {
      title: "Confidence",
      warning: judgment === "low",
      lines: compact([
        `Judgment: ${judgment}`,
        maybeLine("Score", confidence.workflow_score),
        ...asStringList(confidence.next_verification).slice(0, 3).map((item) => `Next: ${item}`),
      ]),
    },
  ].map((section) => ({
    ...section,
    lines: section.lines.length ? section.lines : ["No state yet."],
  }));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      return String(record.name || record.commitment || record.reason || JSON.stringify(record));
    }
    return String(item);
  }).filter(Boolean);
}

function asCandidateLines(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (!item || typeof item !== "object") return String(item);
    const record = item as Record<string, unknown>;
    const name = String(record.name || "Candidate");
    const summary = record.summary ? `: ${String(record.summary)}` : "";
    return `${name}${summary}`;
  });
}

function executionLines(execution: Record<string, unknown>) {
  const lines: string[] = [];
  const actions = Array.isArray(execution.actual_actions) ? execution.actual_actions : [];
  const delta = asRecord(execution.state_delta);
  if (actions.length) lines.push(`${actions.length} tool action(s) recorded.`);
  for (const [key, value] of Object.entries(delta)) {
    if (Array.isArray(value) ? value.length > 0 : Boolean(value)) {
      lines.push(`Delta: ${key}`);
    }
  }
  if (!lines.length) lines.push("No tool-backed state delta yet.");
  return lines;
}

function maybeLine(label: string, value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  return `${label}: ${String(value)}`;
}

function compact(lines: string[]) {
  return lines.map((line) => line.trim()).filter(Boolean);
}
