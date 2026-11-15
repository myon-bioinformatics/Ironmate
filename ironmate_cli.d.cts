/** Types for ironmate_cli.cjs. Fixable failures exit the process with status 2. */
export function fail(tool: string, message: string, hint: string | undefined, jsonMode: boolean): never;
export function wantsJson(argv: readonly string[]): boolean;
