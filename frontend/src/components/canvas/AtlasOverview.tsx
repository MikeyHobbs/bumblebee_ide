import { useEffect, useRef, useMemo, memo, useState } from "react";
import Graph from "graphology";
import FA2Layout from "graphology-layout-forceatlas2/worker";

import Sigma from "sigma";
import { NodeCircleProgram } from "sigma/rendering";
import { useGraphStore } from "@/store/graphStore";
import { useEditorStore } from "@/store/editorStore";
import { useGraphOverview, useNodeVariables, apiFetch } from "@/api/client";
import { useConsumerSubgraph } from "@/api/nodes";

import { generatePaletteColor, sizeForKind, localName, useGraphSync } from "./useGraphSync";
import { VARIABLE_COLOR, useVariableExpansion, useVariableTrace } from "./useVariableExpansion";
import { useConsumerHighlight, useHighlightSync, useImpactedSync, useQueryResultSync, useAnimateToNode } from "./useGraphHighlight";
import { useGraphInteractions } from "./useGraphInteractions";

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

  // --- Extracted hooks ---
  const prevOverviewRef = useGraphSync(graphRef, sigmaRef, fa2Ref, fa2StopTimerRef, overviewNodes, overviewEdges);
  useVariableExpansion(graphRef, sigmaRef, expandedNodeId, expandedVariables);
  useVariableTrace(graphRef, sigmaRef, traceRef, tracedVariableId, traceVariables);
  useConsumerHighlight(graphRef, sigmaRef, consumerVariableId, consumerSubgraph);
  useHighlightSync(graphRef, sigmaRef, highlightRef, highlightedNodeIds);
  useImpactedSync(sigmaRef, impactedRef, impactedNodeIds);
  useQueryResultSync(graphRef, queryResultData);
  useAnimateToNode(graphRef, sigmaRef, focusedNodeId);

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

  // Register Sigma event handlers (extracted hook)
  useGraphInteractions(
    sigmaRef.current,
    containerRef.current,
    graphRef,
    sigmaRef,
    focusRef,
    hoveredNode,
    wasDragged,
    isDragging,
    draggedNode,
    callbacksRef,
    highlightRef,
    traceRef,
  );

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
