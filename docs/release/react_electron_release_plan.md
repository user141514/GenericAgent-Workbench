# React / Electron Release Plan

This plan prepares GenericAgent for a safe React/Electron desktop route and a
future npm distribution path. It deliberately keeps Streamlit as a legacy
fallback and avoids publishing the whole repository.

## Release Surfaces

| Surface | Audience | Status | Boundary |
|---|---|---:|---|
| Streamlit legacy | local debug/admin fallback | frozen | Keep `start_local.bat`; only critical fixes. |
| React web app | local development | active | `frontends/react_app`, served by Vite. |
| FastAPI backend | local agent API | active | Must bind to `127.0.0.1` by default. |
| Electron desktop | end-user desktop shell | active candidate | Loads React app, talks to local FastAPI. |
| npm package | installer/dev package | gated | Publishes a minimal desktop package with built React assets and a sanitized backend snapshot, not the repo root. |
| Windows exe | end-user desktop package | active candidate | Bundles Electron, React, sanitized backend, and embedded Python runtime. |

## Architecture Decisions

- npm must not publish the repository root.
- User data directories such as `temp/`, `logs/`, and runtime memory files must
  never be included in publish artifacts.
- Secret-bearing local files such as `mykey.py`, `mykey.json`, `.env`, `*.token`,
  and `*.secret` must be excluded by package whitelist and scanner.
- The Electron package includes built frontend assets, Electron shell code, and
  a sanitized Python backend snapshot under `backend/`.
- The npm package may create a per-user Python virtual environment on first run
  and install the bundled backend requirements there.
- The Python interpreter itself remains an explicit local runtime dependency
  until a future exe/embedded-Python distribution is tested.
- The Windows exe route uses `python-runtime/` as an Electron `extraResources`
  directory, so double-click launch can start FastAPI without relying on a
  system Python installation.

## Quality Gates

### Security

- Secret pattern scan on release candidates.
- npm/electron manifest whitelist check.
- Upload API path, size, and parse-failure tests.
- History/memory path guard tests.
- Localhost-only API binding and CORS review.

### Performance

- React build size and production build success.
- Long markdown reply rendering.
- Turn trace rendering with many turns.
- API run creation latency.
- SSE first event latency.
- Stop request latency.
- Electron cold start and shutdown cleanup.

### Packaging

- `npm pack --dry-run` must be inspected before any real publish.
- `package.json` for any publishable package must define `files`.
- `postinstall` should be avoided unless explicitly reviewed.
- Package tarball must not contain `temp/`, `logs/`, `memory/`, `.env*`,
  `mykey*`, or model response logs.

## First Implementation Slice

This slice adds:

- `tools/security_scan.py`
- `tools/performance_gate.py`
- `tools/release_gate.ps1`
- `tests/security/test_security_scan.py`
- `tests/performance/test_performance_gate.py`

It does not publish or package anything. The goal is to make release safety
and basic performance budgets repeatable before adding npm package scaffolding.

Run the current gate with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_gate.ps1
```

## npm Package Shape

Current v0.2 package shape:

```text
packages/
  gagent-desktop/
    package.json
    README.md
    bin/
      gagent-desktop.js
    electron/
      main.cjs
    dist/
    backend/
      core/
      frontends/
      assets/
      memory/
      requirements.txt
```

This package is a minimal desktop app distribution. It bundles the React build,
Electron shell, and a sanitized backend snapshot. It does not publish the
repository root and does not include local runtime data, logs, model responses,
SQLite memory stores, raw history, `.env*`, or `mykey*` files.

Default user flow:

```powershell
npm install -g gagent-desktop
gagent-desktop
```

First launch uses the packaged backend by default. If the backend Python
environment does not exist, the launcher creates it under
`~/.gagent-desktop/python-env` and installs `backend/requirements.txt`.
Users can also prepare it explicitly:

```powershell
gagent-desktop setup
```

Development override remains available:

```powershell
gagent-desktop --repo F:\GAgent-Multi --python D:\anaconda0\python.exe
```

Prepare the package with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepare_gagent_desktop_package.ps1
```

Verify package contents with:

```powershell
D:\anaconda0\python.exe tools\npm_pack_audit.py --package-dir packages\gagent-desktop
cd packages\gagent-desktop
npm publish --dry-run
```

The package should be published only after:

1. React/Electron local release gate is green.
2. `npm pack --dry-run` content is clean.
3. A package name and install story are chosen.
4. Backend dependency handling is documented and the Python runtime prerequisite
   is explicit.

## Windows Exe Package Shape

Current exe build route:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_gagent_desktop_windows.ps1
```

The script:

1. Builds/copies the React UI into `packages/gagent-desktop/dist`.
2. Rebuilds the sanitized backend snapshot.
3. Downloads the Python embeddable runtime into `packages/gagent-desktop/python-runtime`.
4. Installs backend requirements into that embedded runtime.
5. Runs `electron-builder` to produce a Windows portable package.

For a fast structure-only smoke test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_gagent_desktop_windows.ps1 -SkipDependencyInstall -DirOnly
```

The Electron main process starts the backend itself when `/api/status` is not
healthy, using `python-runtime/python.exe` from packaged resources before
falling back to `GAGENT_PYTHON` or system `python`.

`packages/gagent-desktop/scripts/run-electron-builder.cjs` sets default
Electron download mirrors for Windows/China-friendly builds:

```text
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
```

Environment variables provided by the caller take precedence.
