import { useEffect, useCallback } from "react";
import type Graph from "graphology";
import type Sigma from "sigma";
import { useGraphStore } from "@/store/graphStore";

const TYPE_SHAPE_COLOR = "#4dd0e1"; // TypeShape hub nodes

export { TYPE_SHAPE_COLOR };

interface ConsumerSubgraph {
  type_shapes: Array<{ id: string; base_type: string }>;
  consumers: Array<{ id: string; confidence?: "exact" | "structural" | "weak" }>;
  edges: Array<{ type: string; source: string; target: string }>;
}

/**
 * Handle consumer highlight: show TypeShape subgraph + highlight consumer functions.
 */
export function useConsumerHighlight(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  consumerVariableId: string | null,
  consumerSubgraph: ConsumerSubgraph | undefined,
) {
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    // Clean up any previous TypeShape nodes when consumerVariableId changes
    const toRemove: string[] = [];
    graph.forEachNode((node, attrs) => {
      if (attrs.isTypeShape) toRemove.push(node);
    });
    for (const nodeId of toRemove) {
      graph.dropNode(nodeId);
    }

    if (!consumerVariableId || !consumerSubgraph) {
      sigmaRef.current?.refresh();
      return;
    }

    // Collect highlighted node IDs
    const matched = new Set<string>();
    matched.add(consumerVariableId); // include the source variable itself

    // Get source variable position for TypeShape placement
    const varAttrs = graph.hasNode(consumerVariableId)
      ? graph.getNodeAttributes(consumerVariableId)
      : null;
    const varX = (varAttrs?.x as number) ?? 0;
    const varY = (varAttrs?.y as number) ?? 0;
    const varName = typeof varAttrs?.label === "string" ? varAttrs.label : "variable";

    // Compute graph extent for sizing the TypeShape orbit
    let gMinX = Infinity, gMaxX = -Infinity, gMinY = Infinity, gMaxY = -Infinity;
    graph.forEachNode((_, a) => {
      const nx = a.x as number;
      const ny = a.y as number;
      if (nx < gMinX) gMinX = nx;
      if (nx > gMaxX) gMaxX = nx;
      if (ny < gMinY) gMinY = ny;
      if (ny > gMaxY) gMaxY = ny;
    });
    const graphSpan = Math.max(gMaxX - gMinX, gMaxY - gMinY) || 100;
    const tsRadius = graphSpan * 0.04;

    // Add TypeShape hub nodes to graphology
    const tsAngleStep = consumerSubgraph.type_shapes.length > 0
      ? (2 * Math.PI) / consumerSubgraph.type_shapes.length
      : 0;

    for (let i = 0; i < consumerSubgraph.type_shapes.length; i++) {
      const ts = consumerSubgraph.type_shapes[i]!;
      const tsNodeId = `ts:${ts.id}`;
      if (graph.hasNode(tsNodeId)) continue;

      const angle = tsAngleStep * i - Math.PI / 2;
      const label = ts.base_type || "TypeShape";

      graph.addNode(tsNodeId, {
        x: varX + tsRadius * Math.cos(angle),
        y: varY + tsRadius * Math.sin(angle),
        size: 2,
        color: TYPE_SHAPE_COLOR,
        originalColor: TYPE_SHAPE_COLOR,
        label,
        kind: "type_shape",
        isVariable: false,
        isTypeShape: true,
        fixed: true,
      });
      matched.add(tsNodeId);
    }

    // Build confidence map from consumer data
    const confidenceMap = new Map<string, "exact" | "structural" | "weak">();
    for (const cn of consumerSubgraph.consumers) {
      confidenceMap.set(cn.id, cn.confidence ?? "structural");
    }

    // Add consumer functions to highlight set, with confidence on graph nodes
    for (const cn of consumerSubgraph.consumers) {
      if (graph.hasNode(cn.id)) {
        matched.add(cn.id);
        const conf = cn.confidence ?? "structural";
        graph.setNodeAttribute(cn.id, "confidence", conf);
        // Weak matches get reduced alpha
        if (conf === "weak") {
          const orig = graph.getNodeAttribute(cn.id, "originalColor") as string;
          graph.setNodeAttribute(cn.id, "color", (orig || "#888") + "88");
        }
      }
    }

    // Add edges from the subgraph
    for (const edge of consumerSubgraph.edges) {
      // Map IDs: variables use var: prefix, type shapes use ts: prefix
      let sourceId = edge.source;
      let targetId = edge.target;

      if (edge.type === "HAS_SHAPE") {
        sourceId = consumerVariableId; // already prefixed as var:xxx
        targetId = `ts:${edge.target}`;
      } else if (edge.type === "COMPATIBLE_WITH") {
        sourceId = `ts:${edge.source}`;
        targetId = `ts:${edge.target}`;
      } else if (edge.type === "ACCEPTS") {
        sourceId = edge.source; // LogicNode ID (no prefix)
        targetId = `ts:${edge.target}`;
      }

      if (graph.hasNode(sourceId) && graph.hasNode(targetId)) {
        try {
          let edgeColor: string;
          let edgeSize: number;
          if (edge.type === "HAS_SHAPE") {
            edgeColor = TYPE_SHAPE_COLOR + "88";
            edgeSize = 1;
          } else if (edge.type === "ACCEPTS") {
            // Vary by consumer confidence
            const conf = confidenceMap.get(edge.source) ?? "structural";
            if (conf === "exact") {
              edgeColor = "#a5d6a7cc";
              edgeSize = 1.5;
            } else if (conf === "weak") {
              edgeColor = "#a5d6a744";
              edgeSize = 0.5;
            } else {
              edgeColor = "#a5d6a788";
              edgeSize = 1.0;
            }
          } else {
            edgeColor = "#ffffff44";
            edgeSize = 1;
          }
          graph.addEdge(sourceId, targetId, {
            color: edgeColor,
            size: edgeSize,
            edgeType: edge.type,
            isTypeShape: true,
          });
        } catch {
          // skip duplicate edges
        }
      }
    }

    const existing = useGraphStore.getState().highlightedNodeIds;
    const merged = new Set([...existing, ...matched]);
    useGraphStore.setState({
      highlightedNodeIds: merged,
      queryHighlightLabel: `Consumers of ${varName}`,
    });

    sigmaRef.current?.refresh();
  }, [consumerVariableId, consumerSubgraph, graphRef, sigmaRef]);
}

/**
 * Sync highlight ref and animate camera to fit highlighted nodes.
 */
export function useHighlightSync(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  highlightRef: React.MutableRefObject<Set<string>>,
  highlightedNodeIds: Set<string>,
) {
  useEffect(() => {
    const wasEmpty = highlightRef.current.size === 0;
    highlightRef.current = highlightedNodeIds;
    sigmaRef.current?.refresh();

    const sigma = sigmaRef.current;
    const graph = graphRef.current;
    if (!sigma || !graph || highlightedNodeIds.size === 0) return;

    // Only animate camera when highlights change (not on clear — goHome handles that)
    const ids = Array.from(highlightedNodeIds).filter((id) => graph.hasNode(id));
    if (ids.length === 0) return;

    if (ids.length === 1) {
      const nodeId = ids[0]!;
      const attrs = graph.getNodeAttributes(nodeId);
      const vp = sigma.graphToViewport({ x: attrs.x as number, y: attrs.y as number });
      const fc = sigma.viewportToFramedGraph(vp);
      sigma.getCamera().animate({ x: fc.x, y: fc.y, ratio: 0.1 }, { duration: 600 });
    } else {
      // Compute bounding box and animate to fit
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const id of ids) {
        const attrs = graph.getNodeAttributes(id);
        const x = attrs.x as number;
        const y = attrs.y as number;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const vp = sigma.graphToViewport({ x: cx, y: cy });
      const fc = sigma.viewportToFramedGraph(vp);

      // Estimate ratio to fit the bounding box with padding
      const spanX = maxX - minX || 1;
      const spanY = maxY - minY || 1;
      const graphExtent = Math.max(spanX, spanY);
      // Get the full graph extent for ratio calculation
      let gMinX = Infinity, gMaxX = -Infinity, gMinY = Infinity, gMaxY = -Infinity;
      graph.forEachNode((_, a) => {
        const nx = a.x as number;
        const ny = a.y as number;
        if (nx < gMinX) gMinX = nx;
        if (nx > gMaxX) gMaxX = nx;
        if (ny < gMinY) gMinY = ny;
        if (ny > gMaxY) gMaxY = ny;
      });
      const fullExtent = Math.max(gMaxX - gMinX, gMaxY - gMinY) || 1;
      const ratio = Math.max(0.05, Math.min(0.8, (graphExtent / fullExtent) * 1.5));

      sigma.getCamera().animate(
        { x: fc.x, y: fc.y, ratio },
        { duration: wasEmpty ? 600 : 400 },
      );
    }
  }, [highlightedNodeIds, graphRef, sigmaRef, highlightRef]);
}

/**
 * Sync impacted ref and auto-clear after 10 seconds.
 */
export function useImpactedSync(
  sigmaRef: React.RefObject<Sigma | null>,
  impactedRef: React.MutableRefObject<Set<string>>,
  impactedNodeIds: Set<string>,
) {
  useEffect(() => {
    impactedRef.current = impactedNodeIds;
    sigmaRef.current?.refresh();

    if (impactedNodeIds.size > 0) {
      const timer = setTimeout(() => {
        useGraphStore.getState().clearImpactedNodes();
      }, 10000);
      return () => clearTimeout(timer);
    }
  }, [impactedNodeIds, sigmaRef, impactedRef]);
}

/**
 * Resolve query result node IDs against graphology keys (handles ID mismatches).
 */
export function useQueryResultSync(
  graphRef: React.RefObject<Graph | null>,
  queryResultData: { nodes: Array<{ id: string; properties: Record<string, unknown> }> } | null,
) {
  useEffect(() => {
    const graph = graphRef.current;
    if (!queryResultData || !graph || queryResultData.nodes.length === 0) return;

    const matched = new Set<string>();

    for (const qNode of queryResultData.nodes) {
      // Direct ID match (ideal case — both use UUID)
      if (graph.hasNode(qNode.id)) {
        matched.add(qNode.id);
        continue;
      }

      // Fallback: match by name property
      const rawName = qNode.properties.name;
      const qName = typeof rawName === "string" ? rawName : qNode.id;
      graph.forEachNode((gNodeId, attrs) => {
        if (attrs.name === qName) {
          matched.add(gNodeId);
        }
      });
    }

    if (matched.size > 0) {
      useGraphStore.setState({
        highlightedNodeIds: matched,
        focusedNodeId: matched.size === 1 ? Array.from(matched)[0]! : null,
      });
    }
  }, [queryResultData, graphRef]);
}

/**
 * Camera animation on focus change.
 */
export function useAnimateToNode(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  focusedNodeId: string | null,
) {
  const animateToNode = useCallback((nodeId: string | null) => {
    const sigma = sigmaRef.current;
    if (!sigma) return;

    if (!nodeId) {
      sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 500 });
      return;
    }

    const graph = graphRef.current;
    if (!graph || !graph.hasNode(nodeId)) return;

    const attrs = graph.getNodeAttributes(nodeId);
    const nodeDisplayData = sigma.getNodeDisplayData(nodeId);
    if (nodeDisplayData) {
      const graphCoords = sigma.viewportToFramedGraph(
        sigma.graphToViewport({ x: attrs.x as number, y: attrs.y as number })
      );
      sigma.getCamera().animate(
        { x: graphCoords.x, y: graphCoords.y, ratio: 0.3 },
        { duration: 600 }
      );
    }
  }, [graphRef, sigmaRef]);

  // React to focusedNodeId changes
  useEffect(() => {
    animateToNode(focusedNodeId);
  }, [focusedNodeId, animateToNode]);
}
