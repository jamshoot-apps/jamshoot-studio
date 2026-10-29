// Native Node tests and V8 coverage; no browser, DOM or Python process.
import { spawnSync } from "node:child_process";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const coverage = fileURLToPath(new URL("coverage/node/", root));
await rm(coverage, { recursive: true, force: true });
const result = spawnSync(process.execPath, ["--test", "tests/unit.test.mjs"], {
  cwd: fileURLToPath(root),
  env: { ...process.env, NODE_V8_COVERAGE: coverage },
  stdio: "inherit",
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
