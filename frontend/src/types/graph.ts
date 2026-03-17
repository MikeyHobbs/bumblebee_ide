// --- Enums ---
export type LogicNodeKind = "function" | "method" | "class" | "constant" | "type_alias" | "flow_function";
export type NodeStatus = "active" | "deprecated";
export type ParamKind = "positional_only" | "positional_or_keyword" | "keyword_only" | "var_positional" | "var_keyword";
export type MutationKind = "method_call" | "subscript_assign" | "attr_assign" | "augmented_assign";
export type FeedVia = "assignment" | "mutation_arg" | "call_arg" | "call_return";

export type EdgeType =
  // LogicNode -> LogicNode
  | "CALLS" | "DEPENDS_ON" | "IMPLEMENTS" | "VALIDATES" | "TRANSFORMS" | "INHERITS" | "MEMBER_OF"
  // LogicNode -> Variable
  | "ASSIGNS" | "MUTATES" | "READS" | "RETURNS"
  // Variable -> Variable
  | "PASSES_TO" | "FEEDS"
  // Flow edges
  | "STEP_OF" | "CONTAINS_FLOW" | "PROMOTED_TO"
  // Legacy (kept for backward compat during transition)
  | "DEFINES" | "IMPORTS" | "CONTAINS" | "NEXT";

// --- Core Models ---

export interface ParamSpec {
  name: string;
  type_hint: string | null;
  default: string | null;
  kind: ParamKind;
}

export interface LogicNode {
  id: string;
  ast_hash: string;
  kind: LogicNodeKind;
  name: string;
  module_path: string;
  signature: string;
  source_text: string;
  semantic_intent: string | null;
  docstring: string | null;
  decorators: string[];
  params: ParamSpec[];
  return_type: string | null;
  tags: string[];
  class_id: string | null;
  derived_from: string | null;
  start_line: number | null;
  end_line: number | null;
  status: NodeStatus;
  created_at: string;
  updated_at: string;
  warnings: string[];
}

export interface Variable {
  id: string;
  name: string;
  scope: string;
  origin_node_id: string;
  origin_line: number | null;
  type_hint: string | null;
  is_parameter: boolean;
  is_attribute: boolean;
  created_at: string;
}

export interface GraphEdge {
  type: EdgeType;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

export interface Flow {
  id: string;
  name: string;
  description: string | null;
  entry_point: string;
  exit_points: string[];
  node_ids: string[];
  sub_flow_ids: string[];
  parent_flow_id: string | null;
  promoted_node_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface FlowHierarchy {
  flow: Flow;
  children: FlowHierarchy[];
  depth: number;
}

// --- Timeline & Logic Pack ---

export interface MutationTimeline {
  variable: Variable;
  origin: LogicNode | null;
  assigns: GraphEdge[];
  mutations: GraphEdge[];
  reads: GraphEdge[];
  returns: GraphEdge[];
  passes: GraphEdge[];
  feeds: GraphEdge[];
  terminal: LogicNode | null;
}

export interface LogicPack {
  nodes: GraphNode[];
  edges: GraphEdge[];
  snippets: Record<string, string>;
}

// --- Gap Analysis ---

export interface GapReport {
  dead_ends: LogicNode[];
  orphans: LogicNode[];
  missing_error_handling: Record<string, unknown>[];
  circular_deps: string[][];
  untested_mutations: Record<string, unknown>[];
}

// --- Semantic Diff ---

export interface SemanticDiff {
  added_nodes: LogicNode[];
  removed_nodes: LogicNode[];
  modified_nodes: Array<{
    id: string;
    old_ast_hash: string;
    new_ast_hash: string;
    changed_fields: Record<string, { old: unknown; new: unknown }>;
  }>;
  added_edges: GraphEdge[];
  removed_edges: GraphEdge[];
  added_variables: Variable[];
  removed_variables: Variable[];
}

// --- Graph Meta ---

export interface GraphMeta {
  version: string;
  schema_version: number;
  graph_name: string;
  node_count: number;
  variable_count: number;
  edge_count: number;
  flow_count: number;
  last_serialized: string;
  source_language: string;
  source_root: string;
}

// --- Backward compatibility aliases ---
// These allow existing components that haven't been updated yet to still compile.
// GraphNode is now a union — either a LogicNode or Variable rendered as a graph node.

export type NodeLabel = "LogicNode" | "Variable" | "Flow"
  // Legacy labels kept for transition
  | "Module" | "Class" | "Function" | "Statement" | "ControlFlow" | "Branch";

export interface GraphNode {
  id: string;
  label: NodeLabel;
  properties: Record<string, unknown>;
}

export interface VariableSearchResult {
  name: string;
  scope: string;
  origin_line: number;
  origin_func: string;
  type_hint: string | null;
  module_path: string;
}
