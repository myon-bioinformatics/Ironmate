/** Types for image_digest.cjs. Mirrors image_digest.py (ironmate-image-digest-input/1 -> ironmate-image-digest/1). */
export interface DigestCell {
  row: string;
  col: string;
  /** Relative to options.base; no absolute paths or "..". */
  image?: string | null;
  /** Short lowercase token; "pass" counts as passed. Default "unknown". */
  status?: string;
  /** Up to 6 shown. */
  notes?: string[];
}
export interface DigestInput {
  schema: "ironmate-image-digest-input/1";
  title?: string;
  rows: string[];
  cols: string[];
  cells: DigestCell[];
  /** Short strings; "link" must be an https URL. */
  meta?: Record<string, string>;
}
export interface DigestOptions {
  base: string;
  /** New or empty directory for digest.html, summary.md and digest.json. */
  out: string;
  /** 20000..20000000, default 1000000. */
  maxBytes?: number;
  /** Starting WIDTHxHEIGHT, default "64x128". */
  tile?: `${number}x${number}`;
  python?: string;
}
export interface DigestInfo {
  schema: "ironmate-image-digest/1";
  tile: [number, number];
  bytes: number;
  fits: boolean;
  rows: number;
  cols: number;
  passed: number;
  statuses: Record<string, number>;
}
export function buildDigest(spec: DigestInput, options: DigestOptions): DigestInfo;
