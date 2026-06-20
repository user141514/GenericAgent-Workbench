import { useMemo } from "react";
import { FrontierStatePanel } from "./FrontierStatePanel";
import { MarkdownMessage } from "./MarkdownMessage";
import { renderMessageText } from "./messageText";
import { hasVisibleTurnTrace, maxTraceTurn } from "./messageTrace";
import { TurnTraceList } from "./TurnTracePanel";
import type { AgentEvent, ChatMessage, FrontierStateSnapshot } from "./types";

type ChatMessageItemProps = {
  message: ChatMessage;
  traceEvents: AgentEvent[];
  thinkingByTurn: Map<number, string[]>;
  compactAssistantHistory: boolean;
  showFrontier: boolean;
  frontierState: FrontierStateSnapshot | null;
  showCopy: boolean;
  onCopy: () => void;
};

export function ChatMessageItem({
  message,
  traceEvents,
  thinkingByTurn,
  compactAssistantHistory,
  showFrontier,
  frontierState,
  showCopy,
  onCopy,
}: ChatMessageItemProps) {
  const traceTurn = useMemo(() => maxTraceTurn(traceEvents), [traceEvents]);
  const text = renderMessageText(message.text, {
    role: message.role,
    compact: compactAssistantHistory,
    streaming: message.streaming,
    latestTraceTurn: traceTurn,
  });
  const showTrace = hasVisibleTurnTrace(traceEvents);

  return (
    <article className={`message message-${message.role}`}>
      <div className="message-header">
        <div className="message-role">{message.role}</div>
        {message.streaming && <span className="message-state">running</span>}
      </div>

      {text && (
        <section
          className={message.role === "assistant" ? "message-final-answer" : "message-user-content"}
          aria-label={message.role === "assistant" ? "final reply" : undefined}
        >
          {message.role === "assistant" && <div className="message-section-label">最终回复</div>}
          <MarkdownMessage role={message.role} text={text} />
          {showCopy && (
            <div className="message-actions">
              <button className="message-copy-button" type="button" onClick={onCopy}>
                复制
              </button>
            </div>
          )}
        </section>
      )}

      {showFrontier && frontierState?.enabled && <FrontierStatePanel snapshot={frontierState} />}

      {showTrace && (
        <section className="message-trace-section" aria-label="turn trace">
          <div className="message-section-label">运行过程</div>
          <TurnTraceList events={traceEvents} thinkingByTurn={thinkingByTurn} />
        </section>
      )}
    </article>
  );
}
