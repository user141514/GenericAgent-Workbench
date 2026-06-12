# React Frontend Route

GenericAgent now has two frontend tracks:

- **Legacy Streamlit track**: `start_local.bat` / `frontends/stapp.py`.
- **React track**: `start_react.bat` for browser development and `start_desktop.bat` for the Electron desktop shell.

The Streamlit track is frozen for new product interactions. It remains available for critical bug fixes, debugging, and fallback use. New chat-composer, upload, streaming, stop, copy, event-trace, memory, and history work should target the React track first.

## Architecture

```text
React UI
  -> HTTP + SSE
FastAPI adapter (`core.api`)
  -> AgentInput / AgentOutputEvent
Existing GenericAgent runtime
```

React owns presentation state. It must consume structured backend events instead of inferring agent behavior from rendered text such as `LLM Running (Turn 1)`.

Electron is the desktop packaging route. React still owns the UI; Electron owns the resizable desktop window and future `.exe` packaging.

## Entrypoints

```bat
start_react.bat
```

Starts:

- FastAPI on `http://127.0.0.1:8765`
- Vite on `http://127.0.0.1:5173`
- default browser at the React app

```bat
start_desktop.bat
```

Starts:

- FastAPI on `http://127.0.0.1:8765`
- Vite on `http://127.0.0.1:5173`
- Electron desktop shell

Use `npm.cmd`, not `npm`, in Windows scripts to avoid PowerShell execution policy failures.

## v1 Scope

The React route v1 supports:

- submit task
- stream events via SSE
- stop current run
- copy latest assistant reply
- upload attachments through JSON/base64
- read history list
- read memory files
- display lightweight execution trace

v1 intentionally supports only one active run at a time. Parallel/multi-session run management should be added after the main event contract is stable.
