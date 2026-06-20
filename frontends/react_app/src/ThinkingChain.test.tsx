// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThinkingChain } from "./ThinkingChain";

describe("ThinkingChain", () => {
  it("renders nothing when steps is empty", () => {
    const { container } = render(
      <ThinkingChain steps={[]} isLive={false} />,
    );
    expect(container.textContent).toBe("");
  });

  it("renders collapsed by default when not live", () => {
    render(
      <ThinkingChain
        steps={["Step 1 text", "Step 2 text"]}
        isLive={false}
      />,
    );
    expect(screen.getByText(/思考过程 · 2 段/)).toBeTruthy();
    expect(screen.queryByText("Step 1 text")).toBeNull();
  });

  it("renders expanded when isLive is true", () => {
    render(
      <ThinkingChain
        steps={["Step 1 text", "Step 2 text"]}
        isLive={true}
      />,
    );
    expect(screen.getByText("Step 1 text")).toBeTruthy();
    expect(screen.getByText("Step 2 text")).toBeTruthy();
  });

  it("auto-collapses when isLive changes to false", () => {
    const { rerender } = render(
      <ThinkingChain steps={["Step 1"]} isLive={true} />,
    );
    expect(screen.getByText("Step 1")).toBeTruthy();

    rerender(<ThinkingChain steps={["Step 1"]} isLive={false} />);
    expect(screen.queryByText("Step 1")).toBeNull();
    expect(screen.getByText(/思考过程 · 1 段/)).toBeTruthy();
  });

  it("expands on click when collapsed", () => {
    render(
      <ThinkingChain steps={["Expand me"]} isLive={false} />,
    );
    fireEvent.click(screen.getByText(/思考过程 · 1 段/));
    expect(screen.getByText("Expand me")).toBeTruthy();
  });

  it("collapses on header click when expanded", () => {
    render(
      <ThinkingChain steps={["Collapse me"]} isLive={true} />,
    );
    const header = screen.getByText(/思考过程 · 1 段/);
    fireEvent.click(header);
    expect(screen.queryByText("Collapse me")).toBeNull();
  });

  it("renders live thinking as prose blocks instead of numbered steps", () => {
    render(
      <ThinkingChain steps={["First", "Last"]} isLive={true} />,
    );
    expect(document.querySelectorAll(".thinking-steps li")).toHaveLength(0);
    expect(document.querySelectorAll(".thinking-segment")).toHaveLength(2);
    expect(document.querySelector(".thinking-chain")?.className).toContain("thinking-live");
  });
});
