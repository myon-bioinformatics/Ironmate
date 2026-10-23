"use strict";
/** Ironmate-owned helpers for vendored py_launch.cjs (not a second launcher). */

const {mapLaunchError} = require("./vendor/py_launch.cjs");

const PY_LAUNCH = {envVar: "IRONMATE_PYTHON", noSite: true};

module.exports = {mapLaunchError, PY_LAUNCH};
