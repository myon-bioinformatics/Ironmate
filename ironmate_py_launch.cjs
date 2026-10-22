"use strict";
/** Ironmate-owned helpers for vendored py_launch.cjs (not a second launcher). */

const PY_LAUNCH = {envVar: "IRONMATE_PYTHON", noSite: true};

/**
 * @param {unknown} err
 * @param {string} pythonProcessPrefix e.g. "flow Python process failed: "
 * @param {string} failureFallback when the child exits nonzero with empty stderr
 */
function mapLaunchError(err, pythonProcessPrefix, failureFallback) {
  const msg = String(err && err.message ? err.message : err);
  if (msg.startsWith("py_launch: Python process failed: ")) {
    throw Error(pythonProcessPrefix + msg.slice("py_launch: Python process failed: ".length));
  }
  const spawn = msg.match(/^py_launch: ([^:]+): (spawnSync .+)$/);
  if (spawn) throw Error(pythonProcessPrefix + spawn[2]);
  if (msg.startsWith("py_launch: ")) {
    throw Error(pythonProcessPrefix + msg.slice("py_launch: ".length));
  }
  if (err && Object.hasOwn(err, "status") && err.status !== 0) {
    throw Error((err.stderr && err.stderr.toString("utf8").trim()) || failureFallback);
  }
  throw err;
}

module.exports = {mapLaunchError, PY_LAUNCH};
