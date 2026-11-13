/** Types for ironmate_cli.cjs. Fixable failures exit the process with status 2; PY_LAUNCH and mapLaunchError serve vendored py_launch.cjs. */
export function fail(tool: string, message: string, hint: string | undefined, jsonMode: boolean): never;
export function wantsJson(argv: readonly string[]): boolean;
export const PY_LAUNCH: {envVar: string; noSite: boolean};

export function mapLaunchError(
  err: unknown,
  pythonProcessPrefix: string,
  failureFallback: string,
  context?: {
    inputKnownToExceed?: boolean;
    inputExceededMessage?: string;
    responseMaxBytes?: number;
  },
): never;
