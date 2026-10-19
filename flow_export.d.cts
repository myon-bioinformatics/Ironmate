/** Types for flow_export.cjs. The flow JSON contract is web-ui's flow spec (vendor/web_ui/js/flow.cjs). */
export type FlowFormat = "mermaid" | "svg" | "png" | "base64" | "data-uri";
export interface FlowCard { title: string; note?: string }
export interface FlowSpec { title?: string; sources_label?: string; sources: FlowCard[]; steps: FlowCard[] }
export interface RenderFlowOptions {
  /** Default "svg". */
  format?: FlowFormat;
  /** 0.25..8, default 1. */
  scale?: number;
  /** "#RRGGBB"; transparent when omitted. */
  background?: string;
  mmdc?: string;
  chrome?: string;
  puppeteerConfig?: string;
  /** Default $IRONMATE_PYTHON or "python3". */
  python?: string;
}
/** Bytes of the chosen format (a Node Buffer at run time, also for text formats). Throws Error on failure. */
export function renderFlow(spec: FlowSpec, options?: RenderFlowOptions): Uint8Array;
