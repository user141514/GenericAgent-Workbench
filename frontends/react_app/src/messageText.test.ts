import { describe, expect, it } from "vitest";
import { copyableMessageText, renderMessageText, stripLegacyTurnResidue } from "./messageText";

describe("stripLegacyTurnResidue", () => {
  it("hides stale legacy turn text when structured events have advanced", () => {
    const text = [
      "**LLM Running (Turn 1) ...**",
      "",
      "Tool: `file_read` args:",
      "```text",
      "{\"path\":\"../core/ga.py\"}",
      "```",
    ].join("\n");

    expect(stripLegacyTurnResidue(text, 2)).toBe("");
  });

  it("removes the current legacy marker but keeps current visible content", () => {
    const text = "**LLM Running (Turn 2) ...**\n\ncurrent output";

    expect(stripLegacyTurnResidue(text, 2)).toBe("current output");
  });
});

describe("renderMessageText", () => {
  it("shows the full assistant reply even when compact mode is enabled", () => {
    const text = `**LLM Running (Turn 1) ...**\n\n${"a".repeat(1900)}`;

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
      latestTraceTurn: 1,
    });

    expect(rendered).not.toContain("LLM Running");
    expect(rendered).toBe("a".repeat(1900));
  });

  it("shows only the final assistant answer after legacy tool transcript noise", () => {
    const text = [
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
      "Only this should be displayed.",
    ].join("\n");

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
      latestTraceTurn: 2,
    });

    expect(rendered).toBe("## Final audit\n\nOnly this should be displayed.");
    expect(rendered).not.toContain("Tool:");
    expect(rendered).not.toContain("[Action]");
    expect(rendered).not.toContain("<summary>");
  });

  it("hides leading function-style tool call transcripts from the displayed reply", () => {
    const text = [
      'code_run({"script": "\\n# explore project\\nimport os\\n"})',
      "",
      'file_read({"path": "app.py"})',
      "",
      'file_read({"path": "ai_service.py"})',
      "",
      "I have read the key files. Here is the audit.",
      "",
      "---",
      "",
      "## Code audit",
      "",
      "Only the final answer should be visible.",
    ].join("\n");

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
    });

    expect(rendered).toBe(
      "I have read the key files. Here is the audit.\n\n---\n\n## Code audit\n\nOnly the final answer should be visible.",
    );
    expect(rendered).not.toContain("code_run");
    expect(rendered).not.toContain("file_read");
  });

  it("hides Python repr thinking/tool_use blocks and XML internal tags", () => {
    const text = [
      "[{'type': 'thinking', 'thinking': 'I need to inspect files.'}, {'type': 'tool_use', 'name': 'file_read', 'input': {'path': 'app.py'}}]",
      "",
      "<thinking>private reasoning</thinking>",
      "<tool_use>{\"name\":\"file_read\",\"arguments\":{\"path\":\"app.py\"}}</tool_use>",
      "",
      "## Final report",
      "",
      "Visible answer only.",
    ].join("\n");

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
    });

    expect(rendered).toBe("## Final report\n\nVisible answer only.");
    expect(rendered).not.toContain("thinking");
    expect(rendered).not.toContain("tool_use");
    expect(rendered).not.toContain("file_read");
  });

  it("removes leading function calls and runtime fences without deleting final markdown code", () => {
    const text = [
      'code_run({"script": "print(1)"})',
      "```",
      "[Stdout] noisy output",
      "```",
      "",
      "Final answer:",
      "",
      "```python",
      "print('keep me')",
      "```",
    ].join("\n");

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
    });

    expect(rendered).toBe("Final answer:\n\n```python\nprint('keep me')\n```");
  });

  it("removes tool args fences that follow a legacy Tool line", () => {
    const text = [
      "Tool: `file_read` args:",
      "```text",
      "{\"path\":\"app.py\"}",
      "```",
      "```",
      "[Action] Reading file: app.py",
      "```",
      "",
      "## Final answer",
      "",
      "Visible text.",
    ].join("\n");

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
    });

    expect(rendered).toBe("## Final answer\n\nVisible text.");
    expect(rendered).not.toContain("app.py");
    expect(rendered).not.toContain("```text");
  });

  it("removes multiline function-style calls and their runtime output", () => {
    const text = [
      "code_run({",
      "  \"script\": \"print(1)\"",
      "})",
      "```",
      "[Stdout] 1",
      "```",
      "",
      "Final conclusion.",
    ].join("\n");

    expect(renderMessageText(text, { role: "assistant", compact: true })).toBe("Final conclusion.");
  });

  it("removes multiline Python repr internal blocks", () => {
    const text = [
      "[",
      "  {'type': 'thinking', 'thinking': 'private'},",
      "  {'type': 'tool_use', 'name': 'file_read', 'input': {'path': 'app.py'}}",
      "]",
      "",
      "Final report.",
    ].join("\n");

    expect(renderMessageText(text, { role: "assistant", compact: true })).toBe("Final report.");
  });
});

describe("copyableMessageText", () => {
  it("removes legacy turn and tool transcript noise from copied replies", () => {
    const text = [
      "**LLM Running (Turn 1) ...**",
      "",
      "Tool: `file_read` args:",
      "````text",
      "{\"path\":\"main_manuscript_v2_mainline.md\"}",
      "````",
      "`````",
      "[Action] Reading file: F:\\GAgent-Multi\\temp\\main_manuscript_v2_mainline.md",
      "`````",
      "**LLM Running (Turn 2) ...**",
      "",
      "Tool: `file_read` args:",
      "```text",
      "{\"path\":\"F:\\\\GAgent-Multi\\\\temp\\\\main_manuscript_v2.md\"}",
      "```",
      "```",
      "[Action] Reading file: F:\\GAgent-Multi\\temp\\main_manuscript_v2.md",
      "```",
      "**LLM Running (Turn 5) ...**",
      "<summary>Read the manuscript and prepared the audit.</summary>",
      "",
      "---",
      "",
      "## Mainline audit",
      "",
      "Keep this final answer.",
    ].join("\n");

    const copied = copyableMessageText(text);

    expect(copied).toBe("## Mainline audit\n\nKeep this final answer.");
    expect(copied).not.toContain("LLM Running");
    expect(copied).not.toContain("Tool:");
    expect(copied).not.toContain("[Action]");
    expect(copied).not.toContain("<summary>");
  });

  it("removes leading function-style tool call transcripts from copied replies", () => {
    const text = [
      'code_run({"script": "\\nprint(1)\\n"})',
      'file_read({"path": "app.py"})',
      "",
      "Final conclusion.",
    ].join("\n");

    expect(copyableMessageText(text)).toBe("Final conclusion.");
  });

  it("removes Python repr and XML internal blocks from copied replies", () => {
    const text = [
      "[{'type': 'thinking', 'thinking': 'private'}, {'type': 'tool_use', 'name': 'code_run', 'input': {}}]",
      "<tool_result>{\"status\":\"success\"}</tool_result>",
      "",
      "Final copy.",
    ].join("\n");

    expect(copyableMessageText(text)).toBe("Final copy.");
  });
});
