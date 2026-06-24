// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { createRun, fetchLlmConfig, updateLlmConfig, uploadFiles } from "./api";
import { useAppStore } from "./store";
import type { AgentEvent } from "./types";

vi.mock("./api", () => ({
  createRun: vi.fn(),
  distillDeleteHistory: vi.fn(),
  fetchHistory: vi.fn().mockResolvedValue({ items: [] }),
  fetchMemory: vi.fn().mockResolvedValue({ items: {} }),
  fetchLlmConfig: vi.fn().mockResolvedValue({
    provider: "deepseek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-v4-pro",
    api_key_masked: "",
    configured: false,
    source: "unset",
    config_path: "C:\\Users\\Administrator\\AppData\\Roaming\\gagent-desktop\\llm_config.json",
    backend: "unconfigured",
  }),
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
  updateLlmConfig: vi.fn(),
  checkLlmConfig: vi.fn(),
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

async function waitForSettings() {
  await waitFor(() => expect(screen.getAllByText("test-backend").length).toBeGreaterThan(0));
}

describe("App chat surface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it("keeps the main title out of the content flow", async () => {
    render(<App />);

    await waitForSettings();

    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByText(/Good (morning|afternoon|evening)/i)).toBeNull();
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

    await waitForSettings();
    const turnTitle = screen.getByText("LLM Running (Turn 2) ...");
    const assistantMessage = turnTitle.closest("article");

    expect(assistantMessage?.className).toContain("message-assistant");
    expect(document.querySelector(".trace-panel")).toBeNull();
    expect(screen.queryByText("Turn trace")).toBeNull();
    expect(assistantMessage?.textContent).not.toContain("**LLM Running (Turn 1)");
    expect(assistantMessage?.textContent).not.toContain("Tool: `file_read` args");
  });

  it("renders preserved turn traces on previous assistant replies", async () => {
    useAppStore.setState({
      messages: [
        { id: "u1", role: "user", text: "first task" },
        {
          id: "a1",
          role: "assistant",
          text: "first final",
          traceEvents: [
            event("turn_start", 1),
            event("chunk", 1, "inspected files"),
            event("turn_end", 1),
          ],
        },
        { id: "u2", role: "user", text: "second task" },
        { id: "a2", role: "assistant", text: "second final" },
      ],
      events: [],
      runId: "",
      status: "idle",
    });

    render(<App />);

    await waitForSettings();
    const turnTitle = screen.getByText("LLM Done (Turn 1) ...");
    const assistantMessage = turnTitle.closest("article");
    const finalAnswer = assistantMessage?.querySelector(".message-final-answer");
    const traceSection = assistantMessage?.querySelector(".message-trace-section");

    expect(finalAnswer?.textContent).toContain("first final");
    expect(traceSection?.textContent).toContain("LLM Done (Turn 1) ...");
    expect(assistantMessage?.textContent).not.toContain("second final");
  });

  it("copies only the cleaned final assistant reply", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    useAppStore.setState({
      messages: [
        { id: "u1", role: "user", text: "audit the manuscript" },
        {
          id: "a1",
          role: "assistant",
          text: [
            "**LLM Running (Turn 1) ...**",
            "",
            "Tool: `file_read` args:",
            "```text",
            "{\"path\":\"main_manuscript_v2_mainline.md\"}",
            "```",
            "```",
            "[Action] Reading file: F:\\GAgent-Multi\\temp\\main_manuscript_v2_mainline.md",
            "```",
            "**LLM Running (Turn 2) ...**",
            "<summary>Prepared the answer.</summary>",
            "",
            "---",
            "",
            "## Final audit",
            "",
            "Only this should be copied.",
          ].join("\n"),
        },
      ],
      events: [],
      runId: "",
      status: "idle",
    });

    render(<App />);

    await waitForSettings();
    const finalAnswer = document.querySelector(".message-final-answer");
    expect(finalAnswer?.textContent).toContain("Final audit");
    expect(finalAnswer?.textContent).not.toContain("Tool:");
    expect(finalAnswer?.textContent).not.toContain("[Action]");

    fireEvent.click(screen.getByRole("button", { name: "复制" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("## Final audit\n\nOnly this should be copied."));
  });

  it("uploads dropped files from the composer", async () => {
    vi.mocked(uploadFiles).mockResolvedValueOnce({
      attachments: [
        {
          id: "file-1",
          name: "paper.md",
          size_label: "10 B",
          kind: "text",
          status: "ready",
          distilled_text: "paper text",
          warning: "",
        },
      ],
    });

    const { container } = render(<App />);
    await waitForSettings();

    const composer = container.querySelector("form.composer");
    expect(composer).toBeTruthy();
    const file = new File(["paper text"], "paper.md", { type: "text/markdown" });

    fireEvent.dragEnter(composer as Element, {
      dataTransfer: { files: [file], types: ["Files"], dropEffect: "copy" },
    });
    expect(screen.getByText("Drop files to attach")).toBeTruthy();

    fireEvent.drop(composer as Element, {
      dataTransfer: { files: [file], types: ["Files"], dropEffect: "copy" },
    });

    await waitFor(() => expect(uploadFiles).toHaveBeenCalledWith([file]));
    expect(screen.getByText(/paper.md/)).toBeTruthy();
  });

  it("uploads dropped files from inside the input surface", async () => {
    vi.mocked(uploadFiles).mockResolvedValueOnce({
      attachments: [
        {
          id: "file-1",
          name: "inside.md",
          size_label: "10 B",
          kind: "text",
          status: "ready",
          distilled_text: "paper text",
          warning: "",
        },
      ],
    });

    render(<App />);
    await waitForSettings();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    const file = new File(["paper text"], "inside.md", { type: "text/markdown" });

    fireEvent.dragEnter(textbox, {
      dataTransfer: { files: [file], types: ["Files"], dropEffect: "copy" },
    });
    expect(textbox.closest(".composer-surface")?.className).toContain("drag-active");

    fireEvent.drop(textbox, {
      dataTransfer: { files: [file], types: ["Files"], dropEffect: "copy" },
    });

    await waitFor(() => expect(uploadFiles).toHaveBeenCalledWith([file]));
    expect(screen.getByText(/inside.md/)).toBeTruthy();
  });

  it("sends with Enter and keeps Shift+Enter for new lines", async () => {
    vi.mocked(createRun).mockResolvedValueOnce({ run_id: "run_1", status: "started" });

    render(<App />);
    await waitForSettings();

    const textbox = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(textbox, { target: { value: "first line" } });

    fireEvent.keyDown(textbox, { key: "Enter", code: "Enter", shiftKey: true });
    expect(createRun).not.toHaveBeenCalled();
    fireEvent.change(textbox, { target: { value: "first line\nsecond line" } });

    fireEvent.keyDown(textbox, { key: "Enter", code: "Enter" });

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith("first line\nsecond line", [], "auto"),
    );
  });

  it("expands the textarea to match entered content", async () => {
    render(<App />);
    await waitForSettings();

    const textbox = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
    Object.defineProperty(textbox, "scrollHeight", { configurable: true, value: 112 });

    fireEvent.change(textbox, { target: { value: "line 1\nline 2\nline 3\nline 4" } });

    expect(textbox.style.height).toBe("112px");
  });

  it("lets the user save an API key from the model link panel", async () => {
    vi.mocked(updateLlmConfig).mockResolvedValueOnce({
      provider: "deepseek",
      base_url: "https://api.deepseek.com",
      model: "deepseek-v4-pro",
      api_key_masked: "sk-1...abcd",
      configured: true,
      source: "local",
      config_path: "C:\\Users\\Administrator\\AppData\\Roaming\\gagent-desktop\\llm_config.json",
      backend: "deepseek-v4-pro",
    });

    render(<App />);
    await waitForSettings();

    await waitFor(() => expect(fetchLlmConfig).toHaveBeenCalled());
    const apiKeyInput = screen.getByLabelText("API key");
    fireEvent.change(apiKeyInput, { target: { value: "sk-1234abcd" } });
    fireEvent.click(screen.getByRole("button", { name: "Save API key" }));

    await waitFor(() =>
      expect(updateLlmConfig).toHaveBeenCalledWith({
        provider: "deepseek",
        base_url: "https://api.deepseek.com",
        model: "deepseek-v4-pro",
        api_key: "sk-1234abcd",
      }),
    );
    expect(screen.getByText(/Saved API key/)).toBeTruthy();
  });

  it("does not upload dropped files while a run is active", async () => {
    useAppStore.setState({ status: "running", runId: "run_1" });

    const { container } = render(<App />);
    await waitForSettings();

    const composer = container.querySelector("form.composer");
    const file = new File(["paper text"], "paper.md", { type: "text/markdown" });

    fireEvent.drop(composer as Element, {
      dataTransfer: { files: [file], types: ["Files"], dropEffect: "copy" },
    });

    expect(uploadFiles).not.toHaveBeenCalled();
  });
});
