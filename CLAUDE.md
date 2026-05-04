# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- Python 3.11+ in conda env `rag-env`: `E:\Anaconda3\envs\rag-env\python.exe`
- Use direct interpreter paths, never assume `python` means the project interpreter
- Test runner: `E:\Anaconda3\envs\rag-env\python.exe -m pytest tests/ -v`
- Lint: `ruff check core/` (target-version py310, line-length 120)

## Token Optimization (RTK)

Prefix all shell commands with `rtk` — it filters output before reaching the LLM context.

```bash
rtk git status          # Compact git output (~59% savings)
rtk git diff            # Compact diff (~80% savings)
rtk pytest tests/ -v    # Failures only (~90% savings)
rtk ls -la              # Tree format (~65% savings)
rtk grep "pattern"      # Grouped by file (~75% savings)
rtk err <command>       # Show only errors from any command
```

`rtk` is a passthrough — commands it doesn't recognize pass through unchanged.

## Architecture (Big Picture)

This is a **workbench** built around the GenericAgent execution kernel. It is NOT a rewrite of GenericAgent.

```
User / Bot / UI
  → Frontends (Streamlit, Telegram, Feishu, WeChat Work, etc.)
    → Backend dispatch (BACKEND_KIND env var)
      ├── Classic: core/agentmain.py → agent_loop.py → ga.py (tools)
      └── OpenAI Agents: core/openai_agentmain.py → task_router/chat_specialist/planner_executor
            → run_genericagent_executor → still delegates to classic executor for files/code/browser/shell
```

### 6 execution layers

1. **Frontend Layer** (`frontends/`): `stapp.py` (main Streamlit workbench), `chatapp_common.py` (restore/distill/delete), `file_processor.py` (PDF/DOCX/text attachments), plus Bot apps
2. **Orchestration Layer** (`core/openai_agentmain.py`, 3068 lines): Multi-agent routing via OpenAI Agents SDK. `task_router` → `chat_specialist` (simple) or `planner_executor` (complex). All real work goes through `run_genericagent_executor` → classic executor
3. **Classic Execution Kernel** (`core/agentmain.py`, `core/agent_loop.py`, `core/ga.py`): The actual file/code/browser/shell executor. `ga.py` is the God Node (600 lines, 37+ edges in tool dispatch) — changes must be surgical
4. **Runtime Observability** (`core/runtime/`): `profiler.py`, `llm_cache.py`, `read_prefetch.py`, `read_shortcut.py`, `direct_answer.py`, `early_stop.py`, `execution_policy.py`
5. **Skills/Governance** (`core/skills/`): Skill manifest, discovery, selector, prompt injection, activation log, policy dry-run
6. **Memory Layer**: Old `memory/` text files (global_mem L1/L2 — authoritative injection source) + new `core/memory/` structured SQLite store (FTS5, auxiliary, no caller yet)

### Key design constraints

- **Classic GenericAgent is the default**. `launch.pyw` does NOT set `GA_AGENT_BACKEND` → defaults to `"genericagent"`
- **OpenAI Agents is opt-in**. Only `start_test.pyw` explicitly sets `GA_AGENT_BACKEND=openai-agents`
- **The execution engine is always the same**. Even in OpenAI Agents mode, all file/code/browser/shell work goes through `run_genericagent_executor` → classic `GeneraticAgent`
- **LLM config loading order**: `mykey.py` → `mykey.json` → `.env` env vars → `~/.claude/settings.json`
- **Frontend dynamic routing**: `RouterRules` keyword match → complex tasks (code/review/research) show "Use Planner / Direct Exec" choice. Classic-only mode via sidebar checkbox

## Commands

```bash
# Desktop launcher (classic backend)
python launch.pyw

# OpenAI Agents backend
python start_test.pyw

# Streamlit-only (port 3003, localhost)
E:\Anaconda3\envs\rag-env\python.exe -m streamlit run frontends/stapp.py --server.port 3003 --server.address localhost --server.headless true

# Bot frontends
python frontends/tgapp.py       # Telegram
python frontends/fsapp.py       # Feishu
python frontends/wecomapp.py    # WeChat Work
python frontends/dingtalkapp.py # DingTalk

# Full test suite
E:\Anaconda3\envs\rag-env\python.exe -m pytest tests/ -v

# Single test file
E:\Anaconda3\envs\rag-env\python.exe -m pytest tests/unit/test_read_prefetch.py -v

# Lint
ruff check core/
ruff format core/ --check
```

## Dual Backend — Critical Facts

- `GA_AGENT_BACKEND` is read **once at import time** in `stapp.py:32`. No runtime switching
- Classic path: `agent_runner_loop()` in `agent_loop.py` checks `stop_event` between turns, injects `get_global_memory()` into system prompt
- OpenAI path: `_build_agent_graph()` in `openai_agentmain.py` assembles agent graph with RouterRules → skill SOP → answer quality → read prefetch context blocks. Actual execution through `_run_classic_executor_task()`
- `generaticagent` and `openai-agents` are the only valid values for `GA_AGENT_BACKEND`

## Environment Variables (P2 Runtime Switches)

| Variable | Default | Effect |
|---|---|---|
| `GA_AGENT_BACKEND` | `genericagent` | Backend selection |
| `GENERIC_AGENT_READ_PREFETCH` | off (`!= "1"`) | File prefetch context injection |
| `GENERIC_AGENT_EXECUTION_POLICY` | `observe` | Policy mode: off/observe/soft/hard |
| `GENERIC_AGENT_LLM_CACHE` | off | LLM semantic cache reuse |
| `GENERIC_AGENT_STRUCTURED_MEMORY` | off | SQLite FTS5 memory search |
| `GENERIC_AGENT_SKILL_SOP` | off | Skill SOP prompt injection |
| `GENERIC_AGENT_ANSWER_QUALITY` | off | Answer quality guard |
| `GENERIC_AGENT_SLIM_TOOLS` | off | Tool schema slimming |
| `GENERIC_AGENT_DIRECT_ANSWER` | off | Narrow read direct answer |
| `GENERIC_AGENT_READ_SHORTCUT` | off | File read fast path |
| `GENERIC_AGENT_EARLY_STOP` | off | Early stop in classic executor |
| `GENERIC_AGENT_PROFILE` | off | Profiler export |

## God Node Protection (ga.py)

`core/ga.py` is the classic executor's tool dispatch handler with 37+ methods. Rules:
- Append new `do_*` methods only — never modify existing ones without explicit approval
- Use soft imports (`import` inside method body) for new dependencies
- Insert new methods after the last related `do_*` method, before the next unrelated one
- Every `do_*` method must return `StepOutcome` and may `yield` progress lines
- `_build_llm_config` style helpers go right after their `do_*` method

## Secrets

- `mykey.py` — gitignored, contains real API keys. Template: `mykey_template.py`
- `.env` — gitignored, environment variable config. Template: `.env.template`
- `.gitignore` has layered rules: positive includes (`!core/**`, `!memory/*.py`) with re-exclusions
- Never print real key values in output

## Git Conventions (from workflow.md)

- Branches: `<type>/<short-description>` (feat/fix/refactor/docs/test/chore)
- Commits: Conventional Commits `<type>(<scope>): <description>`
- Valid scopes: agent, ga, llmcore, runtime, memory, skills, tools, quality, frontend, docs, config
- Squash merge to main, delete branch after merge
- Each commit should keep the project runnable
