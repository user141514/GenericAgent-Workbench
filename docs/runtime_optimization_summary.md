# Runtime Optimization Summary

## A. 本轮优化目标

本轮 runtime 优化的目标不是新增更多 agent 或引入新框架，而是先把现有多智能体工作台的主路径做实：

- 降低无效 LLM 调用
- 降低工具 schema 带来的 prompt 成本
- 让简单读取任务走快路径
- 增强 profiler / audit 可观测性
- 防止项目规划类问题给出泛化建议
- 给 memory 写入建立硬边界

## B. 已实际生效的优化

以下能力已经真实接入主流程，默认生效或在开关开启后真实影响运行行为：

| 能力 | 作用 | 关键文件 |
|---|---|---|
| tool schema slimming | 缩小 classic executor 的工具 schema，降低 prompt 负担 | `core/tools/schema_selector.py`, `core/agentmain.py` |
| direct answer | 对窄读取任务直接基于工具结果合成答案，减少最后一轮 classic LLM 总结 | `core/runtime/direct_answer.py`, `core/agent_loop.py` |
| read shortcut | 在进入 classic loop 前识别窄读取任务并走快路径 | `core/runtime/read_shortcut.py`, `core/agentmain.py` |
| orchestrator skip planner follow-up | 当 shortcut 已产出最终答案时，跳过 planner 的二次收尾 | `core/openai_agentmain.py`, `core/agentmain.py` |
| explicit_file_view shortcut | 对“看看/查看/读取/打开/显示 + 明确文件路径”直接走文件查看 shortcut | `core/runtime/read_shortcut.py`, `core/runtime/direct_answer.py` |
| Answer Quality Guard | 对“下一步/架构/短板/路线”类问题注入短状态规则，减少泛化建议 | `core/quality/answer_quality_context.py`, `core/openai_agentmain.py` |
| Memory Write Gate | 把 durable memory 写入权限收紧到 `distiller/promoter/manual_user/system_migration` | `core/memory/write_gate.py`, `core/memory/store.py` |

## C. 可观测性增强

本轮除了快路径，也补了观测层，便于后续决策不靠猜：

| 能力 | 作用 | 关键文件 |
|---|---|---|
| runtime profiler | 记录 run / llm / tool / memory / io / frontend spans 和 events | `core/runtime/profiler.py`, `core/openai_agentmain.py`, `core/agent_loop.py` |
| LLM audit | 记录 prompt chars、history chars、memory chars、tools schema chars、route metadata | `core/runtime/llm_cache.py`, `core/llmcore.py` |
| SkillActivation Log | 记录 selected skills、policy dry-run、memory_write_allowed=false | `core/skills/skill_activation.py`, `core/openai_agentmain.py` |
| tool_call argument metadata | 为 classic tool spans 增加安全参数摘要和 `tool_target_path` | `core/agent_loop.py` |
| read_prefetch analyzer | 离线分析 prefetch 是否值得真正接入上下文 | `core/runtime/analyze_read_prefetch.py`, `docs/read_prefetch_effectiveness.md` |

## D. 暂停推进的能力

以下方向已经评估过，但本阶段明确暂停，不继续扩 runtime：

### read_prefetch context injection

- 现状：`read_prefetch` 已有 detector、runtime metadata、effectiveness analyzer
- 暂停原因：当前唯一 `prefetch=true` 的精确样本里，后续 `file_read` 发生在 classic turn 1
- 结论：`estimated_saved_turns=0`
- 判断：现在还没有足够证据说明把文件内容提前塞进 prompt 会带来真实收益

### ExecutionPolicy runtime enforcement

- 现状：`SkillEffects + ExecutionPolicy` 已经能做 dry-run merge
- 暂停原因：目前只是 policy preview，没有小范围安全接入点
- 判断：如果直接上 runtime enforcement，风险大于收益

### HookRegistry

- 现状：classic executor 已经有 callback / handler 雏形
- 暂停原因：当前还没有足够复杂的 cross-cutting runtime 需求
- 判断：现在上大抽象会先增加复杂度

### 并行 Agent

- 现状：系统已经是 orchestrator + classic executor 的多智能体结构
- 暂停原因：当前主要瓶颈是路径选择、无效调用、prompt 成本，不是 agent 数量不够
- 判断：现在推进并行 agent，容易放大复杂度，而不是解决主要浪费

## E. 已知风险

本轮封版时，需要明确保留这些风险认知：

- `Answer Quality Guard` 的 route override 可能把部分分析类聊天送进 planner
- `Answer Quality Guard` 会增加 prompt chars
- skill SOP 注入会增加 planner prompt
- `read_shortcut` 必须继续保持窄边界，不能膨胀成分析/解释 shortcut
- `Memory Write Gate` 会要求旧代码显式传 `source`

## 本轮实际收益

从本轮已有真实 profile / audit 结果看，收益主要体现在：

- 简单读取类任务可以提前结束，不再白跑 classic 多轮或 planner 收尾
- classic executor 的工具 schema 成本已显著下降
- “项目下一步 / 架构 / 能力短板”类问题不再默认给出并行 agent、动态 agent、长期 agent 记忆这类泛化建议
- 现在可以精确观察：
  - 哪些 LLM 调用最慢
  - 哪些 prompt 最膨胀
  - 哪些工具调用重复
  - 哪些 read_prefetch 命中后后续又读了同一文件
- durable memory 已经有硬边界，skill / agent / tool 不能直接写 `memory_items`

## 本轮结论

这一轮 runtime 优化的结果，不是“让系统更花”，而是：

- 把快路径做实
- 把慢点看清
- 把 durable memory 边界收紧
- 明确哪些方向现在不该继续加

下一阶段更适合做小重构、回归巩固和 Git 清理，而不是继续堆 runtime 新能力。
