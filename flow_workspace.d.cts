/// <reference types="node" />
/** Types for flow_workspace.cjs: persistence in Python (flow_workspace.py), patches per web-ui's contract. */
import type {RenderFlowOptions} from "./flow_export.cjs";

export interface FlowWorkspace {
  schema: "ironmate-flow/1";
  /** The source JSON text exactly as imported. */
  original_json: string;
  /** The validated flow (web-ui's flow contract). */
  spec: object;
}
export interface FlowPatchOperation {
  path: string;
  value: string;
}
export interface WorkspaceOptions {
  /** Python executable; defaults to $IRONMATE_PYTHON or python3. */
  python?: string;
}

export function importFlow(text: string, options?: WorkspaceOptions): FlowWorkspace;
export function patchWorkspace(workspace: FlowWorkspace, operations: FlowPatchOperation[],
  options?: WorkspaceOptions): FlowWorkspace;
export function renderWorkspace(workspace: FlowWorkspace, options?: RenderFlowOptions): Buffer;
export function patchAndRender(workspace: FlowWorkspace, operations: FlowPatchOperation[],
  options?: RenderFlowOptions): {workspace: FlowWorkspace; image: Buffer};
