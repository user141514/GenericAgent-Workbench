#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const PACKAGED_BACKEND = path.join(PACKAGE_ROOT, "backend");
const PACKAGED_PYTHON_RUNTIME = path.join(PACKAGE_ROOT, "python-runtime");
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;

function parseArgs(argv) {
  const args = {
    repo: "",
    python: process.env.GAGENT_PYTHON || "python",
    host: process.env.GA_REACT_API_HOST || DEFAULT_HOST,
    port: Number(process.env.GA_REACT_API_PORT || DEFAULT_PORT),
    dryRun: false,
    json: false,
    noApi: false,
    noSetup: false,
    setup: false,
    help: false,
  };

  const rest = [...argv];
  if (rest[0] === "setup") {
    args.setup = true;
    rest.shift();
  }

  for (let index = 0; index < rest.length; index += 1) {
    const item = rest[index];
    if (item === "--repo") args.repo = String(rest[++index] || "");
    else if (item === "--python") args.python = String(rest[++index] || "");
    else if (item === "--host") args.host = String(rest[++index] || DEFAULT_HOST);
    else if (item === "--port") args.port = Number(rest[++index] || DEFAULT_PORT);
    else if (item === "--dry-run") args.dryRun = true;
    else if (item === "--json") args.json = true;
    else if (item === "--no-api") args.noApi = true;
    else if (item === "--no-setup") args.noSetup = true;
    else if (item === "--help" || item === "-h") args.help = true;
    else fail(`Unknown argument: ${item}`);
  }
  return args;
}

function usage() {
  return [
    "Usage: gagent-desktop [setup] [options]",
    "",
    "Options:",
    "  setup             Create/update the bundled backend Python environment and exit.",
    "  --repo <path>     Optional external GAgent-Multi checkout. Defaults to packaged backend.",
    "  --python <path>   Python executable for setup. Defaults to GAGENT_PYTHON or python.",
    "  --host <host>     API host. Default: 127.0.0.1.",
    "  --port <port>     API port. Default: 8765.",
    "  --no-api          Do not start backend; require an existing healthy API.",
    "  --no-setup        Do not auto-create the bundled backend Python environment.",
    "  --dry-run         Print planned launch configuration and exit.",
    "  --json            Print dry-run output as JSON.",
    "  -h, --help        Show this help.",
  ].join("\n");
}

function findRepoRoot(explicitRepo) {
  const candidates = [explicitRepo, process.env.GAGENT_HOME, PACKAGED_BACKEND, process.cwd()].filter(Boolean);

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (isGAgentRepo(resolved)) {
      return resolved;
    }
  }
  return "";
}

function isGAgentRepo(repo) {
  return fs.existsSync(path.join(repo, "core", "api", "server.py"));
}

function buildConfig(args) {
  const repo = findRepoRoot(args.repo);
  const packagedBackend = isGAgentRepo(PACKAGED_BACKEND);
  const usesPackagedBackend = Boolean(repo) && path.resolve(repo) === path.resolve(PACKAGED_BACKEND);
  const venvDir = path.join(getStateDir(), "python-env");
  const venvPython = resolveVenvPython(venvDir);
  const embeddedPython = resolveEmbeddedPython(PACKAGED_PYTHON_RUNTIME);
  const hasEmbeddedPython = fs.existsSync(embeddedPython);
  const hasPythonEnv = fs.existsSync(venvPython);
  const python = usesPackagedBackend && hasEmbeddedPython
    ? embeddedPython
    : usesPackagedBackend && hasPythonEnv
      ? venvPython
      : args.python;
  const apiUrl = `http://${args.host}:${args.port}`;
  const requirements = repo ? resolveRequirementsFile(repo) : "";
  return {
    packageRoot: PACKAGE_ROOT,
    repo,
    repoSource: args.repo ? "arg" : process.env.GAGENT_HOME ? "env" : usesPackagedBackend ? "packaged" : repo ? "auto" : "missing",
    packagedBackend,
    usesPackagedBackend,
    python,
    setupPython: args.python,
    embeddedPython,
    hasEmbeddedPython,
    venvDir,
    venvPython,
    requirements,
    apiHost: args.host,
    apiPort: args.port,
    apiUrl,
    noApi: args.noApi,
    noSetup: args.noSetup,
    dist: path.join(PACKAGE_ROOT, "dist"),
    electronMain: path.join(PACKAGE_ROOT, "electron", "main.cjs"),
  };
}

function resolveRequirementsFile(repo) {
  const desktopRequirements = path.join(repo, "requirements-desktop.txt");
  if (fs.existsSync(desktopRequirements)) {
    return desktopRequirements;
  }
  return path.join(repo, "requirements.txt");
}

function dryRunOutput(config, json) {
  const payload = {
    ok: Boolean(config.repo) && fs.existsSync(path.join(config.dist, "index.html")),
    packageRoot: config.packageRoot,
    repo: config.repo,
    repoSource: config.repoSource,
    python: config.python,
    apiUrl: config.apiUrl,
    noApi: config.noApi,
    dist: config.dist,
    electronMain: config.electronMain,
    hasReactDist: fs.existsSync(path.join(config.dist, "index.html")),
    hasBackend: Boolean(config.repo),
    packagedBackend: config.packagedBackend,
    usesPackagedBackend: config.usesPackagedBackend,
    embeddedPython: config.embeddedPython,
    hasEmbeddedPython: config.hasEmbeddedPython,
    venvDir: config.venvDir,
    venvPython: config.venvPython,
    hasPythonEnv: fs.existsSync(config.venvPython),
    requirements: config.requirements,
  };
  if (json) {
    console.log(JSON.stringify(payload, null, 2));
  } else {
    for (const [key, value] of Object.entries(payload)) {
      console.log(`${key}: ${value}`);
    }
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return 0;
  }

  const config = buildConfig(args);
  if (args.dryRun) {
    dryRunOutput(config, args.json);
    return config.repo && fs.existsSync(path.join(config.dist, "index.html")) ? 0 : 1;
  }

  if (!config.repo) {
    fail("Packaged backend is missing. Reinstall gagent-desktop or pass --repo to a GAgent-Multi checkout.");
  }
  if (!fs.existsSync(path.join(config.dist, "index.html"))) {
    fail("Packaged React dist is missing. Prepare the npm package before launching.");
  }

  if (args.setup) {
    await ensurePythonEnvironment(config, { force: true });
    return 0;
  }

  let backendProcess = null;
  const healthy = await isApiHealthy(config.apiUrl);
  if (!healthy) {
    if (args.noApi) {
      fail(`No healthy API at ${config.apiUrl}, and --no-api was set.`);
    }
    await ensurePythonEnvironment(config, { force: false });
    const busy = await isPortBusy(config.host, config.port);
    if (busy) {
      fail(`Port ${config.port} is occupied, but ${config.apiUrl}/api/status is not healthy.`);
    }
    backendProcess = startBackend(config);
    try {
      await waitForApi(config.apiUrl, 30_000);
    } catch (error) {
      backendProcess.kill();
      throw error;
    }
  }

  try {
    return await launchElectron(config);
  } finally {
    if (backendProcess) {
      backendProcess.kill();
    }
  }
}

async function ensurePythonEnvironment(config, { force }) {
  if (!config.usesPackagedBackend || config.noSetup) {
    return;
  }
  if (config.hasEmbeddedPython) {
    return;
  }
  if (!force && fs.existsSync(config.venvPython)) {
    return;
  }
  if (!fs.existsSync(config.requirements)) {
    fail(`Bundled backend requirements are missing: ${config.requirements}`);
  }
  fs.mkdirSync(config.venvDir, { recursive: true });
  if (!fs.existsSync(config.venvPython)) {
    await runCommand(config.setupPython, ["-m", "venv", config.venvDir], {
      cwd: config.repo,
      label: "create Python environment",
    });
  }
  await runCommand(config.venvPython, ["-m", "pip", "install", "--upgrade", "pip"], {
    cwd: config.repo,
    label: "upgrade pip",
  });
  await runCommand(config.venvPython, ["-m", "pip", "install", "-r", config.requirements], {
    cwd: config.repo,
    label: "install backend requirements",
  });
}

function startBackend(config) {
  const child = spawn(
    config.python,
    ["-m", "core.api.server", "--host", config.apiHost, "--port", String(config.apiPort)],
    {
      cwd: config.repo,
      stdio: "inherit",
      env: {
        ...process.env,
        GA_REACT_API_HOST: config.apiHost,
        GA_REACT_API_PORT: String(config.apiPort),
      },
    },
  );
  child.on("error", (error) => {
    fail(`Failed to start backend: ${error.message}`);
  });
  return child;
}

function launchElectron(config) {
  const electronPath = require("electron");
  const child = spawn(electronPath, [config.packageRoot], {
    stdio: "inherit",
    env: {
      ...process.env,
      GA_REACT_API_HOST: config.apiHost,
      GA_REACT_API_PORT: String(config.apiPort),
    },
  });
  return new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code) => resolve(code || 0));
  });
}

function runCommand(command, args, { cwd, label }) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: "inherit", env: process.env });
    child.on("error", (error) => reject(new Error(`Failed to ${label}: ${error.message}`)));
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Failed to ${label}: exit code ${code}`));
    });
  });
}

function getStateDir() {
  if (process.env.GAGENT_DESKTOP_STATE_DIR) {
    return path.resolve(process.env.GAGENT_DESKTOP_STATE_DIR);
  }
  const home = process.env.USERPROFILE || process.env.HOME || process.cwd();
  return path.join(home, ".gagent-desktop");
}

function resolveVenvPython(venvDir) {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function resolveEmbeddedPython(runtimeDir) {
  return process.platform === "win32"
    ? path.join(runtimeDir, "python.exe")
    : path.join(runtimeDir, "bin", "python");
}

function isApiHealthy(apiUrl) {
  return Promise.all([
    httpStatusOk(`${apiUrl}/api/status`),
    httpStatusOk(`${apiUrl}/api/llm-config`),
  ]).then(([statusOk, configOk]) => statusOk && configOk);
}

function httpStatusOk(url) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 1500 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
  });
}

function waitForApi(apiUrl, timeoutMs) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (await isApiHealthy(apiUrl)) {
        resolve();
        return;
      }
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`Timed out waiting for ${apiUrl}/api/status`));
        return;
      }
      setTimeout(tick, 500);
    };
    tick();
  });
}

function isPortBusy(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(true));
    server.once("listening", () => {
      server.close(() => resolve(false));
    });
    server.listen(port, host);
  });
}

function fail(message) {
  console.error(`[gagent-desktop] ${message}`);
  process.exit(1);
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    fail(error && error.message ? error.message : String(error));
  });
