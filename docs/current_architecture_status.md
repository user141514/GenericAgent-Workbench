# Current Architecture Status

## 总体定位

GenericAgent Workbench 不是重写 GenericAgent。  
它是在经典 GenericAgent 内核之上，加了一层编排、观测、记忆、技能和产品层。

必须明确这几点：

- classic executor 仍然是实际文件 / 代码 / 浏览器 / 命令执行内核
- OpenAI Agents 层负责 router / planner / chat / handoff
- structured memory 仍是辅助层，旧 global memory 仍是权威注入来源
- `ExecutionPolicy` 目前只是 dry-run
- `read_prefetch` 目前只是 observe-only，不做 context injection

## A. 已生效主流程能力

| 能力 | 说明 | 关键文件 |
|---|---|---|
| RouterRules 快速路由 | 在进入 LLM orchestration 前先做一层 cheap route | `core/router_rules.py`, `core/openai_agentmain.py` |
| `task_router / chat_specialist / planner_executor` | OpenAI Agents 层的主图谱 | `core/openai_agentmain.py` |
| classic executor handoff | planner 可将文件/代码/浏览器任务交给经典 GenericAgent | `core/openai_agentmain.py`, `core/agentmain.py`, `core/agent_loop.py` |
| runtime profiler | 真正记录 spans / events | `core/runtime/profiler.py`, `core/openai_agentmain.py`, `core/agent_loop.py` |
| LLM audit | 记录 prompt chars / route / tool schema 等 | `core/runtime/llm_cache.py`, `core/llmcore.py` |
| tool schema slimming | 缩小 classic 工具 schema | `core/tools/schema_selector.py`, `core/agentmain.py` |
| direct answer | 对窄读取任务跳过最后一轮 classic 总结 | `core/runtime/direct_answer.py`, `core/agent_loop.py` |
| read shortcut | 读取类快路径 | `core/runtime/read_shortcut.py`, `core/agentmain.py` |
| skip planner follow-up | shortcut 已完成时跳过 planner 收尾 | `core/openai_agentmain.py`, `core/agentmain.py` |
| explicit_file_view shortcut | 明确文件查看类请求的快路径 | `core/runtime/read_shortcut.py`, `core/runtime/direct_answer.py` |
| Optional SOP planner 注入 | 只在 planner task-local context 注入 skill SOP | `core/skills/skill_prompt_injector.py`, `core/openai_agentmain.py` |
| Answer Quality Guard | 规划/架构类问题的状态感知 guard | `core/quality/answer_quality_context.py`, `core/openai_agentmain.py` |
| Memory Write Gate | durable memory 写入硬边界 | `core/memory/write_gate.py`, `core/memory/store.py` |

## B. 开关控制能力

| 能力 | 开关 | 关键文件 |
|---|---|---|
| skill SOP 注入 | `GENERIC_AGENT_SKILL_SOP=1` | `core/skills/skill_prompt_injector.py` |
| Answer Quality Guard | `GENERIC_AGENT_ANSWER_QUALITY=1` | `core/quality/answer_quality_context.py` |
| tool schema slimming | `GENERIC_AGENT_SLIM_TOOLS=1` | `core/tools/schema_selector.py` |
| direct answer | `GENERIC_AGENT_DIRECT_ANSWER=1` | `core/runtime/direct_answer.py` |
| read shortcut | `GENERIC_AGENT_READ_SHORTCUT=1` | `core/runtime/read_shortcut.py` |
| early stop | `GENERIC_AGENT_EARLY_STOP=1` | `core/runtime/early_stop.py` |
| profiler 导出 | `GENERIC_AGENT_PROFILE=1` | `core/runtime/profiler.py` |

## C. 基础设施已完成但未接入 runtime 的能力

| 能力 | 当前状态 | 关键文件 |
|---|---|---|
| `SkillEffects` | 只定义 metadata，不影响 runtime | `core/skills/skill_effects.py` |
| `ExecutionPolicy` | 只 merge / preview，不做 enforcement | `core/runtime/execution_policy.py` |
| `SkillActivation` | 只记录 activation log 和 policy preview | `core/skills/skill_activation.py`, `core/openai_agentmain.py` |
| structured memory store | SQLite ledger 已有，但还没接管主 prompt retrieval | `core/memory/store.py`, `core/memory/schema.sql` |
| evidence chunk FTS index | 搜索原始证据可用，但不是主上下文源 | `core/memory/indexer.py`, `core/memory/store.py` |
| LLM cache reuse | audit 已接入，但 `get/set` 还未启用 runtime 复用 | `core/runtime/llm_cache.py` |
| discovered skills layer | 能发现 skill metadata，但不会自动进入 prompt | `core/skills/skill_discovery.py`, `core/skills/skill_parser.py` |
| `read_prefetch` | 目前 observe-only，只做 detector / metadata / analyzer | `core/runtime/read_prefetch.py`, `core/runtime/analyze_read_prefetch.py` |

## D. 只是设计概念 / 后续方向

| 方向 | 当前状态 | 说明 |
|---|---|---|
| tool-backed skill runtime | concept only | 还没有真正把 skill 变成可执行 runtime policy |
| workflow skill | concept only | 尚未实现 |
| reviewer phase injection | concept only | 只有 phase infra，没有 reviewer prompt 注入 |
| dynamic agent spawning | concept only | 不在当前主流程 |
| parallel agent execution | concept only | 当前瓶颈也不在这里 |
| trust-policy marketplace | concept only | 没有 runtime enforcement 链路 |

## 当前的真实执行分层

### 1. Product / Frontend Layer

- `frontends/*`
- 负责 UI、会话交互、产品壳层

### 2. Orchestration Layer

- `core/openai_agentmain.py`
- 负责：
  - route
  - planner
  - chat
  - handoff
  - planner-local context 拼装
  - runtime profiler / audit 汇总

### 3. Classic Execution Kernel

- `core/agentmain.py`
- `core/agent_loop.py`
- `core/ga.py`

负责：
- 文件
- 代码
- 浏览器
- 命令
- 工具 dispatch

### 4. Runtime Observability Layer

- `core/runtime/*`
- 负责：
  - profiler
  - llm audit
  - direct answer
  - early stop
  - read shortcut
  - read_prefetch detect / analyze

### 5. Skills / Governance Layer

- `core/skills/*`
- 负责：
  - skill manifest / taxonomy / selector
  - SOP prompt block
  - activation log
  - policy dry-run

### 6. Memory Layer

- `memory/*`
- `core/memory/*`

其中：
- `memory/*` 里的旧 global memory 仍是权威注入来源
- `core/memory/*` 里的 structured memory 仍然是辅助层

## 当前结论

当前架构不是“缺更多 agent”，而是：

- 主路径已经具备编排 + 执行 + 观测
- 一部分 dry-run 底座已经做好
- 现在更需要封版、回归、清理和小重构

因此，下一步更适合做：

- 小重构
- 文档和 regression 巩固
- Git 清理

而不是继续扩 runtime 新能力。
