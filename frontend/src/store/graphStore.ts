import { create } from "zustand";
import type { GraphNode, GraphEdge, SemanticDiff } from "@/types/graph";

type ViewMode = "knowledge-graph" | "flow-view" | "variable-flow";

interface BreadcrumbEntry {
  viewMode: ViewMode;
  label: string;
  nodeId: string | null;
  focusedNodeId: string | null;
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

  // Focus / expand (Sigma single-canvas)
  focusedNodeId: string | null;
  expandedNodeId: string | null;
  tracedVariableId: string | null;
  consumerVariableId: string | null;
  selectedTypeShapeId: string | null;

  // Query results (highlight mode)
  queryHighlightLabel: string | null;
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

  // Focus actions (Sigma)
  expandNode: (nodeId: string) => void;
  collapseExpanded: () => void;
  traceVariable: (variableId: string) => void;
  clearTrace: () => void;
  showConsumers: (variableId: string) => void;
  selectTypeShape: (shapeId: string | null) => void;

  // Query result (highlight on Sigma canvas)
  showQueryResult: (label: string, nodes: GraphNode[], edges: GraphEdge[]) => void;
  expandHighlight: (nodeId: string, neighborIds: string[]) => void;
  removeHighlightNode: (nodeId: string) => void;

  // Diff
  setActiveDiff: (diff: SemanticDiff | null) => void;

  // Impact analysis (compose save)
  impactedNodeIds: Set<string>;
  setImpactedNodes: (nodeIds: string[]) => void;
  clearImpactedNodes: () => void;
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
  queryHighlightLabel: null,
  queryResultData: null,
  activeDiff: null,
  focusedNodeId: null,
  expandedNodeId: null,
  tracedVariableId: null,
  consumerVariableId: null,
  selectedTypeShapeId: null,
  breadcrumb: [{ viewMode: "knowledge-graph", label: "Graph", nodeId: null, focusedNodeId: null }],

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
      viewMode: "knowledge-graph",
      focusedNodeId: nodeId,
      activeNodeId: nodeId,
      selectedNodeId: null,
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "knowledge-graph", label, nodeId, focusedNodeId: nodeId },
      ],
    })),

  navigateToFlow: (flowId, label) =>
    set((state) => ({
      viewMode: "flow-view",
      activeNodeId: flowId,
      selectedNodeId: null,
      focusedNodeId: null,
      expandedNodeId: null,
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "flow-view", label, nodeId: flowId, focusedNodeId: null },
      ],
    })),

  navigateToVariable: (variableName) =>
    set((state) => ({
      viewMode: "variable-flow",
      activeNodeId: variableName,
      selectedNodeId: null,
      focusedNodeId: null,
      expandedNodeId: null,
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "variable-flow", label: variableName, nodeId: variableName, focusedNodeId: null },
      ],
    })),

  navigateBack: (index) =>
    set((state) => {
      const entry = state.breadcrumb[index];
      if (!entry) return state;
      return {
        viewMode: entry.viewMode,
        activeNodeId: entry.nodeId,
        focusedNodeId: entry.focusedNodeId,
        expandedNodeId: null,
        selectedNodeId: null,
        breadcrumb: state.breadcrumb.slice(0, index + 1),
      };
    }),

  goHome: () =>
    set({
      viewMode: "knowledge-graph",
      activeNodeId: null,
      selectedNodeId: null,
      focusedNodeId: null,
      expandedNodeId: null,
      tracedVariableId: null,
      consumerVariableId: null,
      selectedTypeShapeId: null,
      highlightedNodeIds: new Set<string>(),
      queryHighlightLabel: null,
      breadcrumb: [{ viewMode: "knowledge-graph", label: "Graph", nodeId: null, focusedNodeId: null }],
      visibleNodes: [],
      visibleEdges: [],
      queryResultData: null,
      activeDiff: null,
      impactedNodeIds: new Set<string>(),
    }),

  expandNode: (nodeId) =>
    set((state) => ({
      expandedNodeId: state.expandedNodeId === nodeId ? null : nodeId,
    })),

  collapseExpanded: () => set({ expandedNodeId: null, tracedVariableId: null }),

  traceVariable: (variableId) => set({ tracedVariableId: variableId }),

  clearTrace: () => set({ tracedVariableId: null, consumerVariableId: null }),

  showConsumers: (variableId) => set({ consumerVariableId: variableId, tracedVariableId: null }),

  selectTypeShape: (shapeId) => set({ selectedTypeShapeId: shapeId }),

  showQueryResult: (label, nodes, edges) =>
    set((state) => ({
      viewMode: "knowledge-graph",
      activeNodeId: null,
      selectedNodeId: null,
      focusedNodeId: null,
      expandedNodeId: null,
      highlightedNodeIds: new Set<string>(),
      queryHighlightLabel: label,
      queryResultData: { nodes, edges },
      breadcrumb: [
        state.breadcrumb[0]!,
        {
          viewMode: "knowledge-graph",
          label,
          nodeId: null,
          focusedNodeId: null,
        },
      ],
    })),

  expandHighlight: (nodeId, neighborIds) =>
    set((state) => {
      const next = new Set(state.highlightedNodeIds);
      next.add(nodeId);
      for (const nid of neighborIds) next.add(nid);
      return {
        highlightedNodeIds: next,
        focusedNodeId: nodeId,
      };
    }),

  removeHighlightNode: (nodeId) =>
    set((state) => {
      if (!state.highlightedNodeIds.has(nodeId)) return state;
      const next = new Set(state.highlightedNodeIds);
      next.delete(nodeId);
      // If the focused node was removed, clear focus
      const focusedNodeId = state.focusedNodeId === nodeId ? null : state.focusedNodeId;
      // If no highlights remain, clear the query label too
      if (next.size === 0) {
        return { highlightedNodeIds: next, focusedNodeId, queryHighlightLabel: null };
      }
      return { highlightedNodeIds: next, focusedNodeId };
    }),

  setActiveDiff: (diff) => set({ activeDiff: diff }),

  impactedNodeIds: new Set<string>(),
  setImpactedNodes: (nodeIds) => set({ impactedNodeIds: new Set(nodeIds) }),
  clearImpactedNodes: () =>
    set((state) => {
      if (state.impactedNodeIds.size === 0) return state;
      return { impactedNodeIds: new Set<string>() };
    }),
}));
