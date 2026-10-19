/** Types for flow_workspace.cjs. Python owns persistence; patch semantics are web-ui's flow patches. */
import type {FlowSpec, RenderFlowOptions} from "./flow_export.cjs";
export interface FlowWorkspace { schema: "ironmate-flow/1"; original_json: string; spec: FlowSpec }
export interface FlowPatchOperation { path: string; value: string }
export interface WorkspaceOptions { python?: string }
/** Wraps flow JSON text without reserializing it. */
export function importFlow(text: string, options?: WorkspaceOptions): FlowWorkspace;
export function patchWorkspace(workspace: FlowWorkspace, operations: FlowPatchOperation[],
  options?: WorkspaceOptions): FlowWorkspace;
export function renderWorkspace(workspace: FlowWorkspace, options?: RenderFlowOptions): Uint8Array;
export function patchAndRender(workspace: FlowWorkspace, operations: FlowPatchOperation[],
  options?: RenderFlowOptions): {workspace: FlowWorkspace; image: Uint8Array};
