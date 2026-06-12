// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FrontierStatePanel } from "./FrontierStatePanel";
import type { FrontierStateSnapshot } from "./types";

function snapshot(overrides: Partial<FrontierStateSnapshot> = {}): FrontierStateSnapshot {
  return {
    enabled: true,
    mode: "research",
    run_id: "run_1",
    intent_state: { task_type: "research_frontier", user_goal: "Improve research workflow." },
    evidence_state: { user_provided: ["current user request"], unsupported: [] },
    strategy_state: {
      selected: [{ name: "Counter-Claim", summary: "Check the strongest opposite claim." }],
      bad_strategy_flags: [],
    },
    execution_state: { state_delta: {}, actual_actions: [], unexecuted_commitments: [] },
    synthesis_state: { gate_action: "pass", warnings: [], missing_sections: [] },
    confidence_state: { current_judgment: "medium", next_verification: ["Run a small kill test."] },
    ...overrides,
  };
}

describe("FrontierStatePanel", () => {
  it("renders collapsed by default and expands on click", () => {
    const { container } = render(<FrontierStatePanel snapshot={snapshot()} />);
    const details = container.querySelector("details");

    expect(details?.open).toBe(false);
    fireEvent.click(screen.getByText("Frontier State"));
    expect(details?.open).toBe(true);
    expect(screen.getByText("Intent")).toBeTruthy();
  });

  it("marks warning sections", () => {
    const { container } = render(
      <FrontierStatePanel
        snapshot={snapshot({
          synthesis_state: {
            gate_action: "review_warn",
            warnings: ["missing_counterevidence_for_strong_claim"],
            missing_sections: ["Strong Counterevidence Check"],
          },
        })}
      />,
    );

    expect(container.querySelector(".frontier-section-warning")).toBeTruthy();
    expect(screen.getByText("research / 1 warnings")).toBeTruthy();
  });
});
