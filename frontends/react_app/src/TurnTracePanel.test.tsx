// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TurnTraceList } from "./TurnTracePanel";
import type { AgentEvent } from "./types";

function event(kind: AgentEvent["kind"], turn: number, text = ""): AgentEvent {
  return {
    kind,
    text,
    error: "",
    source: "agent",
    turn,
    task_id: "run_1",
    metadata: {},
  };
}

describe("TurnTraceList", () => {
  it("renders collapsed one-line turn cards that expand on click", () => {
    render(
      <TurnTraceList
        events={[
          event("turn_start", 1),
          event("chunk", 1, "first answer"),
          event("turn_end", 1),
          event("turn_start", 2),
          event("chunk", 2, "second answer"),
        ]}
      />,
    );

    const summaries = screen.getAllByText(/LLM .* \(Turn \d\) \.\.\./);
    expect(summaries).toHaveLength(2);

    const firstCard = summaries[0].closest("details");
    expect(firstCard?.hasAttribute("open")).toBe(false);

    fireEvent.click(summaries[0]);

    expect(firstCard?.hasAttribute("open")).toBe(true);
    expect(screen.queryByText("status")).toBeNull();
    expect(screen.queryByText("Turn trace")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy last reply" })).toBeNull();
  });

  it("renders nothing when no turns exist", () => {
    const { container } = render(<TurnTraceList events={[]} />);

    expect(container.textContent).toBe("");
  });

  it("renders thinking chain inside turn cards when thinkingByTurn is provided", () => {
    const thinkingByTurn = new Map<number, string[]>();
    thinkingByTurn.set(1, [
      "Analyzing the codebase structure",
      "Identifying relevant files",
    ]);

    render(
      <TurnTraceList
        events={[
          event("turn_start", 1),
          event("thinking_block" as AgentEvent["kind"], 1, "Analyzing the codebase structure"),
          event("thinking_block" as AgentEvent["kind"], 1, "Identifying relevant files"),
          event("turn_end", 1),
          event("turn_start", 2),
        ]}
        thinkingByTurn={thinkingByTurn}
      />,
    );

    // Turn 1 card shows collapsed thinking
    expect(screen.getByText("💭 思考过程 (2 steps)")).toBeTruthy();
  });
});
