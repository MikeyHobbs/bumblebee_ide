import * as dagre from "@dagrejs/dagre";
import type { Node, Edge } from "@xyflow/react";

export function computeTimelineLayout(
  nodes: Node[],
  edges: Edge[],
  direction: "LR" | "TB" = "LR",
): Node[] {
  if (nodes.length === 0) return [];

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 80,
    marginx: 20,
    marginy: 20,
  });

  for (const node of nodes) {
    g.setNode(node.id, { width: 160, height: 60 });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const dagreNode = g.node(node.id) as { x?: number; y?: number } | undefined;
    return {
      ...node,
      position: {
        x: (dagreNode?.x ?? 0) - 80,
        y: (dagreNode?.y ?? 0) - 30,
      },
    };
  });
}
