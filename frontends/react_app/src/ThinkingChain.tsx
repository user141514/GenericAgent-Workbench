import { useEffect, useMemo, useState } from "react";

interface ThinkingChainProps {
  steps: string[];
  isLive: boolean;
}

export function ThinkingChain({ steps, isLive }: ThinkingChainProps) {
  const segments = useMemo(
    () => steps.map((step) => step.trim()).filter(Boolean),
    [steps],
  );
  const [collapsed, setCollapsed] = useState(!isLive);

  useEffect(() => {
    if (!isLive) setCollapsed(true);
  }, [isLive]);

  if (!segments.length) return null;

  const label = `思考过程 · ${segments.length} 段`;

  if (collapsed) {
    return (
      <button
        className="thinking-chain thinking-collapsed"
        type="button"
        onClick={() => setCollapsed(false)}
      >
        <span className="thinking-chevron" aria-hidden="true">&#8250;</span>
        <span className="thinking-title">{label}</span>
      </button>
    );
  }

  return (
    <div className={`thinking-chain thinking-expanded${isLive ? " thinking-live" : ""}`}>
      <button
        className="thinking-header"
        type="button"
        onClick={() => setCollapsed(true)}
      >
        <span className="thinking-chevron open" aria-hidden="true">&#8250;</span>
        <span className="thinking-title">{label}</span>
        {isLive && <span className="thinking-live-indicator">生成中</span>}
      </button>
      <div className="thinking-segments" aria-label="thinking process">
        {segments.map((text, index) => (
          <p key={`${index}-${text.slice(0, 24)}`} className="thinking-segment">
            {text}
          </p>
        ))}
      </div>
    </div>
  );
}
