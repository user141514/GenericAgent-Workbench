import { describe, expect, it } from "vitest";
import { applyAgentEvent, friendlyErrorText, lastAssistantText, useAppStore } from "./store";
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
    const second = applyAgentEvent(first.messages, event("chunk", " done"));

    expect(second.messages).toHaveLength(2);
    expect(second.messages[1].text).toBe("partial done");
    expect(second.messages[1].streaming).toBe(true);
  });

  it("keeps turn_delta events in trace without creating assistant body text", () => {
    const start: ChatMessage[] = [{ id: "u1", role: "user", text: "hello" }];
    const turnStart = event("turn_start", "");
    const first = applyAgentEvent(start, turnStart, []);
    const second = applyAgentEvent(first.messages, event("turn_delta", "tool progress"), [turnStart]);

    expect(second.messages).toEqual(start);
    expect(second.status).toBe("running");
  });

  it("does not duplicate turn_delta text when the matching chunk arrives", () => {
    const start: ChatMessage[] = [{ id: "u1", role: "user", text: "hello" }];
    const turnStart = event("turn_start", "");
    const turnDelta = event("turn_delta", "same text");
    const chunk = event("chunk", "same text");

    const first = applyAgentEvent(start, turnStart, []);
    const second = applyAgentEvent(first.messages, turnDelta, [turnStart]);
    const third = applyAgentEvent(second.messages, chunk, [turnStart, turnDelta]);

    expect(third.messages).toHaveLength(2);
    expect(third.messages[1].text).toBe("same text");
    expect(third.messages[1].traceEvents?.map((entry) => entry.kind)).toEqual([
      "turn_start",
      "turn_delta",
      "chunk",
    ]);
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

  it("attaches turn events to the assistant message so old replies keep their trace", () => {
    const start: ChatMessage[] = [{ id: "u1", role: "user", text: "hello" }];
    const turnStart = event("turn_start", "");
    const chunk = event("chunk", "partial");
    const done = event("done", "final");

    const first = applyAgentEvent(start, turnStart, []);
    const second = applyAgentEvent(first.messages, chunk, [turnStart]);
    const third = applyAgentEvent(second.messages, done, [turnStart, chunk]);

    expect(third.messages[1].traceEvents?.map((entry) => entry.kind)).toEqual([
      "turn_start",
      "chunk",
      "done",
    ]);
    expect(third.messages[1].streaming).toBe(false);
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

describe("friendlyErrorText", () => {
  it("labels connection timeouts as network faults", () => {
    const text = friendlyErrorText(
      "CONNECTION_ERROR ConnectTimeout: HTTPSConnectionPool(host='api.deepseek.com') timed out",
    );

    expect(text).toContain("网络连接故障");
    expect(text).toContain("api.deepseek.com");
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
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: "user", text: "new question" });
  });

  it("keeps old assistant trace events after starting the next run", () => {
    useAppStore.setState({
      messages: [{ id: "u1", role: "user", text: "first question" }],
      events: [],
      frontierState: null,
      runId: "run_1",
      status: "running",
      error: "",
    });

    useAppStore.getState().applyEvent(event("turn_start", ""));
    useAppStore.getState().applyEvent(event("chunk", "first partial"));
    useAppStore.getState().applyEvent(event("done", "first final"));
    useAppStore.getState().setRunStarted("run_2", "second question");

    const firstAssistant = useAppStore.getState().messages.find((message) => message.role === "assistant");
    expect(firstAssistant?.text).toBe("first final");
    expect(firstAssistant?.traceEvents?.map((entry) => entry.kind)).toEqual([
      "turn_start",
      "chunk",
      "done",
    ]);
    expect(useAppStore.getState().events).toEqual([]);
  });

  it("ignores stale events from an earlier run", () => {
    useAppStore.setState({
      messages: [{ id: "u2", role: "user", text: "second question" }],
      events: [],
      frontierState: null,
      runId: "run_2",
      status: "running",
      error: "",
    });

    useAppStore.getState().applyEvent({
      ...event("chunk", "stale first answer"),
      task_id: "run_1",
    });

    const state = useAppStore.getState();
    expect(state.messages).toEqual([{ id: "u2", role: "user", text: "second question" }]);
    expect(state.events).toEqual([]);
    expect(state.status).toBe("running");
  });

  it("adds synthetic trace events when restoring assistant history with legacy turns", () => {
    useAppStore.getState().restoreConversation([
      { role: "user", text: "old question" },
      {
        role: "assistant",
        text: [
          "**LLM Running (Turn 1) ...**",
          "",
          "Tool: `file_read` args:",
          "```text",
          "{\"path\":\"app.py\"}",
          "```",
          "```",
          "[Action] Reading file: app.py",
          "```",
          "**LLM Running (Turn 2) ...**",
          "",
          "Final answer.",
        ].join("\n"),
      },
    ]);

    const assistant = useAppStore.getState().messages.find((message) => message.role === "assistant");
    expect(assistant?.traceEvents?.map((entry) => entry.turn)).toEqual([1, 1, 2]);
    expect(assistant?.traceEvents?.map((entry) => entry.kind)).toEqual([
      "turn_start",
      "turn_delta",
      "turn_start",
    ]);
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
