# Runtime Regression Matrix

本矩阵用于封版后做固定回归，确保本轮优化不退化。

## 1. 你好

- env vars:
  - 默认即可
- expected route:
  - `chat`
- expected agent:
  - `chat_specialist`
- expected shortcut:
  - none
- expected prefetch metadata:
  - none / `read_prefetch_should_prefetch=false`
- expected skills:
  - none
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - no `answer_quality_context_injected`
  - no `read_shortcut`

## 2. 这样看它的输出质量和你也有差距，怎么去改进呢？

- env vars:
  - `GENERIC_AGENT_ANSWER_QUALITY=1`
- expected route:
  - planner path
- expected agent:
  - `planner_executor`
- expected shortcut:
  - none
- expected prefetch metadata:
  - false / not relevant
- expected skills:
  - optional only, not required
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - `answer_quality_context_injected=true`
  - planner path selected
  - no classic executor unless needed

## 3. 读取当前项目 README 的第一行标题，然后只用一句话总结项目定位。

- env vars:
  - `GENERIC_AGENT_READ_SHORTCUT=1`
  - `GENERIC_AGENT_DIRECT_ANSWER=1`
- expected route:
  - shortcut path
- expected agent:
  - classic fast path; normal classic loop skipped
- expected shortcut:
  - `readme_title_and_positioning`
- expected prefetch metadata:
  - none / false
- expected skills:
  - none
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - `read_shortcut hit`
  - `orchestrator_skip_planner_followup`
  - classic loop skipped

## 4. 看看 core/router_rules.py

- env vars:
  - `GENERIC_AGENT_READ_SHORTCUT=1`
- expected route:
  - explicit file view shortcut
- expected agent:
  - classic shortcut path
- expected shortcut:
  - `explicit_file_view`
- expected prefetch metadata:
  - `read_prefetch_should_prefetch=false`
- expected skills:
  - none
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - `read_shortcut_check`
  - no `code_run`
  - no analysis summary requirement

## 5. 分析 core/router_rules.py 的路由逻辑

- env vars:
  - `GENERIC_AGENT_PROFILE=1`
- expected route:
  - normal planner / classic path
- expected agent:
  - `task_router` -> `planner_executor` -> `classic_executor`
- expected shortcut:
  - no `read_shortcut`
- expected prefetch metadata:
  - `read_prefetch_should_prefetch=true`
  - `read_prefetch_target_file=core/router_rules.py`
- expected skills:
  - none required
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - `read_prefetch_detected`
  - later `tool_call:file_read`
  - analyzer can identify `tool_target_path`

## 6. 修改 core/router_rules.py

- env vars:
  - 默认即可
- expected route:
  - normal executor path
- expected agent:
  - planner / classic normal path
- expected shortcut:
  - no `read_shortcut`
- expected prefetch metadata:
  - `read_prefetch_should_prefetch=false`
- expected skills:
  - none required
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - no `read_prefetch_detected`

## 7. 下一步怎么优化这个项目？

- env vars:
  - `GENERIC_AGENT_ANSWER_QUALITY=1`
  - `GENERIC_AGENT_SKILL_SOP=1` optional
- expected route:
  - planner path
- expected agent:
  - `planner_executor`
- expected shortcut:
  - none
- expected prefetch metadata:
  - false / not relevant
- expected skills:
  - may include `performance-optimization`
  - may include `incremental-implementation`
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - `answer_quality_context_injected=true`
  - if skill SOP enabled, may include `selected_skills`
  - answer should not start with generic AutoGen recommendation

## 8. 这一步怎么验证？

- env vars:
  - `GENERIC_AGENT_SKILL_SOP=1`
- expected route:
  - planner path
- expected agent:
  - `planner_executor`
- expected shortcut:
  - none
- expected prefetch metadata:
  - false / not relevant
- expected skills:
  - `test-driven-development`
- expected memory gate behavior:
  - not involved
- expected profiler / audit markers:
  - planner path
  - skill SOP metadata if enabled

## 9. source="skill" 写 memory_items

- env vars:
  - 默认即可
- expected route:
  - n/a
- expected agent:
  - n/a
- expected shortcut:
  - n/a
- expected prefetch metadata:
  - n/a
- expected skills:
  - n/a
- expected memory gate behavior:
  - reject
  - redirect `memory_candidates`
- expected profiler / audit markers:
  - not required

## 10. source="distiller" 写 memory_items

- env vars:
  - 默认即可
- expected route:
  - n/a
- expected agent:
  - n/a
- expected shortcut:
  - n/a
- expected prefetch metadata:
  - n/a
- expected skills:
  - n/a
- expected memory gate behavior:
  - allowed
- expected profiler / audit markers:
  - not required

## 使用方式

建议把这 10 个 case 当作阶段性封版回归基线：

1. 先跑最窄读取类
2. 再跑规划类 / 质量类
3. 最后跑 memory gate 行为

如果其中任一 case 的 route、shortcut、prefetch metadata、memory gate 结果与这里不一致，就不应继续扩 runtime 能力，应先回到 regression 修复。
