# Read Shortcut Regression Set

This document freezes the current `read_shortcut` behavior for narrow file-view requests.

Scope limits:
- no `read_prefetch`
- no analysis / explanation / review shortcut
- no multi-file auto-read
- no long-file summarization

## A. Cases That Should Hit `read_shortcut`

### 1. `看看 core/router_rules.py`
- expected `should_shortcut`: `true`
- expected logical extraction type: `explicit_file_view`
- current serialized `extraction_type`: `explicit_file_view:80`
- expected `line_count`: `80`

### 2. `查看 core/agentmain.py`
- expected `should_shortcut`: `true`
- expected logical extraction type: `explicit_file_view`
- current serialized `extraction_type`: `explicit_file_view:80`
- expected `line_count`: `80`

### 3. `读取 core/agentmain.py 前 20 行`
- expected `should_shortcut`: `true`
- expected logical extraction type: `explicit_file_view`
- current serialized `extraction_type`: `explicit_file_view:20`
- expected `line_count`: `20`

### 4. `打开 README.md`
- expected `should_shortcut`: `true` if `README.md` resolves uniquely inside project root
- expected logical extraction type: `explicit_file_view`
- current serialized `extraction_type`: `explicit_file_view:80`
- expected `line_count`: `80`

## B. Cases That Should Not Hit `read_shortcut`

### 5. `分析 core/agentmain.py 的执行流程`
- expected `should_shortcut`: `false`
- expected reason family: analysis intent blocked

### 6. `查看 core/router_rules.py 并解释逻辑`
- expected `should_shortcut`: `false`
- expected reason family: analysis / explanation intent blocked

### 7. `修改 core/agentmain.py`
- expected `should_shortcut`: `false`
- expected reason family: modification intent blocked

### 8. `优化 core/agent_loop.py`
- expected `should_shortcut`: `false`
- expected reason family: optimization intent blocked

### 9. `读取 ../secret.txt`
- expected `should_shortcut`: `false`
- expected reason: `path_traversal_not_allowed`

### 10. `显示 package.json`
- if `package.json` resolves to multiple matches inside project root:
  - expected `should_shortcut`: `false`
  - expected reason: `ambiguous_filename`
- if only one `package.json` exists:
  - expected `should_shortcut`: `true`
  - expected logical extraction type: `explicit_file_view`

## C. Legacy README Behavior Must Not Regress

### 11. `读取当前项目 README 的第一行标题，然后只用一句话总结项目定位。`
- expected `should_shortcut`: `true`
- expected `extraction_type`: `readme_title_and_positioning`
- expected behavior: old README title / positioning shortcut stays intact
- expected note: must not be overwritten by explicit-file-view logic

## Manual Runtime Validation

Enable:

```powershell
$env:GENERIC_AGENT_READ_SHORTCUT='1'
```

Run these requests:
- `看看 core/router_rules.py`
- `分析 core/router_rules.py 的路由逻辑`
- `读取当前项目 README 的第一行标题，然后只用一句话总结项目定位。`

Record:
- `read_shortcut hit`
- `extraction_type`
- `line_count`
- `classic_executor entered`
- `code_run called`
- `wall_clock_ms`
- `result_correct`

Expected runtime outcomes:
- file-view request should hit shortcut and avoid `code_run`
- analysis request should not shortcut
- legacy README title / positioning shortcut should still hit
