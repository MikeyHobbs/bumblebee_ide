import { create } from "zustand";
import type { GraphNode, GraphEdge } from "@/types/graph";

type SemanticZoomTier = "overview" | "module" | "detail";

interface GraphState {
  selectedNodeId: string | null;
  highlightedNodeIds: Set<string>;
  visibleNodes: GraphNode[];
  visibleEdges: GraphEdge[];
  zoomLevel: number;
  semanticZoomTier: SemanticZoomTier;
  selectNode: (nodeId: string | null) => void;
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  setVisibleGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setZoomLevel: (zoom: number) => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  selectedNodeId: null,
  highlightedNodeIds: new Set<string>(),
  visibleNodes: [],
  visibleEdges: [],
  zoomLevel: 1,
  semanticZoomTier: "module",
  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),
  highlightNodes: (nodeIds) =>
    set({ highlightedNodeIds: new Set(nodeIds) }),
  clearHighlights: () => set({ highlightedNodeIds: new Set<string>() }),
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
}));
