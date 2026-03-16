import { create } from "zustand";
import type { GraphNode, GraphEdge } from "@/types/graph";

type SemanticZoomTier = "overview" | "module" | "detail";
type ViewMode = "modules" | "file-members" | "class-detail" | "function-detail" | "variable-flow" | "query-result";

interface BreadcrumbEntry {
  viewMode: ViewMode;
  label: string;
  modulePath: string | null;
  nodeName: string | null;
}

/** A snapshot of the graph state for history navigation. */
interface HistoryEntry {
  viewMode: ViewMode;
  activeModulePath: string | null;
  activeNodeName: string | null;
  breadcrumb: BreadcrumbEntry[];
  queryResultData: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  /** IDs of nodes that were expanded via Cmd+Click branching */
  expandedNodes: Set<string>;
}

interface GraphState {
  selectedNodeId: string | null;
  highlightedNodeIds: Set<string>;
  visibleNodes: GraphNode[];
  visibleEdges: GraphEdge[];
  zoomLevel: number;
  semanticZoomTier: SemanticZoomTier;
  indexing: boolean;
  viewMode: ViewMode;
  activeModulePath: string | null;
  activeNodeName: string | null;
  breadcrumb: BreadcrumbEntry[];
  queryResultData: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  /** Track which nodes have been expanded in the current view */
  expandedNodes: Set<string>;
  /** Navigation history stack */
  historyStack: HistoryEntry[];
  historyIndex: number;

  selectNode: (nodeId: string | null) => void;
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  setVisibleGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setZoomLevel: (zoom: number) => void;
  setIndexing: (indexing: boolean) => void;
  drillIntoFile: (modulePath: string, label: string) => void;
  drillIntoClass: (className: string, modulePath: string) => void;
  drillIntoFunction: (functionName: string, modulePath: string) => void;
  drillIntoVariable: (variableName: string, modulePath: string) => void;
  navigateTo: (index: number) => void;
  showQueryResult: (label: string, nodes: GraphNode[], edges: GraphEdge[]) => void;
  /** Expand a node's usages inline — spawns call-site nodes as branches */
  expandNodeUsages: (nodeId: string, usageNodes: GraphNode[], usageEdges: GraphEdge[]) => void;
  /** Collapse a previously expanded node */
  collapseNodeUsages: (nodeId: string) => void;
  goBack: () => void;
  goForward: () => void;
}

function captureSnapshot(state: GraphState): HistoryEntry {
  return {
    viewMode: state.viewMode,
    activeModulePath: state.activeModulePath,
    activeNodeName: state.activeNodeName,
    breadcrumb: [...state.breadcrumb],
    queryResultData: state.queryResultData,
    expandedNodes: new Set(state.expandedNodes),
  };
}

function pushHistory(state: GraphState): { historyStack: HistoryEntry[]; historyIndex: number } {
  const snapshot = captureSnapshot(state);
  // Truncate any forward history when navigating new
  const stack = state.historyStack.slice(0, state.historyIndex + 1);
  stack.push(snapshot);
  // Keep max 50 entries
  if (stack.length > 50) stack.shift();
  return { historyStack: stack, historyIndex: stack.length - 1 };
}

export const useGraphStore = create<GraphState>((set) => ({
  selectedNodeId: null,
  highlightedNodeIds: new Set<string>(),
  visibleNodes: [],
  visibleEdges: [],
  zoomLevel: 1,
  semanticZoomTier: "module",
  indexing: false,
  viewMode: "modules",
  activeModulePath: null,
  activeNodeName: null,
  queryResultData: null,
  expandedNodes: new Set<string>(),
  historyStack: [],
  historyIndex: -1,
  breadcrumb: [{ viewMode: "modules", label: "Files", modulePath: null, nodeName: null }],
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
  setZoomLevel: (zoom) => {
    let tier: SemanticZoomTier = "module";
    if (zoom < 0.4) {
      tier = "overview";
    } else if (zoom > 1.2) {
      tier = "detail";
    }
    set({ zoomLevel: zoom, semanticZoomTier: tier });
  },
  setIndexing: (indexing) => set({ indexing }),
  drillIntoFile: (modulePath, label) =>
    set((state) => ({
      ...pushHistory(state),
      viewMode: "file-members",
      activeModulePath: modulePath,
      activeNodeName: null,
      selectedNodeId: null,
      expandedNodes: new Set<string>(),
      breadcrumb: [
        ...state.breadcrumb.slice(0, 1),
        { viewMode: "file-members", label, modulePath, nodeName: null },
      ],
    })),
  drillIntoClass: (className, modulePath) =>
    set((state) => {
      const shortName = className.split(".").pop() ?? className;
      return {
        ...pushHistory(state),
        viewMode: "class-detail",
        activeModulePath: modulePath,
        activeNodeName: className,
        selectedNodeId: null,
        expandedNodes: new Set<string>(),
        breadcrumb: [
          ...state.breadcrumb.slice(0, 2),
          { viewMode: "class-detail", label: shortName, modulePath, nodeName: className },
        ],
      };
    }),
  drillIntoFunction: (functionName, modulePath) =>
    set((state) => {
      const shortName = functionName.split(".").pop() ?? functionName;
      const isCrossFile = modulePath !== state.activeModulePath && modulePath !== "";
      let newBreadcrumb: BreadcrumbEntry[];
      if (state.viewMode === "class-detail") {
        newBreadcrumb = [
          ...state.breadcrumb.slice(0, 3),
          { viewMode: "function-detail", label: shortName, modulePath, nodeName: functionName },
        ];
      } else if (isCrossFile) {
        const fileName = modulePath.split("/").pop() ?? modulePath;
        newBreadcrumb = [
          state.breadcrumb[0]!,
          { viewMode: "file-members", label: fileName, modulePath, nodeName: null },
          { viewMode: "function-detail", label: shortName, modulePath, nodeName: functionName },
        ];
      } else {
        newBreadcrumb = [
          ...state.breadcrumb.slice(0, 2),
          { viewMode: "function-detail", label: shortName, modulePath, nodeName: functionName },
        ];
      }
      return {
        ...pushHistory(state),
        viewMode: "function-detail",
        activeModulePath: modulePath,
        activeNodeName: functionName,
        selectedNodeId: null,
        expandedNodes: new Set<string>(),
        breadcrumb: newBreadcrumb,
      };
    }),
  drillIntoVariable: (variableName, modulePath) =>
    set((state) => {
      const shortName = variableName.split(".").pop() ?? variableName;
      return {
        ...pushHistory(state),
        viewMode: "variable-flow",
        activeModulePath: modulePath,
        activeNodeName: variableName,
        selectedNodeId: null,
        expandedNodes: new Set<string>(),
        breadcrumb: [
          ...state.breadcrumb.slice(0, 3),
          { viewMode: "variable-flow", label: shortName, modulePath, nodeName: variableName },
        ],
      };
    }),
  showQueryResult: (label, nodes, edges) =>
    set((state) => ({
      ...pushHistory(state),
      viewMode: "query-result",
      activeModulePath: null,
      activeNodeName: null,
      selectedNodeId: null,
      expandedNodes: new Set<string>(),
      queryResultData: { nodes, edges },
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "query-result", label, modulePath: null, nodeName: null },
      ],
    })),
  expandNodeUsages: (nodeId, usageNodes, usageEdges) =>
    set((state) => {
      const expanded = new Set(state.expandedNodes);
      expanded.add(nodeId);
      // Merge usage nodes/edges into current query result data (or create new)
      const existing = state.queryResultData ?? { nodes: [], edges: [] };
      const seenIds = new Set(existing.nodes.map((n) => n.id));
      const newNodes = [...existing.nodes];
      for (const n of usageNodes) {
        if (!seenIds.has(n.id)) {
          seenIds.add(n.id);
          newNodes.push(n);
        }
      }
      const edgeKeys = new Set(existing.edges.map((e) => `${e.source}-${e.type}-${e.target}`));
      const newEdges = [...existing.edges];
      for (const e of usageEdges) {
        const key = `${e.source}-${e.type}-${e.target}`;
        if (!edgeKeys.has(key)) {
          edgeKeys.add(key);
          newEdges.push(e);
        }
      }
      return {
        ...pushHistory(state),
        expandedNodes: expanded,
        queryResultData: { nodes: newNodes, edges: newEdges },
        viewMode: "query-result",
      };
    }),
  collapseNodeUsages: (nodeId) =>
    set((state) => {
      const expanded = new Set(state.expandedNodes);
      expanded.delete(nodeId);
      return { expandedNodes: expanded };
    }),
  navigateTo: (index) =>
    set((state) => {
      const entry = state.breadcrumb[index];
      if (!entry) return state;
      return {
        ...pushHistory(state),
        viewMode: entry.viewMode,
        activeModulePath: entry.modulePath,
        activeNodeName: entry.nodeName,
        selectedNodeId: null,
        expandedNodes: new Set<string>(),
        breadcrumb: state.breadcrumb.slice(0, index + 1),
      };
    }),
  goBack: () =>
    set((state) => {
      if (state.historyIndex < 0) return state;
      // Save current state as forward entry
      const snapshot = captureSnapshot(state);
      const stack = [...state.historyStack];
      // If we're at the end, push current as forward target
      if (state.historyIndex === stack.length - 1) {
        stack.push(snapshot);
      }
      const targetIndex = Math.max(0, state.historyIndex - 1);
      const target = stack[targetIndex];
      if (!target) return state;
      return {
        historyStack: stack,
        historyIndex: targetIndex,
        viewMode: target.viewMode,
        activeModulePath: target.activeModulePath,
        activeNodeName: target.activeNodeName,
        selectedNodeId: null,
        breadcrumb: target.breadcrumb,
        queryResultData: target.queryResultData,
        expandedNodes: target.expandedNodes,
      };
    }),
  goForward: () =>
    set((state) => {
      const targetIndex = state.historyIndex + 1;
      const target = state.historyStack[targetIndex];
      if (!target) return state;
      return {
        historyIndex: targetIndex,
        viewMode: target.viewMode,
        activeModulePath: target.activeModulePath,
        activeNodeName: target.activeNodeName,
        selectedNodeId: null,
        breadcrumb: target.breadcrumb,
        queryResultData: target.queryResultData,
        expandedNodes: target.expandedNodes,
      };
    }),
}));
