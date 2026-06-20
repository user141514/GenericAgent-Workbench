import { describe, expect, it } from "vitest";
import { thinkingMapForEvents } from "./messageTrace";
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

describe("thinkingMapForEvents", () => {
  it("coalesces streaming thinking deltas into readable segments", () => {
    const deltas = ["这", "个", "用户", "发", "来", "了", "一份", "课题"];

    const map = thinkingMapForEvents(
      deltas.map((text) => event("thinking_block", 1, text)),
    );

    expect(map.get(1)).toEqual(["这个用户发来了一份课题"]);
  });

  it("splits blank-line separated thinking into paragraphs without using every event as a step", () => {
    const map = thinkingMapForEvents([
      event("thinking_block", 1, "第一段分析。\n\n第二段验证。"),
      event("thinking_block", 1, "\n\n第三段收束。"),
    ]);

    expect(map.get(1)).toEqual([
      "第一段分析。",
      "第二段验证。",
      "第三段收束。",
    ]);
  });
});
