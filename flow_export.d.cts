/// <reference types="node" />
/** Types for flow_export.cjs: Python (flow_export.py) renders; the JSON contract is web-ui's flow. */
export type FlowFormat = "mermaid" | "svg" | "png" | "base64" | "data-uri";
export interface RenderFlowOptions {
  /** Defaults to "svg". */
  format?: FlowFormat;
  /** 0.25..8, default 1. */
  scale?: number;
  background?: string;
  /** Mermaid CLI and browser paths, passed through to flow_export.py. */
  mmdc?: string;
  chrome?: string;
  puppeteerConfig?: string;
  /** Python executable; defaults to $IRONMATE_PYTHON or python3. */
  python?: string;
}

/** Rendered output as bytes (text formats are UTF-8). Spec JSON is limited to 256 KiB. */
export function renderFlow(spec: object, options?: RenderFlowOptions): Buffer;
