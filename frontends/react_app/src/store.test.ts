import { describe, expect, it } from "vitest";
import { applyAgentEvent, lastAssistantText, useAppStore } from "./store";
import type { AgentEvent, ChatMessage } from "./types";

function event(kind: AgentEvent["kind"], text = "", error = ""): AgentEvent {
  return {
    kind,
    text,
    error,
    source: "user",
    turn: 1,
    task_id: "run_1",
    metadata: {},
  };
}

describe("applyAgentEvent", () => {
  it("updates the streaming assistant message from chunk events", () => {
    const start: ChatMessage[] = [{ id: "u1", role: "user", text: "hello" }];
    const first = applyAgentEvent(start, event("chunk", "partial"));
    const second = applyAgentEvent(first.messages, event("chunk", "partial done"));

    expect(second.messages).toHaveLength(2);
    expect(second.messages[1].text).toBe("partial done");
    expect(second.messages[1].streaming).toBe(true);
  });

  it("finalizes the assistant message on done", () => {
    const start: ChatMessage[] = [
      { id: "u1", role: "user", text: "hello" },
      { id: "a1", role: "assistant", text: "partial", streaming: true },
    ];

    const result = applyAgentEvent(start, event("done", "final"));

    expect(result.status).toBe("idle");
    expect(result.messages[1].text).toBe("final");
    expect(result.messages[1].streaming).toBe(false);
  });

  it("records errors as terminal assistant text", () => {
    const result = applyAgentEvent([], event("error", "", "boom"));

    expect(result.status).toBe("error");
    expect(result.error).toBe("boom");
    expect(result.messages[0].text).toBe("boom");
  });
});

describe("lastAssistantText", () => {
  it("copies only the latest assistant reply", () => {
    const text = lastAssistantText([
      { id: "u1", role: "user", text: "first question" },
      { id: "a1", role: "assistant", text: "old reply" },
      { id: "u2", role: "user", text: "second question" },
      { id: "a2", role: "assistant", text: "new reply" },
    ]);

    expect(text).toBe("new reply");
  });
});

describe("useAppStore run lifecycle", () => {
  it("clears previous run events when a new run starts", () => {
    useAppStore.setState({
      messages: [{ id: "a1", role: "assistant", text: "old reply" }],
      events: [event("turn_start", "old trace")],
      runId: "old_run",
      status: "idle",
      error: "",
    });

    useAppStore.getState().setRunStarted("new_run", "new question");

    const state = useAppStore.getState();
    expect(state.runId).toBe("new_run");
    expect(state.events).toEqual([]);
    expect(state.messages.at(-1)).toMatchObject({ role: "user", text: "new question" });
  });

  it("updates frontier state without creating assistant text", () => {
    useAppStore.setState({
      messages: [{ id: "u1", role: "user", text: "research question" }],
      events: [],
      frontierState: null,
      runId: "run_1",
      status: "running",
      error: "",
    });

    useAppStore.getState().applyEvent({
      ...event("frontier_state"),
      metadata: {
        frontier_state: {
          enabled: true,
          mode: "research",
          run_id: "run_1",
          intent_state: { task_type: "research_frontier" },
          evidence_state: {},
          strategy_state: {},
          execution_state: {},
          synthesis_state: {},
          confidence_state: {},
        },
      },
    });

    const state = useAppStore.getState();
    expect(state.frontierState?.enabled).toBe(true);
    expect(state.messages).toHaveLength(1);
    expect(state.events).toEqual([]);
  });
});
