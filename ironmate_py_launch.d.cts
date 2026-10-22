/** Types for ironmate_py_launch.cjs: error mapping for vendored py_launch.cjs. */
export const PY_LAUNCH: {envVar: string; noSite: boolean};

export function mapLaunchError(
  err: unknown,
  pythonProcessPrefix: string,
  failureFallback: string,
): never;
