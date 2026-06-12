import { describe, expect, it } from "vitest";
import { buildTurnSummaries } from "./turnTrace";
import type { AgentEvent } from "./types";

function event(kind: AgentEvent["kind"], turn: number, text = "", error = ""): AgentEvent {
  return {
    kind,
    text,
    error,
    source: "agent",
    turn,
    task_id: "run_1",
    metadata: {},
  };
}

describe("buildTurnSummaries", () => {
  it("folds noisy events into one row per turn", () => {
    const turns = buildTurnSummaries([
      event("status", 0, "waiting"),
      event("turn_start", 1),
      event("status", 0, "waiting"),
      event("turn_delta", 1, "[阶段] 经典执行中..."),
      event("chunk", 1, "partial answer"),
      event("turn_end", 1),
      event("turn_start", 2),
      event("chunk", 2, "second answer"),
    ]);

    expect(turns).toHaveLength(2);
    expect(turns[0]).toMatchObject({
      turn: 1,
      state: "done",
      chunks: 1,
      deltas: 1,
      text: "partial answer",
    });
    expect(turns[1]).toMatchObject({
      turn: 2,
      state: "running",
      chunks: 1,
      text: "second answer",
    });
  });

  it("keeps expandable detail lines compact and skips heartbeat status", () => {
    const turns = buildTurnSummaries([
      event("turn_start", 1),
      event("status", 1, "waiting"),
      event("chunk", 1, "one"),
      event("chunk", 1, "two"),
      event("done", 1, "final"),
    ]);

    expect(turns[0].entries.map((entry) => entry.kind)).toEqual(["turn_start", "chunk", "chunk", "done"]);
    expect(turns[0].entries.at(-1)?.text).toBe("final");
  });
});
