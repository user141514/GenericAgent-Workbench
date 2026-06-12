// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders assistant markdown as structured HTML", () => {
    const { container } = render(
      <MarkdownMessage
        role="assistant"
        text={[
          "## 标题",
          "",
          "- 第一项",
          "- 第二项",
          "",
          "```ts",
          "const ok = true;",
          "```",
        ].join("\n")}
      />,
    );

    expect(screen.getByRole("heading", { level: 2, name: "标题" })).toBeTruthy();
    expect(screen.getByText("第一项").tagName).toBe("LI");
    expect(container.querySelector("pre code")?.textContent).toContain("const ok = true;");
    expect(container.textContent).not.toContain("## 标题");
    expect(container.textContent).not.toContain("```ts");
  });

  it("keeps user text plain", () => {
    const { container } = render(<MarkdownMessage role="user" text="## 不渲染" />);

    expect(container.querySelector("h2")).toBeNull();
    expect(screen.getByText("## 不渲染")).toBeTruthy();
  });
});
