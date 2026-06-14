import {
  DragEvent,
  FormEvent,
  KeyboardEvent,
  MouseEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  createRun,
  distillDeleteHistory,
  fetchHistory,
  fetchMemory,
  fetchSettings,
  reinjectTools,
  resetConversation,
  restoreHistory,
  stopRun,
  streamRunEvents,
  switchKey,
  triggerAutonomous,
  updateSettings,
  uploadFiles,
} from "./api";
import { FrontierStatePanel } from "./FrontierStatePanel";
import { MarkdownMessage } from "./MarkdownMessage";
import { copyableMessageText, renderMessageText } from "./messageText";
import { lastAssistantText, useAppStore } from "./store";
import { TurnTraceList } from "./TurnTracePanel";
import type { AgentEvent, AppSettings, RoutingMode } from "./types";
import "./styles.css";

type SidePanel = "history" | "memory" | "";
type HistoryContextMenu = {
  filename: string;
  title: string;
  x: number;
  y: number;
} | null;

const routingLabels: Record<RoutingMode, string> = {
  auto: "自动判断",
  classic: "经典模式",
  multi_agent: "多Agent编排",
};

export default function App() {
  const [input, setInput] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [notice, setNotice] = useState("");
  const [sidePanel, setSidePanel] = useState<SidePanel>("");
  const [historyMenu, setHistoryMenu] = useState<HistoryContextMenu>(null);
  const eventSource = useRef<EventSource | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const {
    messages,
    events,
    attachments,
    history,
    memory,
    frontierState,
    settings,
    runId,
    status,
    error,
    setRunStarted,
    setStopping,
    applyEvent,
    setAttachments,
    setHistory,
    setMemory,
    setSettings,
    setError,
    restoreConversation,
    clearConversation,
    clearAttachments,
  } = useAppStore();

  const canSend = status === "idle" && input.trim().length > 0;
  const canStop = status === "running";
  const latestReply = useMemo(() => copyableMessageText(lastAssistantText(messages)), [messages]);
  const latestAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return "";
  }, [messages]);
  const streamingAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant" && messages[i].streaming) return messages[i].id;
    }
    return "";
  }, [messages]);
  const hasTurnTrace = useMemo(
    () => events.some((event) => event.turn > 0 && event.kind !== "status"),
    [events],
  );
  const latestTraceTurn = useMemo(
    () => events.reduce((maxTurn, event) => (event.kind === "status" ? maxTurn : Math.max(maxTurn, event.turn || 0)), 0),
    [events],
  );
  const traceMessageId = hasTurnTrace
    ? streamingAssistantId || (status === "idle" || status === "error" ? latestAssistantId : "")
    : "";
  const needsLiveAssistantMessage = (status === "running" || status === "stopping") && !streamingAssistantId;

  useEffect(() => {
    refreshSidebarData();
    return () => eventSource.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useLayoutEffect(() => {
    resizeTextarea();
  }, [input]);

  async function refreshSidebarData() {
    await Promise.all([
      fetchHistory().then((data) => setHistory(data.items)).catch(() => setHistory([])),
      fetchMemory().then((data) => setMemory(data.items)).catch(() => setMemory({})),
      fetchSettings().then((data) => setSettings(data)).catch(() => undefined),
    ]);
  }

  function startEventStream(runIdValue: string) {
    eventSource.current?.close();
    eventSource.current = streamRunEvents(
      runIdValue,
      (agentEvent: AgentEvent) => applyEvent(agentEvent),
      (streamError) => setError(streamError.message),
    );
  }

  function resizeTextarea(element = textareaRef.current) {
    if (!element) return;
    element.style.height = "auto";
    if (element.scrollHeight > 0) {
      const nextHeight = Math.min(element.scrollHeight, 280);
      element.style.height = `${nextHeight}px`;
      element.style.overflowY = element.scrollHeight > 280 ? "auto" : "hidden";
    }
  }

  async function submitPrompt() {
    if (!canSend || isUploading) return;
    const query = input.trim();
    setInput("");
    setNotice("");
    try {
      const run = await createRun(query, attachments, settings.routing_mode);
      setRunStarted(run.run_id, query);
      clearAttachments();
      startEventStream(run.run_id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError));
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submitPrompt();
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key !== "Enter"
      || event.shiftKey
      || event.altKey
      || event.ctrlKey
      || event.metaKey
      || event.nativeEvent.isComposing
    ) {
      return;
    }
    event.preventDefault();
    void submitPrompt();
  }

  async function onStop() {
    if (!runId) return;
    setStopping();
    try {
      await stopRun(runId);
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : String(stopError));
    }
  }

  function hasDraggedFiles(event: DragEvent<HTMLElement>) {
    const transfer = event.dataTransfer;
    return Array.from(transfer.types || []).includes("Files") || transfer.files.length > 0;
  }

  function onComposerDragEnter(event: DragEvent<HTMLFormElement>) {
    if (status !== "idle" || isUploading || !hasDraggedFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDragActive(true);
  }

  function onComposerDragOver(event: DragEvent<HTMLFormElement>) {
    if (status !== "idle" || isUploading || !hasDraggedFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    if (!isDragActive) setIsDragActive(true);
  }

  function onComposerDragLeave(event: DragEvent<HTMLFormElement>) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) return;
    setIsDragActive(false);
  }

  async function onComposerDrop(event: DragEvent<HTMLFormElement>) {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    setIsDragActive(false);
    if (status !== "idle" || isUploading) return;
    await onFileChange(event.dataTransfer.files);
  }

  async function onFileChange(files: FileList | File[] | null) {
    if (!files?.length) return;
    if (status !== "idle" || isUploading) return;
    setIsUploading(true);
    setNotice("");
    try {
      const result = await uploadFiles(Array.from(files));
      setAttachments(result.attachments);
      setNotice(`已附加 ${result.attachments.length} 个文件`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : String(uploadError));
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function copyLastReply() {
    if (!latestReply) return;
    await navigator.clipboard.writeText(latestReply);
    setNotice("已复制最后一条回复");
  }

  async function onNewChat() {
    try {
      eventSource.current?.close();
      await resetConversation();
      clearConversation();
      clearAttachments();
      setInput("");
      setNotice("已新建对话");
      await refreshSidebarData();
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : String(resetError));
    }
  }

  async function onRestoreHistory(filename: string) {
    try {
      eventSource.current?.close();
      const restored = await restoreHistory(filename);
      restoreConversation(restored.messages);
      clearAttachments();
      setInput("");
      setNotice(`已恢复 ${restored.count} 轮历史对话：${restored.item.title || restored.item.filename}`);
      setHistoryMenu(null);
    } catch (restoreError) {
      setError(restoreError instanceof Error ? restoreError.message : String(restoreError));
    }
  }

  function openHistoryMenu(event: MouseEvent, filename: string, title: string) {
    event.preventDefault();
    const menuWidth = 280;
    const menuHeight = 168;
    const margin = 12;
    setHistoryMenu({
      filename,
      title,
      x: Math.max(margin, Math.min(event.clientX, window.innerWidth - menuWidth - margin)),
      y: Math.max(margin, Math.min(event.clientY, window.innerHeight - menuHeight - margin)),
    });
  }

  async function onDistillDeleteHistory(filename: string) {
    try {
      const result = await distillDeleteHistory(filename);
      setNotice(`已删除并蒸馏：${result.summary?.title || result.filename}`);
      setHistoryMenu(null);
      await Promise.all([
        fetchHistory().then((data) => setHistory(data.items)),
        fetchMemory().then((data) => setMemory(data.items)),
      ]);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : String(deleteError));
    }
  }

  async function patchSettings(patch: Partial<Pick<AppSettings, "routing_mode" | "compact_assistant_history" | "autonomous_enabled">>) {
    try {
      const next = await updateSettings(patch);
      setSettings(next);
    } catch (settingsError) {
      setError(settingsError instanceof Error ? settingsError.message : String(settingsError));
    }
  }

  async function onSwitchKey(index: number) {
    try {
      const result = await switchKey(index);
      setSettings(result.settings);
      setNotice(`已切换到 ${result.backend}`);
    } catch (switchError) {
      setError(switchError instanceof Error ? switchError.message : String(switchError));
    }
  }

  async function onReinjectTools() {
    try {
      const result = await reinjectTools();
      setNotice(result.injected ? `已重新注入工具示范 ${result.injected} 条` : "已刷新工具 schema 缓存");
    } catch (toolError) {
      setError(toolError instanceof Error ? toolError.message : String(toolError));
    }
  }

  async function onTriggerAutonomous() {
    if (status !== "idle") return;
    try {
      setNotice("");
      const run = await triggerAutonomous("manual");
      setRunStarted(run.run_id, "[AUTO] 自主进化：选择并执行一项有价值的任务");
      startEventStream(run.run_id);
    } catch (autoError) {
      setError(autoError instanceof Error ? autoError.message : String(autoError));
    }
  }

  return (
    <div className="app-shell" onClick={() => historyMenu && setHistoryMenu(null)}>
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">GA</div>
          <div>
            <strong>GenericAgent</strong>
            <span>{settings.backend || "React route"}</span>
          </div>
        </div>

        <button className="primary-action" type="button" onClick={onNewChat}>
          + 新建对话
        </button>

        <div className="panel-switcher">
          <button
            type="button"
            className={sidePanel === "history" ? "active" : ""}
            onClick={() => setSidePanel(sidePanel === "history" ? "" : "history")}
          >
            历史
          </button>
          <button
            type="button"
            className={sidePanel === "memory" ? "active" : ""}
            onClick={() => setSidePanel(sidePanel === "memory" ? "" : "memory")}
          >
            记忆
          </button>
        </div>

        {sidePanel === "history" && (
          <section className="side-section panel-section">
            <h2>对话历史</h2>
            <div className="mini-list">
              {history.slice(0, 10).map((item) => (
                <button
                  key={item.filepath}
                  className="history-button"
                  type="button"
                  onClick={() => onRestoreHistory(item.filename)}
                  onContextMenu={(event) => openHistoryMenu(event, item.filename, item.title || item.filename)}
                  title="左键恢复；右键删除并蒸馏"
                >
                  <span>{item.title || item.filename}</span>
                  <small>{item.mtime_str} / {item.size_kb} KB</small>
                </button>
              ))}
              {history.length === 0 && <p className="muted">暂无历史记录</p>}
            </div>
          </section>
        )}

        {sidePanel === "memory" && (
          <section className="side-section panel-section">
            <h2>记忆系统</h2>
            <div className="mini-list">
              {Object.entries(memory).map(([name, content]) => (
                <details key={name} open={name === "global_mem_insight.txt"}>
                  <summary>{memoryLabel(name)}</summary>
                  <p>{content.slice(0, 1200) || "(empty)"}</p>
                </details>
              ))}
              {Object.keys(memory).length === 0 && <p className="muted">暂无记忆内容</p>}
            </div>
          </section>
        )}

        <section className="side-section">
          <h2>路由策略</h2>
          <div className="segmented">
            {(["auto", "classic", "multi_agent"] as RoutingMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                className={settings.routing_mode === mode ? "active" : ""}
                onClick={() => patchSettings({ routing_mode: mode })}
              >
                {routingLabels[mode]}
              </button>
            ))}
          </div>
        </section>

        <section className="side-section">
          <h2>模型链路</h2>
          <p className="muted current-model">Current: {settings.backend || "unknown"}</p>
          <div className="key-grid">
            {(settings.key_labels.length ? settings.key_labels : ["Default"]).map((label, index) => (
              <button
                key={`${label}-${index}`}
                type="button"
                className={settings.current_key_index === index ? "active" : ""}
                onClick={() => onSwitchKey(index)}
              >
                Key{index + 1}
              </button>
            ))}
          </div>
        </section>

        <section className="side-section">
          <h2>运行控制</h2>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={settings.compact_assistant_history}
              onChange={(event) => patchSettings({ compact_assistant_history: event.currentTarget.checked })}
            />
            <span>压缩助手历史回复</span>
          </label>
          <button className="plain-action" type="button" onClick={onReinjectTools}>
            重新注入工具
          </button>
          <button className="plain-action" type="button" onClick={onStop} disabled={!runId || status === "idle"}>
            强制停止任务
          </button>
        </section>

        <section className="side-section autonomous-card">
          <h2>自主进化</h2>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={settings.autonomous_enabled}
              onChange={(event) => patchSettings({ autonomous_enabled: event.currentTarget.checked })}
            />
            <span>{settings.autonomous_enabled ? "已允许" : "已停止"}</span>
          </label>
          <p className="muted">
            空闲时间：{settings.idle_seconds ? `${settings.idle_seconds} 秒` : "尚未开始计时"}
          </p>
          <button
            className="autonomous-button"
            type="button"
            onClick={onTriggerAutonomous}
            disabled={status !== "idle"}
          >
            立即自主进化
          </button>
        </section>
      </aside>

      <main className="chat-pane">
        <header className="topbar">
          <div>
            <p>Backend: genericagent / {routingLabels[settings.routing_mode]}</p>
          </div>
          <div className={`status-pill status-${status}`}>{status}</div>
        </header>

        <section className="messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Start with a task, paper, experiment, or codebase.</h2>
              <p>The React route listens to structured backend events instead of guessing from Streamlit reruns.</p>
            </div>
          ) : (
            messages.map((message) => {
              const text = renderMessageText(
                message.text,
                {
                  role: message.role,
                  compact: settings.compact_assistant_history,
                  streaming: message.streaming,
                  latestTraceTurn: message.id === traceMessageId ? latestTraceTurn : 0,
                },
              );
              const showTraceHere = message.id === traceMessageId;
              const showFrontierHere = Boolean(frontierState?.enabled)
                && message.role === "assistant"
                && (message.id === traceMessageId || (!traceMessageId && message.id === latestAssistantId));
              const showCopyHere = message.role === "assistant" && message.id === latestAssistantId && Boolean(latestReply);
              return (
                <article key={message.id} className={`message message-${message.role}`}>
                  <div className="message-role">{message.role}</div>
                  {showTraceHere && <TurnTraceList events={events} />}
                  {showFrontierHere && <FrontierStatePanel snapshot={frontierState} />}
                  {text && <MarkdownMessage role={message.role} text={text} />}
                  {showCopyHere && (
                    <div className="message-actions">
                      <button className="message-copy-button" type="button" onClick={copyLastReply}>
                        复制
                      </button>
                    </div>
                  )}
                </article>
              );
            })
          )}
          {needsLiveAssistantMessage && (
            <article className="message message-assistant message-live-trace">
              <div className="message-role">assistant</div>
              {hasTurnTrace ? <TurnTraceList events={events} /> : <p>正在分析任务…</p>}
              {frontierState?.enabled && <FrontierStatePanel snapshot={frontierState} />}
            </article>
          )}
          {error && <div className="error-banner">{error}</div>}
          {notice && !error && <div className="notice-banner">{notice}</div>}
        </section>

        <form
          className="composer"
          onSubmit={onSubmit}
          onDragEnter={onComposerDragEnter}
          onDragOver={onComposerDragOver}
          onDragLeave={onComposerDragLeave}
          onDrop={onComposerDrop}
          aria-label="chat composer"
        >
          <div className={`composer-surface${isDragActive ? " drag-active" : ""}`}>
            {isDragActive && <div className="composer-drop-hint">Drop files to attach</div>}
            {attachments.length > 0 && (
              <div className="composer-attachments">
                {attachments.map((file) => (
                  <span key={file.id} title={file.warning || file.name}>
                    {file.status === "ready" ? "📎" : "⚠"} {file.name}
                  </span>
                ))}
                <button type="button" onClick={clearAttachments}>
                  清空
                </button>
              </div>
            )}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => {
                setInput(event.target.value);
                resizeTextarea(event.currentTarget);
              }}
              onKeyDown={onComposerKeyDown}
              placeholder={status === "idle" ? "any task?" : "Agent is running..."}
              disabled={status !== "idle"}
              rows={1}
            />
            <div className="composer-toolbar">
              <div className="composer-left-actions">
                <label className="attach-button" title="上传附件" aria-label="Upload files">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    onChange={(event) => onFileChange(event.currentTarget.files)}
                    disabled={status !== "idle" || isUploading}
                  />
                  +
                </label>
              </div>
              <div className="composer-right-actions">
                <span className="composer-model-pill" title={settings.backend || "unknown"}>
                  {settings.backend || "GenericAgent"}
                </span>
                {canStop ? (
                  <button type="button" className="stop-button send-button" onClick={onStop}>
                    Stop
                  </button>
                ) : (
                  <button className="send-button" type="submit" disabled={!canSend || isUploading} aria-label="Send">
                    ↑
                  </button>
                )}
              </div>
            </div>
          </div>
        </form>
      </main>

      {historyMenu && (
        <div
          className="history-context-menu"
          style={{ left: historyMenu.x, top: historyMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <strong>{historyMenu.title}</strong>
          <button type="button" onClick={() => onRestoreHistory(historyMenu.filename)}>
            恢复此对话
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => onDistillDeleteHistory(historyMenu.filename)}
          >
            删除并蒸馏
          </button>
          <small>会先写入 memory/history_memory_inbox.md，再删除原历史文件。</small>
        </div>
      )}
    </div>
  );
}

function memoryLabel(name: string) {
  if (name === "global_mem_insight.txt") return "L1: 记忆索引";
  if (name === "global_mem.txt") return "L2: 全局记忆";
  if (name === "history_memory_inbox.md") return "记忆候选池";
  return name;
}
