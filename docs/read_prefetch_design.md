# Read Prefetch Design

`read_prefetch` is a dry-run detector for requests that likely need a single file to be read before answering, but are not safe for `read_shortcut`.

## Difference Between `read_shortcut` and `read_prefetch`

`read_shortcut`:
- is for narrow file-view or README title extraction requests
- can directly return an answer
- is allowed to bypass later LLM work in a very small set of cases

`read_prefetch`:
- is for analysis / explanation / understanding requests about one explicit file
- does **not** read the file in v1
- does **not** answer directly
- does **not** skip LLM
- does **not** inject prompt context
- does **not** change planner or classic executor behavior

## Why V1 Is Dry-Run Only

V1 is intentionally metadata-only because the risk surface is higher than `read_shortcut`:
- analysis requests often need judgment, not just raw file display
- wrong prefetch can bloat context or bias the answer
- ambiguous filenames or mixed action requests should fail closed
- current runtime already has multiple routing and shortcut layers; prefetch should be observed before it is connected

So v1 only emits a `ReadPrefetchDecision`.

## Match Conditions

`read_prefetch` matches only when all of the following are true:

1. The query has analysis / explanation / understanding intent, such as:
   - `分析`
   - `解释`
   - `梳理`
   - `理解`
   - `执行流程`
   - `代码结构`
   - `路由逻辑`
   - `turn loop`
   - `workflow`
   - `看看 ... 逻辑`
   - `看看 ... 执行流程`

2. The query contains one explicit file path or filename, for example:
   - `core/router_rules.py`
   - `core/agent_loop.py`
   - `core/openai_agentmain.py`
   - `README.md`

3. The file exists inside `project_root`.

4. The file extension is one of:
   - `.py`
   - `.md`
   - `.txt`
   - `.json`
   - `.yaml`
   - `.yml`
   - `.toml`

## Exclusion Conditions

`read_prefetch` must not trigger when:
- the query contains action / execution intent:
  - `修改`
  - `修复`
  - `实现`
  - `重构`
  - `优化`
  - `删除`
  - `写入`
  - `patch`
  - `运行`
  - `测试`
  - `部署`
  - `安装`
- the filename resolves to multiple files
  - reason: `ambiguous_filename`
- the path is absolute or uses parent traversal
  - reason: `unsafe_path`
- there is no explicit file
  - no prefetch

## Output Shape

The detector returns:
- `should_prefetch`
- `target_file`
- `reason`
- `confidence`
- `max_lines`
- `max_chars`
- `signals`

`max_lines` and `max_chars` are advisory only in v1. They are not enforced anywhere yet.

## Possible Future Integration Points

If later connected, likely integration points are:
- planner task-local context
- classic `initial_user_content`
- max-chars clipping before file injection
- profile / audit metadata for hit-rate and false-positive analysis

Those are future directions only. V1 does not connect to any of them.
