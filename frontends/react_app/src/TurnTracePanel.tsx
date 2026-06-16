import { useMemo } from "react";
import { ThinkingChain } from "./ThinkingChain";
import { buildTurnSummaries, labelForTurnState } from "./turnTrace";
import type { AgentEvent } from "./types";

type TurnTraceListProps = {
  events: AgentEvent[];
  thinkingByTurn?: Map<number, string[]>;
};

export function TurnTraceList({ events, thinkingByTurn }: TurnTraceListProps) {
  const turnSummaries = useMemo(() => buildTurnSummaries(events), [events]);
  if (turnSummaries.length === 0) return null;

  return (
    <div className="turn-list">
      {turnSummaries.map((turn) => {
        const thinkingSteps = thinkingByTurn?.get(turn.turn) || [];
        const isLive = turn.state === "running";
        return (
          <details key={turn.turn} className={`turn-card turn-${turn.state}`}>
            <summary>
              <span className="turn-chevron" aria-hidden="true">
                ›
              </span>
              <span className="turn-title">
                {labelForTurnState(turn.state)} (Turn {turn.turn}) ...
              </span>
            </summary>
            <div className="turn-detail">
              <ThinkingChain steps={thinkingSteps} isLive={isLive} />
              <p>{turn.text || (turn.state === "running" ? "运行中..." : "已完成")}</p>
              <div className="turn-meta">
                <span>{turn.chunks} chunks</span>
                <span>{turn.deltas} updates</span>
                <span>{turn.entries.length} detail lines</span>
              </div>
              {turn.entries.length > 0 && (
                <div className="turn-event-lines">
                  {turn.entries.map((entry, index) => (
                    <div key={`${entry.kind}-${index}`} className="turn-event-line">
                      <span>{entry.label}</span>
                      <p>{entry.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
