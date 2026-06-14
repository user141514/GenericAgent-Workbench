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
    const text = "**LLM Running (Turn 2) ...**\n\n当前轮输出";

    expect(stripLegacyTurnResidue(text, 2)).toBe("当前轮输出");
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
});
