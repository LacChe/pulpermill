// Runs a Python script with the first interpreter that works: `python3`, `python` or, on Windows, `py -3`.
// (On Windows `python3` is usually missing or a Store stub, so a fixed name made the dry runs fail with no explanation.)
import { spawnSync } from "node:child_process";

const CANDIDATES = [["python3"], ["python"], ["py", "-3"]];

function works(cmd) {
  const probe = spawnSync(cmd[0], [...cmd.slice(1), "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 3)"], { encoding: "utf8" });
  return !probe.error && probe.status === 0;
}

export function runPython(script, input) {
  for (const cmd of CANDIDATES) {
    if (works(cmd)) return spawnSync(cmd[0], [...cmd.slice(1), script], { input, encoding: "utf8" });
  }
  return { status: 1, stdout: "", stderr: "No Python 3.12 or newer was found (tried python3, python and py -3). Install Python, or put it on the PATH, to run the dry checks.\n" };
}
