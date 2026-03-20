import { useEffect, useRef, useMemo, useCallback, memo, useState } from "react";
import Graph from "graphology";
import FA2Layout from "graphology-layout-forceatlas2/worker";

import Sigma from "sigma";
import { NodeCircleProgram } from "sigma/rendering";
import { useGraphStore } from "@/store/graphStore";
import { useEditorStore, isNodeInVfsSession } from "@/store/editorStore";
import { useGraphOverview, useNodeVariables, apiFetch } from "@/api/client";
import { useConsumerSubgraph } from "@/api/nodes";
import { getSigmaZoomTier, labelThresholdForTier } from "@/graph/layout/semanticZoom";
import { buildCallInsertion } from "@/editor/completionService";

const VARIABLE_COLOR = "#ffd54f";   // local / assign / mutate
const PARAM_COLOR = "#81d4fa";      // input parameters
const ATTR_COLOR = "#ce93d8";       // attributes
const RETURN_COLOR = "#a5d6a7";     // return values
const READS_COLOR = "#ffab91";      // required data (globals, reads)
const TYPE_SHAPE_COLOR = "#4dd0e1"; // TypeShape hub nodes

/** Muted pastel palette for file/class groups. */
function generatePaletteColor(index: number): string {
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

function sizeForKind(kind: string): number {
  switch (kind) {
    case "class": return 5;
    case "module": return 6;
    case "function":
    case "method":
    case "flow_function": return 3;
    default: return 2;
  }
}

function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

function varColor(v: { is_parameter: boolean; is_attribute: boolean; edge_type: string }): string {
  if (v.is_parameter) return PARAM_COLOR;
  if (v.edge_type === "RETURNS") return RETURN_COLOR;
  if (v.edge_type === "READS") return READS_COLOR;
  if (v.is_attribute) return ATTR_COLOR;
  return VARIABLE_COLOR;
}

function AtlasOverview() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const fa2Ref = useRef<InstanceType<typeof FA2Layout> | null>(null);
  const fa2StopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draggedNode = useRef<string | null>(null);
  const isDragging = useRef(false);
  const wasDragged = useRef(false);
  const hoveredNode = useRef<string | null>(null);
  const traceRef = useRef<Set<string>>(new Set());
  const highlightRef = useRef<Set<string>>(new Set());
  const impactedRef = useRef<Set<string>>(new Set());

  // Store state
  const focusedNodeId = useGraphStore((s) => s.focusedNodeId);
  const expandedNodeId = useGraphStore((s) => s.expandedNodeId);
  const tracedVariableId = useGraphStore((s) => s.tracedVariableId);
  const highlightedNodeIds = useGraphStore((s) => s.highlightedNodeIds);
  const queryResultData = useGraphStore((s) => s.queryResultData);
  const impactedNodeIds = useGraphStore((s) => s.impactedNodeIds);
  const queryLabel = useGraphStore((s) => s.queryHighlightLabel);
  const navigateToNode = useGraphStore((s) => s.navigateToNode);
  const goHome = useGraphStore((s) => s.goHome);
  const expandNode = useGraphStore((s) => s.expandNode);
  const collapseExpanded = useGraphStore((s) => s.collapseExpanded);
  const traceVariable = useGraphStore((s) => s.traceVariable);
  const clearTrace = useGraphStore((s) => s.clearTrace);
  const showConsumers = useGraphStore((s) => s.showConsumers);
  const consumerVariableId = useGraphStore((s) => s.consumerVariableId);
  const expandHighlight = useGraphStore((s) => s.expandHighlight);
  const openNodeView = useEditorStore((s) => s.openNodeView);

  // Stable refs for callbacks
  const callbacksRef = useRef({ navigateToNode, goHome, expandNode, collapseExpanded, openNodeView, traceVariable, clearTrace, showConsumers, expandHighlight });
  callbacksRef.current = { navigateToNode, goHome, expandNode, collapseExpanded, openNodeView, traceVariable, clearTrace, showConsumers, expandHighlight };

  // Ref to track focused/expanded in event handlers without re-creating Sigma
  const focusRef = useRef({ focusedNodeId, expandedNodeId });
  focusRef.current = { focusedNodeId, expandedNodeId };

  // Indexing state
  const indexing = useGraphStore((s) => s.indexing);

  // Data fetching — lightweight overview (no source_text)
  const { data: overview, isLoading: overviewLoading, isError: overviewError, refetch: refetchOverview } = useGraphOverview(!indexing);

  // Fetch actual variable node data for the expanded node
  const { data: expandedVariables } = useNodeVariables(expandedNodeId);

  // Variable trace: find real ID from graphology node
  const tracedRealId = useMemo(() => {
    if (!tracedVariableId) return null;
    const graph = graphRef.current;
    if (!graph || !graph.hasNode(tracedVariableId)) return null;
    const attrs = graph.getNodeAttributes(tracedVariableId);
    return (typeof attrs.realNodeId === "string" ? attrs.realNodeId : null);
  }, [tracedVariableId]);

  // For trace, re-use node variables on the traced variable's origin
  const { data: traceVariables } = useNodeVariables(tracedRealId);

  // Resolve consumer variable's real ID for the type-shape consumer query
  const consumerRealId = useMemo(() => {
    if (!consumerVariableId) return null;
    const graph = graphRef.current;
    if (!graph || !graph.hasNode(consumerVariableId)) return null;
    const attrs = graph.getNodeAttributes(consumerVariableId);
    return (typeof attrs.realNodeId === "string" ? attrs.realNodeId : null);
  }, [consumerVariableId]);

  const { data: consumerSubgraph } = useConsumerSubgraph(consumerRealId);

  const overviewNodes = overview?.nodes ?? [];
  const overviewEdges = overview?.edges ?? [];

  // Track whether initial graph has been built — only rebuild once
  const [graphVersion, setGraphVersion] = useState(0);

  // Reset graph when a new codebase starts indexing — kill sigma immediately + clear state
  useEffect(() => {
    if (indexing) {
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
      setGraphVersion(0);
      prevOverviewRef.current = new Set();
      graphRef.current = null;
    }
  }, [indexing]);

  useEffect(() => {
    if (overviewNodes.length > 0 && graphVersion === 0) {
      setGraphVersion(1);
    }
  }, [overviewNodes.length, graphVersion]);

  // Build graphology graph — only on initial load (graphVersion 0→1)
  const graphData = useMemo(() => {
    if (graphVersion === 0) return null;

    const g = new Graph({ multi: true, type: "directed" });

    // Build class membership map from MEMBER_OF edges
    const classMap = new Map<string, string>();
    for (const e of overviewEdges) {
      if (e.type === "MEMBER_OF") {
        classMap.set(e.source, e.target);
      }
    }

    // Build group key per node and assign colors
    const groupColorMap = new Map<string, string>();
    let colorIndex = 0;

    function getGroupColor(groupKey: string): string {
      let color = groupColorMap.get(groupKey);
      if (!color) {
        color = generatePaletteColor(colorIndex++);
        groupColorMap.set(groupKey, color);
      }
      return color;
    }

    // Compute degree map from overview edges
    const degreeMap = new Map<string, number>();
    for (const e of overviewEdges) {
      degreeMap.set(e.source, (degreeMap.get(e.source) ?? 0) + 1);
      degreeMap.set(e.target, (degreeMap.get(e.target) ?? 0) + 1);
    }

    const nodeIdSet = new Set<string>();
    for (const n of overviewNodes) {
      if (nodeIdSet.has(n.id)) continue;
      nodeIdSet.add(n.id);

      const classId = classMap.get(n.id);
      const groupKey = classId ? `class:${classId}` : `file:${n.module_path}`;
      const color = getGroupColor(groupKey);

      const degree = degreeMap.get(n.id) ?? 0;
      const size = sizeForKind(n.kind) + Math.min(Math.log2(1 + degree) * 0.5, 3);

      g.addNode(n.id, {
        x: 0,
        y: 0,
        size,
        color,
        originalColor: color,
        label: localName(n.name),
        kind: n.kind,
        modulePath: n.module_path,
        name: n.name,
        isVariable: false,
      });
    }

    for (const e of overviewEdges) {
      if (nodeIdSet.has(e.source) && nodeIdSet.has(e.target)) {
        try {
          g.addEdge(e.source, e.target, {
            color: "rgba(255,255,255,0.008)",
            size: 0.1,
            edgeType: e.type,
            weight: 3,
          });
        } catch {
          // skip duplicate edges
        }
      }
    }

    // Add invisible star-topology edges so co-located nodes cluster together.
    // Uses a star pattern (first node as hub) instead of O(n²) all-pairs.
    const fileGroups = new Map<string, string[]>();
    g.forEachNode((node, attrs) => {
      const fp = attrs.modulePath as string;
      if (!fp) return;
      let list = fileGroups.get(fp);
      if (!list) { list = []; fileGroups.set(fp, list); }
      list.push(node);
    });
    for (const members of fileGroups.values()) {
      if (members.length < 2) continue;
      const hub = members[0]!;
      for (let i = 1; i < members.length; i++) {
        try {
          g.addEdge(hub, members[i]!, {
            color: "rgba(0,0,0,0)",
            size: 0,
            hidden: true,
            weight: 1,
            edgeType: "SAME_FILE",
          });
        } catch {
          // skip duplicate
        }
      }
    }

    // Random scatter so FA2 starts from an unbiased spread
    const spread = Math.max(Math.sqrt(g.order) * 10, 50);
    g.forEachNode((id) => {
      g.setNodeAttribute(id, "x", (Math.random() - 0.5) * spread);
      g.setNodeAttribute(id, "y", (Math.random() - 0.5) * spread);
    });

    return { g };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphVersion]);

  // Incremental graph sync — add/remove nodes without rebuilding Sigma or restarting FA2
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
  }, [overviewNodes, overviewEdges]);

  // Handle variable expansion: show real variable nodes near the parent
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    // Remove any existing variable nodes first
    const toRemove: string[] = [];
    graph.forEachNode((node, attrs) => {
      if (attrs.isVariable) toRemove.push(node);
    });
    for (const nodeId of toRemove) {
      graph.dropNode(nodeId);
    }

    // Add variable nodes from the fetched variable data
    if (expandedNodeId && expandedVariables && graph.hasNode(expandedNodeId)) {
      const parentAttrs = graph.getNodeAttributes(expandedNodeId);
      const parentX = parentAttrs.x as number;
      const parentY = parentAttrs.y as number;

      // Compute graph extent from actual node positions
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      graph.forEachNode((_, attrs) => {
        const nx = attrs.x as number;
        const ny = attrs.y as number;
        if (nx < minX) minX = nx;
        if (nx > maxX) maxX = nx;
        if (ny < minY) minY = ny;
        if (ny > maxY) maxY = ny;
      });
      const graphSpan = Math.max(maxX - minX, maxY - minY) || 100;

      // Orbit radius = ~3% of the total graph span — tight orbit
      const radius = graphSpan * 0.03;

      const angleStep = expandedVariables.length > 0 ? (2 * Math.PI) / expandedVariables.length : 0;

      expandedVariables.forEach((v, i) => {
        const angle = angleStep * i;
        const varId = `var:${v.id}`;
        if (graph.hasNode(varId)) return;

        const shortName = localName(v.name);
        const typeStr = v.type_hint ? `: ${v.type_hint}` : "";
        const label = `${shortName}${typeStr}`;
        const col = varColor(v);

        graph.addNode(varId, {
          x: parentX + radius * Math.cos(angle),
          y: parentY + radius * Math.sin(angle),
          size: 1.5,
          color: col,
          originalColor: col,
          label,
          kind: "variable",
          isVariable: true,
          realNodeId: v.id,
          fixed: true,
        });

        try {
          graph.addEdge(expandedNodeId, varId, {
            color: col + "66",
            size: 0.5,
            type: "arrow",
            edgeType: v.edge_type,
            isVariable: true,
          });
        } catch {
          // skip duplicate
        }
      });
    }

    sigmaRef.current?.refresh();
  }, [expandedNodeId, expandedVariables]);

  // Handle variable trace: highlight connected LogicNodes
  useEffect(() => {
    if (tracedVariableId && traceVariables) {
      const traced = new Set<string>();
      traced.add(tracedVariableId);
      const graph = graphRef.current;
      if (graph) {
        // Find all LogicNodes that share an edge with this variable
        for (const v of traceVariables) {
          const varNodeId = `var:${v.id}`;
          if (graph.hasNode(varNodeId)) traced.add(varNodeId);
        }
        // Also trace the origin node
        graph.forEachNode((node, attrs) => {
          if (!attrs.isVariable) {
            // Check if any variable edge connects this node to the traced variable
            for (const v of traceVariables) {
              if (v.id === tracedVariableId || `var:${v.id}` === tracedVariableId) {
                traced.add(node);
              }
            }
          }
        });
      }
      traceRef.current = traced;
    } else {
      traceRef.current = new Set();
    }
    sigmaRef.current?.refresh();
  }, [tracedVariableId, traceVariables]);

  // Handle consumer highlight: show TypeShape subgraph + highlight consumer functions
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
  }, [consumerVariableId, consumerSubgraph]);

  // Sync highlight ref and animate camera to fit highlighted nodes
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
  }, [highlightedNodeIds]);

  // Sync impacted ref and auto-clear after 10 seconds
  useEffect(() => {
    impactedRef.current = impactedNodeIds;
    sigmaRef.current?.refresh();

    if (impactedNodeIds.size > 0) {
      const timer = setTimeout(() => {
        useGraphStore.getState().clearImpactedNodes();
      }, 10000);
      return () => clearTimeout(timer);
    }
  }, [impactedNodeIds]);

  // Resolve query result node IDs against graphology keys (handles ID mismatches)
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
  }, [queryResultData]);

  // Camera animation on focus change
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
  }, []);

  // React to focusedNodeId changes
  useEffect(() => {
    animateToNode(focusedNodeId);
  }, [focusedNodeId, animateToNode]);

  // Create and manage Sigma instance
  useEffect(() => {
    const container = containerRef.current;
    if (!graphData || !container || graphData.g.order === 0) return;
    graphRef.current = graphData.g;

    // Seed the incremental sync ref so the first refetch can diff properly
    prevOverviewRef.current = new Set(overviewNodes.map((n) => n.id));

    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    const sigma = new Sigma(graphData.g, container, {
      allowInvalidContainer: true,
      defaultNodeType: "circle",
      nodeProgramClasses: { circle: NodeCircleProgram },
      defaultEdgeColor: "rgba(255,255,255,0.008)",
      defaultEdgeType: "line",
      defaultNodeColor: "#888",
      labelColor: { color: "#c0c0c0" },
      labelFont: "monospace",
      labelSize: 11,
      labelRenderedSizeThreshold: 6,
      renderEdgeLabels: false,
      hideEdgesOnMove: true,
      minCameraRatio: 0.01,
      maxCameraRatio: 10,
      nodeReducer: (node, data) => {
        const res = { ...data };
        const { focusedNodeId: fid } = focusRef.current;
        const hovered = hoveredNode.current;
        const graph = graphRef.current;
        const tracedIds = traceRef.current;
        const highlightIds = highlightRef.current;
        const impactedIds = impactedRef.current;

        // Impact analysis highlight (compose save)
        if (impactedIds.size > 0 && impactedIds.has(node)) {
          res.color = "#ff4444";
          res.highlighted = true;
          res.zIndex = 3;
          return res;
        }

        // Variable trace mode
        if (tracedIds.size > 0) {
          if (tracedIds.has(node)) {
            res.highlighted = true;
            res.zIndex = 2;
          } else {
            res.color = "rgba(60,60,60,0.12)";
            res.label = "";
            res.zIndex = 0;
          }
          return res;
        }

        // Query highlight mode
        if (highlightIds.size > 0) {
          const { expandedNodeId: eid } = focusRef.current;
          const parentHighlighted = data.isVariable && eid && highlightIds.has(eid);
          if (highlightIds.has(node) || parentHighlighted) {
            const conf = data.confidence as string | undefined;
            if (conf === "weak") {
              const orig = (data.originalColor as string) || "#888";
              res.color = orig + "88";
              res.highlighted = true;
              res.zIndex = 1;
            } else {
              res.highlighted = true;
              res.zIndex = 2;
            }
          } else {
            res.color = "rgba(60,60,60,0.12)";
            res.label = "";
            res.zIndex = 0;
          }
          // Apply focus emphasis within highlighted set
          if (fid === node) {
            res.size = (data.size as number) + 3;
          }
          return res;
        }

        // Focused mode: dim non-neighbors
        if (fid && graph) {
          const isFocused = node === fid;
          const isNeighbor = graph.hasEdge(fid, node) || graph.hasEdge(node, fid);

          if (isFocused) {
            res.highlighted = true;
            res.zIndex = 2;
            res.size = (data.size as number) + 3;
          } else if (isNeighbor || data.isVariable) {
            res.zIndex = 1;
          } else {
            res.color = "rgba(60,60,60,0.12)";
            res.label = "";
            res.zIndex = 0;
          }
        }

        // Hover highlighting
        if (hovered && graph) {
          if (node === hovered) {
            res.highlighted = true;
            res.zIndex = 2;
          } else if (graph.hasEdge(hovered, node) || graph.hasEdge(node, hovered)) {
            res.highlighted = true;
            res.zIndex = 1;
          } else if (!fid) {
            res.color = "rgba(80,80,80,0.15)";
            res.label = "";
            res.zIndex = 0;
          }
        }

        return res;
      },
      edgeReducer: (edge, data) => {
        const res = { ...data };
        const { focusedNodeId: fid } = focusRef.current;
        const hovered = hoveredNode.current;
        const graph = graphRef.current;
        const tracedIds = traceRef.current;
        const highlightIds = highlightRef.current;

        // Variable trace mode
        if (tracedIds.size > 0 && graph) {
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          if (tracedIds.has(src) && tracedIds.has(tgt)) {
            res.color = VARIABLE_COLOR;
            res.size = 1.5;
          } else {
            res.color = "rgba(60,60,60,0.03)";
          }
          return res;
        }

        // Query highlight mode
        if (highlightIds.size > 0 && graph) {
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          const srcHighlighted = highlightIds.has(src);
          const tgtHighlighted = highlightIds.has(tgt);
          const isVarEdge = data.isVariable as boolean | undefined;
          const { expandedNodeId: eid } = focusRef.current;
          const parentHighlighted = isVarEdge && eid && highlightIds.has(eid);
          if ((srcHighlighted && tgtHighlighted) || parentHighlighted) {
            res.color = "rgba(255,255,255,0.08)";
            res.size = 0.5;
          } else {
            res.color = "rgba(60,60,60,0.03)";
          }
          return res;
        }

        if (fid && graph) {
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          if (src === fid || tgt === fid) {
            const degree = graph.degree(fid);
            const alpha = degree > 30 ? 0.04 : 0.08;
            res.color = `rgba(255,255,255,${alpha})`;
            res.size = 0.5;
          } else {
            res.color = "rgba(60,60,60,0.02)";
          }
        }

        if (hovered && graph) {
          const src = graph.source(edge);
          const tgt = graph.target(edge);
          if (src === hovered || tgt === hovered) {
            const degree = graph.degree(hovered);
            const alpha = degree > 30 ? 0.03 : 0.06;
            res.color = `rgba(255,255,255,${alpha})`;
            res.size = 0.5;
          } else if (!fid) {
            res.color = "rgba(60,60,60,0.02)";
          }
        }

        return res;
      },
    });

    // Hover events — debounce refresh via rAF to avoid 60+ refreshes/sec
    let hoverRafId = 0;
    const scheduleRefresh = () => {
      cancelAnimationFrame(hoverRafId);
      hoverRafId = requestAnimationFrame(() => sigma.refresh());
    };

    sigma.on("enterNode", ({ node }) => {
      hoveredNode.current = node;
      scheduleRefresh();
      container.style.cursor = "pointer";
    });

    sigma.on("leaveNode", () => {
      hoveredNode.current = null;
      scheduleRefresh();
      container.style.cursor = "default";
    });

    // Single click: focus on node (skip if we were dragging)
    // Cmd+click: expand highlights with neighbors
    sigma.on("clickNode", ({ node, event }) => {
      if (wasDragged.current) {
        wasDragged.current = false;
        return;
      }

      // Graph autocomplete mode: click a highlighted suggestion node to insert its call
      const edState = useEditorStore.getState();
      if (edState.graphAutoComplete && edState.pendingSuggestions.length > 0) {
        const suggestion = edState.pendingSuggestions.find((s) => s.node_id === node);
        if (suggestion) {
          const varName = edState.suggestionContext?.variableName ?? "";
          const insertion = buildCallInsertion(suggestion, varName);
          // Dispatch a custom event that CodeEditor listens to for insertion
          window.dispatchEvent(new CustomEvent("bumblebee:insert-suggestion", {
            detail: { text: insertion, nodeId: node },
          }));
          edState.clearPendingSuggestions();
          return;
        }
      }

      // Graph AC mode (no pending suggestions): click to toggle node in/out of VFS session
      if (edState.graphAutoComplete) {
        const graph = graphRef.current;
        const attrs = graph?.getNodeAttributes(node);
        if (attrs?.isVariable) return; // skip variables

        if (isNodeInVfsSession(node)) {
          // Deselect — remove from VFS session
          edState.removeNodeFromVfsSession(node);
        } else {
          // Add to VFS session — fetch source_text then add
          const nodeName = typeof attrs?.name === "string" ? attrs.name : node;
          const modulePath = typeof attrs?.modulePath === "string" ? attrs.modulePath : "";
          void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
            .then((full) => {
              useEditorStore.getState().addNodeToVfsSession(
                node,
                localName(nodeName),
                full.source_text ?? "",
                modulePath,
              );
            })
            .catch((err) => console.warn(`Failed to fetch node ${node} for VFS session:`, err));
        }
        return;
      }

      const graph = graphRef.current;
      const attrs = graph?.getNodeAttributes(node);
      if (!attrs || attrs.isVariable) return;

      // TypeShape nodes: project to VFS and open in editor
      if (attrs.isTypeShape) {
        const shapeId = node.startsWith("ts:") ? node.slice(3) : node;
        const label = typeof attrs.label === "string" ? attrs.label : "TypeShape";
        void apiFetch<{ source: string; file_path: string }>(`/api/v1/vfs/type-shape/${shapeId}?project=true`)
          .then((res) => {
            callbacksRef.current.openNodeView({
              nodeId: `ts:${shapeId}`,
              name: label,
              kind: "type_shape",
              sourceText: res.source,
              modulePath: `__typeshapes__.${label}`,
            });
          })
          .catch((err) => console.warn(`Failed to project TypeShape ${shapeId}:`, err));
        return;
      }

      const nodeName = typeof attrs.name === "string" ? attrs.name : node;
      const kind = typeof attrs.kind === "string" ? attrs.kind : "";
      const modulePath = typeof attrs.modulePath === "string" ? attrs.modulePath : "";
      const isMeta = event.original.metaKey || event.original.ctrlKey;

      if (isMeta && graph) {
        // Cmd+click: expand highlight set with this node + its neighbors
        const neighbors = graph.neighbors(node).filter((n) => {
          const na = graph.getNodeAttributes(n);
          return !na.isVariable;
        });
        callbacksRef.current.expandHighlight(node, neighbors);

        // Also fetch + open in editor
        void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
          .then((full) => {
            callbacksRef.current.openNodeView({
              nodeId: node,
              name: localName(nodeName),
              kind,
              sourceText: full.source_text,
              modulePath,
            });
          })
          .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
        return;
      }

      // Plain click with active highlights: focus within set, pan to node
      if (highlightRef.current.size > 0) {
        focusRef.current = { ...focusRef.current, focusedNodeId: node };
        useGraphStore.setState({ focusedNodeId: node, selectedNodeId: null });
        // Pan to center on node without changing zoom
        const nodeVp = sigma.graphToViewport({ x: attrs.x as number, y: attrs.y as number });
        const fc = sigma.viewportToFramedGraph(nodeVp);
        sigma.getCamera().animate({ x: fc.x, y: fc.y }, { duration: 300 });
        sigma.refresh();

        void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
          .then((full) => {
            callbacksRef.current.openNodeView({
              nodeId: node,
              name: localName(nodeName),
              kind,
              sourceText: full.source_text,
              modulePath,
            });
          })
          .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
        return;
      }

      // Plain click, no highlights: navigate (existing behavior)
      callbacksRef.current.navigateToNode(node, localName(nodeName));

      // Fetch source_text on demand — overview payload omits it for performance
      void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
        .then((full) => {
          callbacksRef.current.openNodeView({
            nodeId: node,
            name: localName(nodeName),
            kind,
            sourceText: full.source_text,
            modulePath,
          });
        })
        .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
    });

    // Double click: expand or trace
    sigma.on("doubleClickNode", ({ node, preventSigmaDefault }) => {
      preventSigmaDefault();
      const attrs = graphRef.current?.getNodeAttributes(node);

      if (attrs?.isVariable) {
        callbacksRef.current.showConsumers(node);
        return;
      }

      callbacksRef.current.expandNode(node);
    });

    sigma.on("doubleClickStage", ({ preventSigmaDefault }) => {
      preventSigmaDefault();
      if (focusRef.current.focusedNodeId || traceRef.current.size > 0 || highlightRef.current.size > 0) {
        callbacksRef.current.clearTrace();
        callbacksRef.current.collapseExpanded();
        callbacksRef.current.goHome();
        sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 500 });
      }
    });

    // Node drag-and-drop
    sigma.on("downNode", ({ node, event }) => {
      isDragging.current = true;
      draggedNode.current = node;
      sigma.getCamera().disable();
      event.original.preventDefault();
      event.original.stopPropagation();
    });

    sigma.getMouseCaptor().on("mousemovebody", (event) => {
      if (!isDragging.current || !draggedNode.current) return;
      wasDragged.current = true;
      const graph = graphRef.current;
      if (!graph) return;

      const pos = sigma.viewportToGraph(event);
      graph.setNodeAttribute(draggedNode.current, "x", pos.x);
      graph.setNodeAttribute(draggedNode.current, "y", pos.y);
    });

    sigma.getMouseCaptor().on("mouseup", () => {
      if (isDragging.current) {
        isDragging.current = false;
        draggedNode.current = null;
        sigma.getCamera().enable();
      }
    });

    // Semantic zoom: adjust label threshold
    // Guard against calling setSetting on a killed Sigma instance
    // (camera animations can outlive the Sigma lifecycle)
    sigma.getCamera().on("updated", () => {
      if (sigmaRef.current !== sigma) return;
      const ratio = sigma.getCamera().ratio;
      const tier = getSigmaZoomTier(ratio);
      const threshold = labelThresholdForTier(tier);
      sigma.setSetting("labelRenderedSizeThreshold", threshold);
    });

    sigmaRef.current = sigma;

    // Async ForceAtlas2 worker — runs until settled, then stops
    try {
      fa2Ref.current = new FA2Layout(graphData.g, {
        settings: {
          barnesHutOptimize: true,
          barnesHutTheta: 0.5,
          adjustSizes: false,
          strongGravityMode: true,
          gravity: 2,
          scalingRatio: 1,
          edgeWeightInfluence: 1,
          slowDown: graphData.g.order > 300 ? 8 : 4,
        },
      });
      fa2Ref.current.start();
      fa2StopTimerRef.current = setTimeout(() => {
        fa2Ref.current?.stop();
      }, graphData.g.order > 500 ? 3000 : 1500);
    } catch (e) {
      console.warn("FA2Layout worker failed to start, graph will use static layout", e);
    }

    // If there's already a focused node, animate to it
    if (focusRef.current.focusedNodeId) {
      requestAnimationFrame(() => {
        const fid = focusRef.current.focusedNodeId;
        if (fid && graphData.g.hasNode(fid)) {
          const nodeAttrs = graphData.g.getNodeAttributes(fid);
          const nodeDisplayData = sigma.getNodeDisplayData(fid);
          if (nodeDisplayData) {
            const graphCoords = sigma.viewportToFramedGraph(
              sigma.graphToViewport({ x: nodeAttrs.x as number, y: nodeAttrs.y as number })
            );
            sigma.getCamera().animate(
              { x: graphCoords.x, y: graphCoords.y, ratio: 0.3 },
              { duration: 600 }
            );
          }
        }
      });
    }

    return () => {
      if (fa2StopTimerRef.current !== null) clearTimeout(fa2StopTimerRef.current);
      fa2Ref.current?.kill();
      fa2Ref.current = null;
      fa2StopTimerRef.current = null;
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graphData]);

  // Listen for VFS rebuild events (triggered when a node is removed from VFS session)
  useEffect(() => {
    const handler = async (e: Event) => {
      const { tabId, nodeIds } = (e as CustomEvent<{ tabId: string; nodeIds: string[] }>).detail;
      try {
        const sources = await Promise.all(
          nodeIds.map((id) =>
            apiFetch<{ source_text: string }>(`/api/v1/nodes/${id}`).then((r) => r.source_text ?? ""),
          ),
        );
        const assembled = sources.filter(Boolean).join("\n\n");
        useEditorStore.getState().updateTabContent(tabId, assembled);
        useEditorStore.getState().markClean(tabId);
      } catch (err) {
        console.warn("VFS session rebuild failed:", err);
      }
    };
    window.addEventListener("bumblebee:vfs-rebuild", handler);
    return () => window.removeEventListener("bumblebee:vfs-rebuild", handler);
  }, []);

  // Refresh sigma when focus/expand/trace/highlight state changes
  useEffect(() => {
    sigmaRef.current?.refresh();
  }, [focusedNodeId, expandedNodeId, tracedVariableId, highlightedNodeIds]);

  // Always render the container so Sigma's DOM element is never unmounted
  const showOverlay = overviewError || indexing || overviewLoading || !overview || overview.nodes.length === 0;

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div
        ref={containerRef}
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--bg-primary)",
        }}
      />
      {!showOverlay && (
        <button
          onClick={() => void refetchOverview()}
          title="Refresh graph"
          style={{
            position: "absolute",
            top: 8,
            left: 8,
            zIndex: 10,
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            color: "var(--text-secondary)",
            cursor: "pointer",
            padding: "4px 6px",
            fontSize: 13,
            lineHeight: 1,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-secondary)"; }}
        >
          &#x21bb;
        </button>
      )}
      {showOverlay && (
        <div
          className="flex flex-col items-center justify-center gap-4"
          style={{
            position: "absolute",
            inset: 0,
            background: "var(--bg-primary)",
            color: "var(--text-muted)",
            pointerEvents: "none",
          }}
        >
          {overviewError ? (
            <span className="text-sm font-mono">Failed to load graph — is the backend running?</span>
          ) : indexing ? (
            <>
              <div
                className="w-48 h-1 rounded overflow-hidden"
                style={{ background: "var(--bg-tertiary)" }}
              >
                <div
                  className="h-full rounded"
                  style={{
                    background: "var(--node-function)",
                    width: "60%",
                    animation: "pulse 1.5s ease-in-out infinite",
                  }}
                />
              </div>
              <span className="text-sm font-mono">Indexing repository...</span>
            </>
          ) : (
            <span className="text-sm font-mono">Loading graph...</span>
          )}
        </div>
      )}
      {highlightedNodeIds.size > 0 && (
        <div
          style={{
            position: "absolute",
            top: 8,
            right: 12,
            fontSize: 11,
            fontFamily: "monospace",
            color: "var(--text-primary)",
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-primary)",
            borderRadius: 4,
            padding: "4px 8px",
            pointerEvents: "none",
            userSelect: "none",
          }}
        >
          {queryLabel ? `${queryLabel}: ` : ""}{highlightedNodeIds.size} node{highlightedNodeIds.size !== 1 ? "s" : ""} selected
        </div>
      )}
      {overview && (
        <div
          style={{
            position: "absolute",
            bottom: 8,
            right: 12,
            fontSize: 10,
            fontFamily: "monospace",
            color: "var(--text-muted)",
            pointerEvents: "none",
            userSelect: "none",
          }}
        >
          {overview.nodes.length} nodes · {overview.edges.length} edges
        </div>
      )}
    </div>
  );
}

export default memo(AtlasOverview);
