# Protocol Layer Architecture Review

Date: 2026-05-18
Scope: `core/protocol/` + `core/runtime/protocol_bridge.py`

---

## 1. `core/protocol/` 每个文件的职责

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包导出。对外暴露 4 个核心类型：`AgentInput`、`AgentOutputEvent`、`AgentOutputChannel`/`QueueOutputChannel`、`AgentBackend` |
| `events.py` | 定义 `AgentOutputEvent` dataclass — 代理输出的**唯一事件类型**。7 种 event kind（chunk/done/turn_start/turn_end/turn_delta/stopped/error）。提供 `from_legacy_dict()`（旧 raw dict → 新 typed event）和 `to_legacy_dict()`（反向兼容转换）。`is_terminal()` 判断事件是否终止任务 |
| `input.py` | 定义 `AgentInput` dataclass — 代理输入的**唯一请求类型**。替代 `put_task(query, source, images, run_id)` 的散参数。提供 `to_legacy_kwargs()` 反向兼容 |
| `channel.py` | 定义 `AgentOutputChannel` ABC（抽象输出管道，前端消费）+ `QueueOutputChannel` 实现（本地 queue.Queue 封装，sentinel 机制防止阻塞 get）。提供 `from_legacy_queue()` 桥接工厂（后台线程将旧 dict queue 转译为 typed event） |
| `agent.py` | 定义 `AgentBackend` ABC — 所有 agent 必须实现的 6 个方法：`submit(AgentInput) -> AgentOutputChannel`、`abort()`、`is_running`、`get_llm_name()`、`get_key_labels()`、`switch_to_key(n)` |
| `drain.py` | `AgentOutputDrainer` — 统一 10 个前端的队列排空逻辑。`collect(max_items)` 非阻塞轮询、`drain_all()` 阻塞排空、`wait_for_done(timeout)` 等待终止。`from_legacy_queue()` 向后兼容工厂 |
| `formatter.py` | `AgentOutputFormatter` ABC — 解耦 agent loop 中的显示格式化。`NullFormatter`（无标记）、`VerboseFormatter`（markdown turn marker + tool call 格式） |

## 2. 每个文件的依赖列表

| 文件 | 内部依赖（protocol 包内） | 外部依赖 |
|------|--------------------------|----------|
| `__init__.py` | `.events`, `.input`, `.channel`, `.agent` | 无 |
| `events.py` | 无 | stdlib: `dataclasses`, `typing.Any` |
| `input.py` | 无 | stdlib: `dataclasses` |
| `channel.py` | `.events.AgentOutputEvent` | stdlib: `queue`, `abc`, `threading`（仅在 `from_legacy_queue` 内部惰性导入） |
| `agent.py` | `.channel.AgentOutputChannel`, `.input.AgentInput` | stdlib: `abc` |
| `drain.py` | `.channel`, `.events` | stdlib: `queue` |
| `formatter.py` | 无 | stdlib: `abc` |

**关键事实**：整个 `core/protocol/` 的外部依赖**仅限于 Python 标准库**。不依赖 `core.agentmain`、`core.runtime`、`frontends/`、任何第三方库。

## 3. `core/protocol/` 不允许依赖哪些层

`core/protocol/` 是**最底层**的合约层。它**严禁**依赖以下任何层：

| 禁止依赖的层 | 原因 |
|-------------|------|
| `core/runtime/` | runtime 是基础设施层，包含事件日志、状态机、会话持久化。协议层是纯数据契约，不应感知运行时如何记录事件 |
| `core/agentmain.py` / `core/openai_agentmain.py` | 具体的 Agent 实现。协议层定义接口，具体 Agent 实现接口——依赖方向必须反过来 |
| `core/agent_loop.py` | agent 循环包含 LLM 调用、工具派发逻辑。协议层不涉及这些 |
| `core/llmcore.py` | LLM session 层。协议层不应感知 LLM |
| `core/ga.py` | 工具 handler。协议层不应感知工具实现 |
| `frontends/` | 任何前端代码。前端依赖协议，协议不依赖前端 |
| 任何第三方库（除 stdlib） | 协议层必须零外部依赖，确保任何环境下都可导入 |

**允许的依赖**：
- Python stdlib：`abc`、`dataclasses`、`queue`、`threading`、`typing`
- 协议包内部文件：`.events`、`.input`、`.channel`、`.agent`

## 4. 为什么 `runtime_bridge.py` 不应该放在 `core/protocol/`

原实现中 `runtime_bridge.py` 放在 `core/protocol/` 下，存在以下问题：

### 4.1 违反依赖方向

`runtime_bridge.py` 的 `RuntimeEventMapper` 类调用了 `RuntimeHost` 的具体方法：

```python
state = self._host._require_session()   # 调用 RuntimeHost 私有方法
self._host._emit("llm_call_started", ...) # 调用 RuntimeHost 内部方法
self._host.request_tool(...)              # 调用 RuntimeHost 公共方法
self._host.complete_session(...)          # 调用 RuntimeHost 公共方法
```

虽然 `from core.runtime.host import RuntimeHost` 放在 `TYPE_CHECKING` 下（运行时不会执行 import），但这只是**语法上的规避**，不是**架构上的解耦**。实际调用时通过 duck typing 依赖 RuntimeHost 的完整 API surface：

- `_require_session()` — 私有方法，非公开接口
- `_emit()` — 私有方法，非公开接口
- `start_session()`、`request_tool()`、`complete_tool()`、`fail_session()`、`complete_session()`、`request_stop()` — 公共方法

这 8 个方法构成一个**隐式契约**：`RuntimeEventMapper` 假设传入的 `host` 对象必须有这些方法。这个契约属于 runtime 层的内部约定，不应该出现在协议层。

### 4.2 职责错位

`RuntimeEventMapper` 的职责是"把 agent 输出事件转译成 runtime session 记录"。这是**基础设施层的接线逻辑**，不是协议定义。协议只定义"事件是什么形状"，不管"事件被谁怎么消费"。

### 4.3 污染协议层

如果 `runtime_bridge.py` 留在 `core/protocol/`：
- 协议包的认知边界模糊：哪些是纯数据契约？哪些是 runtime 接线？
- 新加入的开发者可能往协议包里放更多 runtime 相关代码
- 代码审查时需要额外判断 `TYPE_CHECKING` 是真解耦还是假解耦

## 5. 为什么移动到 `core/runtime/protocol_bridge.py` 更合理

### 5.1 依赖方向正确

```
core.protocol (纯数据，零 runtime 依赖)
     ▲
     │ from core.protocol.events import AgentOutputEvent
     │
core.runtime.protocol_bridge (接线层)
     ▲
     │ from core.runtime.host import RuntimeHost
     │
core.runtime.host (会话控制面)
```

- `core.runtime` **可以**依赖 `core.protocol`：runtime 是上层，protocol 是底层
- `core.runtime.protocol_bridge` **可以**同时依赖 `core.protocol` 和 `core.runtime.host`：它是 runtime 层内部的接线模块
- `core.protocol` **不**依赖任何 runtime 模块：协议层保持干净

### 5.2 与现有 runtime `__init__.py` 集成

`core/runtime/__init__.py` 已经导出了 30+ 个符号（`RuntimeHost`、`RuntimeEvent`、`ModeStateMachine`、`ExecutionPolicy` 等）。`RuntimeEventMapper` 作为 runtime 的对外 API 之一，在此导出是自然的：

```python
from .protocol_bridge import RuntimeEventMapper
```

### 5.3 测试隔离更清晰

| 测试目标 | 需要 mock 的层 |
|----------|---------------|
| `test_protocol_events.py` | 无（纯数据） |
| `test_protocol_channel.py` | 无（纯数据 + queue） |
| `test_runtime_mapper.py` | 可能需要 mock RuntimeHost |

如果 mapper 在 protocol 包内，protocol 测试就需要感知 runtime 类型，破坏了测试隔离。

## 6. 当前依赖方向图

```
                        ┌──────────────────────────────────┐
                        │         Python stdlib              │
                        │  abc, dataclasses, queue, typing   │
                        └──────────┬───────────────────────┘
                                   │ 依赖（允许）
                                   ▼
                        ┌──────────────────────────────────┐
                        │     core/protocol/   (协议层)      │
                        │                                  │
                        │  events.py   input.py             │
                        │  channel.py  agent.py             │
                        │  drain.py    formatter.py         │
                        │                                  │
                        │  外部依赖: stdlib only             │
                        │  禁止依赖: core.runtime,           │
                        │           core.agentmain,          │
                        │           frontends/               │
                        └───────┬──────────────────────────┘
                                │ 依赖（允许：上层依赖下层）
            ┌───────────────────┼───────────────────┐
            │                   │                   │
            ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ core/runtime/    │ │ core/agentmain/  │ │ frontends/       │
│                  │ │                  │ │                  │
│ host.py          │ │ GeneraticAgent   │ │ stapp.py         │
│ event_schema.py  │ │ (future:         │ │ stapp_mobile.py  │
│ state_machine.py │ │  implements      │ │ qtapp.py         │
│ protocol_        │ │  AgentBackend)   │ │ ...              │
│ bridge.py  ◄──────│                  │ │                  │
│ (接线层)         │ │                  │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘

依赖规则:
  core.protocol  ←  core.runtime      ✅ 允许
  core.protocol  ←  core.agentmain    ✅ 允许
  core.protocol  ←  frontends/        ✅ 允许
  core.runtime   ←  core.protocol     ❌ 禁止（protocol 是底层）
  frontends/     ←  core.protocol     ❌ 禁止
```

## 7. 下一阶段允许做什么、不允许做什么

### 允许

| 允许的操作 | 原因 |
|-----------|------|
| 在 `core/runtime/protocol_bridge.py` 中新增方法 | runtime 层可以扩展桥接逻辑 |
| 在 `core/runtime/__init__.py` 中导出 `RuntimeEventMapper` | 作为 runtime 公开 API |
| 在 `core/agentmain.py` 中 `from core.protocol import AgentInput, AgentOutputChannel, AgentBackend` | agent 实现协议 |
| 在 `core/agentmain.py` 中 `from core.runtime.protocol_bridge import RuntimeEventMapper` | agent 使用 runtime 桥接 |
| 在 `frontends/` 中 `from core.protocol import AgentInput, AgentOutputDrainer` | 前端消费协议 |
| 扩展 `core/protocol/events.py` 新增 event kind | 协议演进 |
| 在 `core/protocol/drain.py` 中新增 drain 方法 | 纯工具函数 |
| 创建 `core/agent_factory.py`（Phase 5 plan） | 工厂函数属于 agent 层 |

### 禁止

| 禁止的操作 | 原因 |
|-----------|------|
| 在 `core/protocol/` 任何文件中 `import core.runtime` | 违反依赖方向，协议层不能依赖运行时 |
| 在 `core/protocol/` 任何文件中 `import core.agentmain` | 协议层不能依赖具体 agent |
| 在 `core/protocol/` 任何文件中 `import frontends` | 协议层不能依赖 UI |
| 在 `core/protocol/` 新增第三方库依赖 | 协议层必须保持零外部依赖（stdlib only） |
| 在 agent loop（`core/agent_loop.py`）中 import 任何 `frontends/` 模块 | agent loop 不能依赖前端 |
| 在 agent loop 中使用 `time.sleep(get_frontend_turn_gap_seconds())` 或类似的前端 pacing 逻辑 | 前端关注点必须通过 protocol 层注入（formatter/throttle） |
| 在前端中直接 `from core.agentmain import GeneraticAgent`（新代码） | 新代码应通过 `agent_factory.load_agent()` 或直接依赖 `AgentBackend` ABC |
| 删除 `put_task()` | 向后兼容：`put_task()` 保留但标记 deprecated，内部调用 `submit()` |
