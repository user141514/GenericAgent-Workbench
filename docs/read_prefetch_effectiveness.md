# Read Prefetch Effectiveness

## Purpose

`read_prefetch` 目前只做 dry-run 检测，不读取文件、不注入 prompt、不改变 runtime 行为。  
这个 analyzer 的作用是离线回答一个更实际的问题：

- `read_prefetch` 命中后，后续真实执行里是否又出现了同文件 `file_read`
- 如果经常出现，是否值得把 `read_prefetch` 真正接到 planner 或 classic 的上下文准备阶段

## Why Analyze Before Integrating

先分析，再接入，有两个原因：

1. 当前系统已经有 `read_shortcut`、`direct_answer`、tool schema slimming、Answer Quality Guard。  
   继续把文件内容提前塞进 prompt，只有在它确实能减少后续 turn 或重复 `file_read` 时才值得。

2. `read_prefetch` 的目标不是“看起来更智能”，而是减少重复工作。  
   如果它只是在第一轮就会正常 `file_read`，那提前注入未必有收益，反而可能增加 prompt 膨胀。

## CLI

```bash
python -m core.runtime.analyze_read_prefetch
python -m core.runtime.analyze_read_prefetch --run-id prefetch_utf_a_20260429
python -m core.runtime.analyze_read_prefetch --profiles-dir temp/profiles --audit-file temp/llm_cache/records.jsonl --limit 20
```

## What It Tries To Infer

按 run 聚合这些信息：

- `read_prefetch_should_prefetch`
- `read_prefetch_target_file`
- `read_prefetch_reason`
- `read_prefetch_confidence`
- `selected_agent`
- `total_duration_ms`
- `llm_call_count`
- `classic_executor_call_count`
- `tool_calls`
- 是否后续出现 `tool_call:file_read`
- 是否很可能读取了同一个目标文件
- `file_read` 大致出现在第几 turn
- `read_prefetch_potentially_useful`
- `estimated_saved_turns`

## Matching Strategy

v1 analyzer 主要依赖保守的 preview 推断：

- `read_prefetch_should_prefetch=true`
- 后续出现 `tool_call:file_read`
- 且 classic audit preview 提到了同一个目标文件

新版 analyzer 优先使用更精确的 profiler metadata：

- `tool_call:file_read` span 的 `tool_target_path`
- `tool_call_result` event 的 `tool_target_path`

优先级是：

1. `exact_tool_target_match`
2. `fallback_preview_mentions_target`
3. `insufficient_tool_metadata`

也就是说，现在只有在 tool span / event 明确记录到同一个目标文件时，才会优先判成精确匹配。  
如果老样本没有这些字段，才回退到 preview 推断。

## Recommended Gate For Real Integration

只有当最近 N 个 `prefetch=true` 的 run 中：

- 至少 50% 后续又读取了同一个文件
- 且其中至少一部分 `file_read` 发生在 `turn >= 2`

才建议考虑下一步做真正的 `read_prefetch` context injection。

如果大多数 `file_read` 都发生在 classic turn 1，那么接入收益就偏弱，更可能只是把相同内容更早塞进 prompt。

另外，只有当 `exact_tool_target_match` 的样本数量足够多时，才值得认真评估 context injection；  
如果长期只能靠 preview 推断，说明 observability 还不够扎实，应该先补数据再决定是否接入。

## Possible Future Integration Points

当前还没有接入。后续如果数据支持，可以考虑：

- planner task-local context
- classic `initial_user_content`
- 基于 `max_chars` 的预读取裁剪
- profile / audit 的更细粒度 `file_read` 参数记录

## Decision Standard

推荐顺序：

1. 先跑 analyzer 看最近样本
2. 如果 `same_file_read` 比例低，不接
3. 如果比例高，但大多发生在 `turn 1`，谨慎接
4. 只有当重复读取明显且发生在后续 turn，才考虑做受控注入实验
