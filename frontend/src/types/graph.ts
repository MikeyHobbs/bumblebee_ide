export type NodeLabel =
  | "Module"
  | "Class"
  | "Function"
  | "Variable"
  | "Statement"
  | "ControlFlow"
  | "Branch";

export type EdgeType =
  | "DEFINES"
  | "CALLS"
  | "INHERITS"
  | "IMPORTS"
  | "ASSIGNS"
  | "MUTATES"
  | "READS"
  | "PASSES_TO"
  | "RETURNS"
  | "FEEDS"
  | "CONTAINS"
  | "NEXT";

export interface GraphNode {
  id: string;
  label: NodeLabel;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  type: EdgeType;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

export interface LogicPack {
  nodes: GraphNode[];
  edges: GraphEdge[];
  snippets: Record<string, string>;
}

export interface TimelineEntry {
  edge_type: string;
  function_name: string;
  variable_name: string;
  line: number;
  seq: number;
  properties: Record<string, unknown>;
}

export interface MutationTimeline {
  variable: Record<string, unknown>;
  origin: TimelineEntry | null;
  mutations: TimelineEntry[];
  reads: TimelineEntry[];
  passes: TimelineEntry[];
  returns: TimelineEntry[];
  feeds: TimelineEntry[];
  terminal: TimelineEntry | null;
}

export interface VariableSearchResult {
  name: string;
  scope: string;
  origin_line: number;
  origin_func: string;
  type_hint: string | null;
  module_path: string;
}
