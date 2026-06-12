import { describe, expect, it } from "vitest";
import { renderMessageText, stripLegacyTurnResidue } from "./messageText";

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
  it("applies compact display after legacy turn cleanup", () => {
    const text = `**LLM Running (Turn 1) ...**\n\n${"a".repeat(1900)}`;

    const rendered = renderMessageText(text, {
      role: "assistant",
      compact: true,
      latestTraceTurn: 1,
    });

    expect(rendered).not.toContain("LLM Running");
    expect(rendered).toContain("[已压缩显示");
  });
});
