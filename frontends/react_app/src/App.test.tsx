// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { useAppStore } from "./store";
import type { AgentEvent } from "./types";

vi.mock("./api", () => ({
  createRun: vi.fn(),
  distillDeleteHistory: vi.fn(),
  fetchHistory: vi.fn().mockResolvedValue({ items: [] }),
  fetchMemory: vi.fn().mockResolvedValue({ items: {} }),
  fetchSettings: vi.fn().mockResolvedValue({
    routing_mode: "auto",
    compact_assistant_history: true,
    autonomous_enabled: false,
    last_reply_time: 0,
    idle_seconds: 0,
    backend: "test-backend",
    current_key_index: 0,
    key_labels: [],
  }),
  reinjectTools: vi.fn(),
  resetConversation: vi.fn(),
  restoreHistory: vi.fn(),
  stopRun: vi.fn(),
  streamRunEvents: vi.fn(),
  switchKey: vi.fn(),
  triggerAutonomous: vi.fn(),
  updateSettings: vi.fn(),
  uploadFiles: vi.fn(),
}));

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

describe("App turn trace placement", () => {
  beforeEach(() => {
    useAppStore.getState().clearConversation();
    useAppStore.setState({
      attachments: [],
      history: [],
      memory: {},
      runId: "",
      status: "idle",
      error: "",
      settings: {
        routing_mode: "auto",
        compact_assistant_history: true,
        autonomous_enabled: false,
        last_reply_time: 0,
        idle_seconds: 0,
        backend: "test-backend",
        current_key_index: 0,
        key_labels: [],
      },
    });
  });

  it("renders running turns inside the assistant reply instead of a separate trace panel", async () => {
    useAppStore.setState({
      messages: [
        { id: "u1", role: "user", text: "do work" },
        {
          id: "a1",
          role: "assistant",
          text: "**LLM Running (Turn 1) ...**\n\nTool: `file_read` args:\n```text\n{}\n```",
          streaming: true,
        },
      ],
      events: [
        event("turn_start", 1),
        event("chunk", 1, "old tool output"),
        event("turn_end", 1),
        event("turn_start", 2),
      ],
      runId: "run_1",
      status: "running",
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText("test-backend")).toBeTruthy());
    const turnTitle = screen.getByText("LLM Running (Turn 2) ...");
    const assistantMessage = turnTitle.closest("article");

    expect(assistantMessage?.className).toContain("message-assistant");
    expect(document.querySelector(".trace-panel")).toBeNull();
    expect(screen.queryByText("Turn trace")).toBeNull();
    expect(assistantMessage?.textContent).not.toContain("**LLM Running (Turn 1)");
    expect(assistantMessage?.textContent).not.toContain("Tool: `file_read` args");
  });
});
