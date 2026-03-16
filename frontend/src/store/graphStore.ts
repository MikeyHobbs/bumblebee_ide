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
  queryResultData: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
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
      viewMode: "file-members",
      activeModulePath: modulePath,
      activeNodeName: null,
      selectedNodeId: null,
      breadcrumb: [
        ...state.breadcrumb.slice(0, 1),
        { viewMode: "file-members", label, modulePath, nodeName: null },
      ],
    })),
  drillIntoClass: (className, modulePath) =>
    set((state) => {
      const shortName = className.split(".").pop() ?? className;
      return {
        viewMode: "class-detail",
        activeModulePath: modulePath,
        activeNodeName: className,
        selectedNodeId: null,
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
        // Drilling from class-detail: breadcrumb goes to depth 3 (Files / file / class / method)
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
        viewMode: "function-detail",
        activeModulePath: modulePath,
        activeNodeName: functionName,
        selectedNodeId: null,
        breadcrumb: newBreadcrumb,
      };
    }),
  drillIntoVariable: (variableName, modulePath) =>
    set((state) => {
      const shortName = variableName.split(".").pop() ?? variableName;
      return {
        viewMode: "variable-flow",
        activeModulePath: modulePath,
        activeNodeName: variableName,
        selectedNodeId: null,
        breadcrumb: [
          ...state.breadcrumb.slice(0, 3),
          { viewMode: "variable-flow", label: shortName, modulePath, nodeName: variableName },
        ],
      };
    }),
  showQueryResult: (label, nodes, edges) =>
    set((state) => ({
      viewMode: "query-result",
      activeModulePath: null,
      activeNodeName: null,
      selectedNodeId: null,
      queryResultData: { nodes, edges },
      breadcrumb: [
        state.breadcrumb[0]!,
        { viewMode: "query-result", label, modulePath: null, nodeName: null },
      ],
    })),
  navigateTo: (index) =>
    set((state) => {
      const entry = state.breadcrumb[index];
      if (!entry) return state;
      return {
        viewMode: entry.viewMode,
        activeModulePath: entry.modulePath,
        activeNodeName: entry.nodeName,
        selectedNodeId: null,
        breadcrumb: state.breadcrumb.slice(0, index + 1),
      };
    }),
}));
