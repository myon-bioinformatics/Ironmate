/** Types for image_digest.cjs: Python (image_digest.py) decodes images and writes the page. */
export interface DigestCell {
  row: string;
  col: string;
  /** Relative path inside the base directory; omitted for a cell without a screenshot. */
  image?: string | null;
  /** Short lowercase token, default "unknown"; only drives colour and counts. */
  status?: string;
  /** Up to 6 short notes, shown under the thumbnail. */
  notes?: string[];
}
export interface DigestInput {
  schema: "ironmate-image-digest-input/1";
  title?: string;
  rows: string[];
  cols: string[];
  /** Short strings; "link" must be an https URL. */
  meta?: Record<string, string>;
  cells: DigestCell[];
}
export interface DigestOptions {
  /** Directory the image paths are relative to. */
  base: string;
  /** New or empty output directory (digest.html, summary.md, digest.json). */
  out: string;
  /** 20000..20000000, default 1000000. */
  maxBytes?: number;
  /** Starting thumbnail size, default "64x128". */
  tile?: `${number}x${number}`;
  /** Python executable; defaults to $IRONMATE_PYTHON or python3. */
  python?: string;
}
/** digest.json (ironmate-image-digest/1). */
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
