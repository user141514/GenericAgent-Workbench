import { useEffect, useState } from "react";

interface ThinkingChainProps {
  steps: string[];
  isLive: boolean; // true = this turn is currently running → expanded
}

export function ThinkingChain({ steps, isLive }: ThinkingChainProps) {
  const [collapsed, setCollapsed] = useState(!isLive);

  // Auto-collapse when this turn stops running
  useEffect(() => {
    if (!isLive) setCollapsed(true);
  }, [isLive]);

  if (!steps.length) return null;

  if (collapsed) {
    return (
      <div
        className="thinking-chain thinking-collapsed"
        onClick={() => setCollapsed(false)}
      >
        <span className="thinking-chevron">&#8250;</span>
        &#x1F4AD; 思考过程 ({steps.length} steps)
      </div>
    );
  }

  return (
    <div className="thinking-chain thinking-expanded">
      <div
        className="thinking-header"
        onClick={() => setCollapsed(true)}
      >
        <span className="thinking-chevron open">&#8250;</span>
        &#x1F4AD; 思考过程 ({steps.length} steps)
      </div>
      <ol className="thinking-steps">
        {steps.map((text, i) => (
          <li
            key={i}
            className={
              i === steps.length - 1 && isLive ? "thinking-live" : ""
            }
          >
            {text}
          </li>
        ))}
      </ol>
    </div>
  );
}
