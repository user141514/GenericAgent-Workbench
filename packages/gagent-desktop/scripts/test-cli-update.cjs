#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const { parseArgs, updateSelf } = require("../bin/gagent-desktop.js");

async function testParseUpdateCommand() {
  assert.equal(parseArgs(["update"]).update, true);
  assert.equal(parseArgs(["--update"]).update, true);
  assert.equal(parseArgs(["-U"]).update, true);
}

async function testSkipsWhenCurrentIsLatest() {
  const installs = [];
  const logs = [];
  const code = await updateSelf({
    currentVersion: "1.2.3",
    fetchLatestVersion: async () => "1.2.3",
    runInstall: (command, args) => {
      installs.push([command, args]);
      return { status: 0 };
    },
    logger: { log: (line) => logs.push(line), error: (line) => logs.push(line) },
  });

  assert.equal(code, 0);
  assert.deepEqual(installs, []);
  assert.ok(logs.some((line) => line.includes("Already up to date")));
}

async function testInstallsLatestWhenNewerVersionExists() {
  const installs = [];
  const code = await updateSelf({
    currentVersion: "1.2.3",
    fetchLatestVersion: async () => "1.2.4",
    runInstall: (command, args) => {
      installs.push([command, args]);
      return { status: 0 };
    },
    logger: { log: () => undefined, error: () => undefined },
  });

  assert.equal(code, 0);
  assert.equal(installs.length, 1);
  assert.match(installs[0][0], /^npm(\.cmd)?$/);
  assert.deepEqual(installs[0][1], ["install", "-g", "gagent-desktop@latest"]);
}

async function testReturnsFailureWhenInstallFails() {
  const errors = [];
  const code = await updateSelf({
    currentVersion: "1.2.3",
    fetchLatestVersion: async () => "1.2.4",
    runInstall: () => ({ status: 7 }),
    logger: { log: () => undefined, error: (line) => errors.push(line) },
  });

  assert.equal(code, 1);
  assert.ok(errors.some((line) => line.includes("Update failed")));
}

async function main() {
  await testParseUpdateCommand();
  await testSkipsWhenCurrentIsLatest();
  await testInstallsLatestWhenNewerVersionExists();
  await testReturnsFailureWhenInstallFails();
  console.log("[test-cli-update] ok");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
