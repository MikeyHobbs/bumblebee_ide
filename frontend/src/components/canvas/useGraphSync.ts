import { useEffect, useRef } from "react";
import type Graph from "graphology";
import type FA2Layout from "graphology-layout-forceatlas2/worker";
import type Sigma from "sigma";
import type { OverviewNode, OverviewEdge } from "@/api/client";

/** Muted pastel palette for file/class groups. */
export function generatePaletteColor(index: number): string {
  const hue = (index * 137.508) % 360;
  const sat = (35 + (index % 3) * 8) / 100;
  const lit = (60 + (index % 4) * 4) / 100;
  const a = sat * Math.min(lit, 1 - lit);
  const f = (n: number) => {
    const k = (n + hue / 30) % 12;
    const color = lit - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

export function sizeForKind(kind: string): number {
  switch (kind) {
    case "class": return 5;
    case "module": return 6;
    case "function":
    case "method":
    case "flow_function": return 3;
    default: return 2;
  }
}

export function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

/**
 * Incremental graph sync — add/remove nodes without rebuilding Sigma or restarting FA2.
 */
export function useGraphSync(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  fa2Ref: React.RefObject<InstanceType<typeof FA2Layout> | null>,
  fa2StopTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  overviewNodes: OverviewNode[],
  overviewEdges: OverviewEdge[],
) {
  const prevOverviewRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const graph = graphRef.current;
    const sigma = sigmaRef.current;
    if (!graph || !sigma) return;

    const prevNodeIds = prevOverviewRef.current;
    const newNodeIds = new Set(overviewNodes.map((n) => n.id));

    // Skip if this is the initial load (handled by graphData useMemo)
    if (prevNodeIds.size === 0) {
      prevOverviewRef.current = newNodeIds;
      return;
    }

    // Find added/removed nodes
    const addedNodes = overviewNodes.filter((n) => !prevNodeIds.has(n.id) && !graph.hasNode(n.id));
    const removedNodeIds = [...prevNodeIds].filter((id) => !newNodeIds.has(id) && graph.hasNode(id));

    let changed = false;

    // --- Node additions ---
    if (addedNodes.length > 0) {
      changed = true;

      // Compute bounding box of existing graph for positioning new nodes
      let maxX = -Infinity, maxY = -Infinity, minX = Infinity, minY = Infinity;
      graph.forEachNode((_, attrs) => {
        if (attrs.isVariable) return;
        const x = attrs.x as number;
        const y = attrs.y as number;
        if (x > maxX) maxX = x;
        if (x < minX) minX = x;
        if (y > maxY) maxY = y;
        if (y < minY) minY = y;
      });

      // Add new nodes at the right edge of the graph
      const offsetX = maxX + (maxX - minX) * 0.1 + 20;
      addedNodes.forEach((n, i) => {
        if (graph.hasNode(n.id)) return;
        const color = generatePaletteColor(graph.order + i);
        graph.addNode(n.id, {
          x: offsetX,
          y: (minY + maxY) / 2 + (i - addedNodes.length / 2) * 15,
          size: sizeForKind(n.kind),
          color,
          originalColor: color,
          label: localName(n.name),
          kind: n.kind,
          modulePath: n.module_path,
          name: n.name,
          isVariable: false,
        });
      });
    }

    // --- Edge sync (always runs) ---
    for (const e of overviewEdges) {
      if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
        const edgeExists = graph.edges(e.source, e.target).some(
          (eid) => graph.getEdgeAttribute(eid, "edgeType") === e.type
        );
        if (!edgeExists) {
          try {
            graph.addEdge(e.source, e.target, {
              color: "rgba(255,255,255,0.008)",
              size: 0.1,
              edgeType: e.type,
              weight: 3,
            });
            changed = true;
          } catch { /* skip duplicate */ }
        }
      }
    }

    // --- Node removals ---
    for (const id of removedNodeIds) {
      if (graph.hasNode(id)) { graph.dropNode(id); changed = true; }
    }

    prevOverviewRef.current = newNodeIds;
    if (changed) {
      sigma.refresh();
      // Restart FA2 briefly so nodes resettle with new edges/nodes
      const fa2 = fa2Ref.current;
      if (fa2) {
        if (fa2StopTimerRef.current !== null) clearTimeout(fa2StopTimerRef.current);
        try {
          fa2.start();
          fa2StopTimerRef.current = setTimeout(() => {
            fa2.stop();
          }, graph.order > 500 ? 3000 : 1500);
        } catch { /* FA2 worker may have been killed */ }
      }
    }
  }, [overviewNodes, overviewEdges, graphRef, sigmaRef, fa2Ref, fa2StopTimerRef]);

  return prevOverviewRef;
}
