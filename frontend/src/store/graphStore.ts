import { create } from "zustand";
import type { GraphNode, GraphEdge, SemanticDiff } from "@/types/graph";

type ViewMode = "knowledge-graph" | "node-detail" | "flow-view" | "variable-flow" | "query-result";

interface BreadcrumbEntry {
  viewMode: ViewMode;
  label: string;
  nodeId: string | null;
}

interface GraphState {
  // Core state
  selectedNodeId: string | null;
  highlightedNodeIds: Set<string>;
  visibleNodes: GraphNode[];
  visibleEdges: GraphEdge[];
  zoomLevel: number;
  indexing: boolean;

  // Navigation
  viewMode: ViewMode;
  activeNodeId: string | null;
  breadcrumb: BreadcrumbEntry[];

  // Query results
  queryResultData: { nodes: GraphNode[]; edges: GraphEdge[] } | null;

  // Semantic diff
  activeDiff: SemanticDiff | null;

  // Actions
  selectNode: (nodeId: string | null) => void;
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  setVisibleGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setZoomLevel: (zoom: number) => void;
  setIndexing: (indexing: boolean) => void;

  // Navigation actions
  navigateToNode: (nodeId: string, label: string) => void;
  navigateToFlow: (flowId: string, label: string) => void;
  navigateToVariable: (variableName: string) => void;
  navigateBack: (index: number) => void;
  goHome: () => void;

  // Query result
  showQueryResult: (label: string, nodes: GraphNode[], edges: GraphEdge[]) => void;

  // Diff
  setActiveDiff: (diff: SemanticDiff | null) => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  selectedNodeId: null,
  highlightedNodeIds: new Set<string>(),
  visibleNodes: [],
  visibleEdges: [],
  zoomLevel: 1,
  indexing: false,
  viewMode: "knowledge-graph",
  activeNodeId: null,
  queryResultData: null,
  activeDiff: null,
  breadcrumb: [{ viewMode: "knowledge-graph", label: "Graph", nodeId: null }],

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  highlightNodes: (nodeIds) =>
    set((state) => {
      const newSet = new Set(nodeIds);
      if (
        newSet.size === state.highlightedNodeIds.size &&
        nodeIds.every((id) => state.highlightedNodeIds.has(id))
      ) {
        return state;
      }
      return { highlightedNodeIds: newSet };
    }),

  clearHighlights: () =>
    set((state) => {
      if (state.highlightedNodeIds.size === 0) return state;
      return { highlightedNodeIds: new Set<string>() };
    }),

  setVisibleGraph: (nodes, edges) =>
    set({ visibleNodes: nodes, visibleEdges: edges }),

  setZoomLevel: (zoom) => set({ zoomLevel: zoom }),

  setIndexing: (indexing) => set({ indexing }),

  navigateToNode: (nodeId, label) =>
    set((state) => ({
      viewMode: "node-detail",
      activeNodeId: nodeId,
      selectedNodeId: null,
      breadcrumb: [
        ...state.breadcrumb.filter((_, i) => i === 0),
        { viewMode: "node-detail", label, nodeId },
      ],
    })),

  navigateToFlow: (flowId, label) =>
    set((state) => ({
      viewMode: "flow-view",
      activeNodeId: flowId,
      selectedNodeId: null,
      breadcrumb: [
        ...state.breadcrumb.filter((_, i) => i === 0),
        { viewMode: "flow-view", label, nodeId: flowId },
      ],
    })),

  navigateToVariable: (variableName) =>
    set((state) => ({
      viewMode: "variable-flow",
      activeNodeId: variableName,
      selectedNodeId: null,
      breadcrumb: [
        ...state.breadcrumb.filter((_, i) => i === 0),
        { viewMode: "variable-flow", label: variableName, nodeId: variableName },
      ],
    })),

  navigateBack: (index) =>
    set((state) => {
      const entry = state.breadcrumb[index];
      if (!entry) return state;
      return {
        viewMode: entry.viewMode,
        activeNodeId: entry.nodeId,
        selectedNodeId: null,
        breadcrumb: state.breadcrumb.slice(0, index + 1),
      };
    }),

  goHome: () =>
    set({
      viewMode: "knowledge-graph",
      activeNodeId: null,
      selectedNodeId: null,
      breadcrumb: [{ viewMode: "knowledge-graph", label: "Graph", nodeId: null }],
    }),

  showQueryResult: (label, nodes, edges) =>
    set((state) => ({
      viewMode: "query-result",
      activeNodeId: null,
      selectedNodeId: null,
      queryResultData: { nodes, edges },
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "query-result", label, nodeId: null },
      ],
    })),

  setActiveDiff: (diff) => set({ activeDiff: diff }),
}));
