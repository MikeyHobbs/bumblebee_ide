import dagre from "@dagrejs/dagre";
import type { Node, Edge } from "@xyflow/react";

const NODE_SIZES: Record<string, { width: number; height: number }> = {
  Folder: { width: 120, height: 32 },
  Module: { width: 150, height: 40 },
  Function: { width: 160, height: 50 },
  Class: { width: 160, height: 50 },
  Variable: { width: 100, height: 100 },
  Statement: { width: 280, height: 36 },
  ControlFlow: { width: 140, height: 80 },
  Branch: { width: 140, height: 40 },
};

const DEFAULT_SIZE = { width: 140, height: 40 };

export function computeDagreLayout(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB",
): Node[] {
  if (nodes.length === 0) return [];

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 100, marginx: 30, marginy: 30 });

  for (const node of nodes) {
    const size = NODE_SIZES[node.type ?? ""] ?? DEFAULT_SIZE;
    g.setNode(node.id, { width: size.width, height: size.height });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: {
        x: (pos?.x ?? 0) - (pos?.width ?? 0) / 2,
        y: (pos?.y ?? 0) - (pos?.height ?? 0) / 2,
      },
    };
  });
}
