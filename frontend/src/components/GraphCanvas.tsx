import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  MarkerType,
  useViewport,
  useReactFlow,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "@/graph/nodes";
import { edgeTypes } from "@/graph/edges";
import { computeForceLayout } from "@/graph/layout/forceLayout";
import { computeDagreLayout } from "@/graph/layout/dagreLayout";
import { useGraphStore } from "@/store/graphStore";
import { useEditorStore } from "@/store/editorStore";
import {
  useLogicNodes,
  useNodeEdges,
  useAllEdges,
  useVariableDetail,
  type LogicNodeResponse,
} from "@/api/client";
import type { GraphNode, GraphEdge } from "@/types/graph";
import SemanticDiffPanel from "./SemanticDiff";


function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

/** Convert LogicNode API responses to React Flow nodes. */
function logicNodesToFlowNodes(nodes: LogicNodeResponse[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    type: "LogicNode",
    position: { x: 0, y: 0 },
    data: {
      label: localName(n.name),
      name: n.name,
      kind: n.kind,
      status: n.status,
      signature: n.signature,
      source_text: n.source_text,
      module_path: n.module_path,
      semantic_intent: n.semantic_intent,
      start_line: n.start_line,
      end_line: n.end_line,
    },
  }));
}

/** Convert edge API responses to React Flow edges. */
function apiEdgesToFlowEdges(
  edges: Array<{ type: string; source: string; target: string; properties: Record<string, unknown> }>,
): Edge[] {
  return edges.map((e, idx) => ({
    id: `${e.source}-${e.type}-${e.target}-${idx}`,
    source: e.source,
    target: e.target,
    type: e.type,
    data: e.properties,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--text-muted)" },
  }));
}

/** Convert legacy GraphNode/GraphEdge format to React Flow nodes/edges. */
function toFlowNodes(graphNodes: GraphNode[]): Node[] {
  return graphNodes.map((gn) => {
    const fullName = typeof gn.properties["name"] === "string" ? gn.properties["name"] : gn.id;
    const kind = typeof gn.properties["kind"] === "string" ? gn.properties["kind"] : undefined;
    return {
      id: gn.id,
      type: kind ? "LogicNode" : gn.label,
      position: { x: 0, y: 0 },
      data: {
        label: localName(fullName),
        ...gn.properties,
      },
    };
  });
}

function toFlowEdges(graphEdges: GraphEdge[]): Edge[] {
  return graphEdges.map((ge, idx) => ({
    id: `${ge.source}-${ge.type}-${ge.target}-${idx}`,
    source: ge.source,
    target: ge.target,
    type: ge.type,
    data: ge.properties,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--text-muted)" },
  }));
}


function Breadcrumb() {
  const breadcrumb = useGraphStore((s) => s.breadcrumb);
  const navigateBack = useGraphStore((s) => s.navigateBack);

  if (breadcrumb.length <= 1) return null;

  return (
    <div
      className="absolute top-3 left-3 z-10 flex items-center gap-1 px-2 py-1 text-xs font-mono"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border)",
      }}
    >
      {breadcrumb.map((entry, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && (
            <span style={{ color: "var(--text-muted)" }}>/</span>
          )}
          {i < breadcrumb.length - 1 ? (
            <button
              onClick={() => navigateBack(i)}
              className="cursor-pointer hover:underline"
              style={{ color: "var(--node-function)" }}
            >
              {entry.label}
            </button>
          ) : (
            <span style={{ color: "var(--text-primary)" }}>
              {entry.label}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

function GraphCanvasInner() {
  const { zoom } = useViewport();
  const { fitView } = useReactFlow();
  const setZoomLevel = useGraphStore((s) => s.setZoomLevel);
  const selectNode = useGraphStore((s) => s.selectNode);
  const viewMode = useGraphStore((s) => s.viewMode);
  const activeNodeId = useGraphStore((s) => s.activeNodeId);
  const navigateToNode = useGraphStore((s) => s.navigateToNode);
  const activeDiff = useGraphStore((s) => s.activeDiff);
  const setActiveDiff = useGraphStore((s) => s.setActiveDiff);

  const openNodeView = useEditorStore((s) => s.openNodeView);

  // === Data fetching ===

  // Knowledge graph: fetch all LogicNodes and edges
  const { data: allNodes } = useLogicNodes(
    undefined,
    undefined,
    500,
  );
  const { data: allEdgesData } = useAllEdges();

  // Node detail: fetch edges for the active node
  const { data: nodeOutEdges } = useNodeEdges(
    viewMode === "node-detail" ? activeNodeId : null,
    "outgoing",
  );
  const { data: nodeInEdges } = useNodeEdges(
    viewMode === "node-detail" ? activeNodeId : null,
    "incoming",
  );

  // Variable flow (legacy support)
  const { data: variableData } = useVariableDetail(
    viewMode === "variable-flow" ? activeNodeId : null,
  );

  // Query result
  const queryResultData = useGraphStore((s) => s.queryResultData);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [layoutVersion, setLayoutVersion] = useState(0);

  useEffect(() => {
    setZoomLevel(zoom);
  }, [zoom, setZoomLevel]);

  // === Knowledge Graph view (landing page) ===
  useEffect(() => {
    if (viewMode !== "knowledge-graph" || !allNodes) return;

    const flowNodes = logicNodesToFlowNodes(allNodes);
    const nodeIdSet = new Set(allNodes.map((n) => n.id));

    // Filter edges to only those whose source & target are in the node set
    const rawEdges = (allEdgesData ?? []).filter(
      (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target),
    );
    const flowEdges = apiEdgesToFlowEdges(rawEdges);

    const laid = computeForceLayout(flowNodes, flowEdges);
    setNodes(laid);
    setEdges(flowEdges);
    setLayoutVersion((v) => v + 1);
  }, [allNodes, allEdgesData, viewMode]);

  // === Node detail view ===
  useEffect(() => {
    if (viewMode !== "node-detail" || !activeNodeId || !allNodes) return;

    // Combine outgoing and incoming edges
    const allEdges = [
      ...(nodeOutEdges ?? []),
      ...(nodeInEdges ?? []),
    ];

    // Collect connected node IDs
    const connectedIds = new Set<string>();
    connectedIds.add(activeNodeId);
    for (const e of allEdges) {
      connectedIds.add(e.source);
      connectedIds.add(e.target);
    }

    // Filter to nodes that exist in the fetched data
    const nodeMap = new Map(allNodes.map((n) => [n.id, n]));
    const visibleNodeData = Array.from(connectedIds)
      .map((id) => nodeMap.get(id))
      .filter((n): n is LogicNodeResponse => n !== undefined);

    const flowNodes = logicNodesToFlowNodes(visibleNodeData);
    const flowEdges = apiEdgesToFlowEdges(allEdges);

    const laid = computeForceLayout(flowNodes, flowEdges);

    // Mark the active node as highlighted
    const withHighlight = laid.map((n) =>
      n.id === activeNodeId
        ? { ...n, data: { ...n.data, highlighted: true } }
        : n,
    );

    setNodes(withHighlight);
    setEdges(flowEdges);
    setLayoutVersion((v) => v + 1);
  }, [activeNodeId, viewMode, allNodes, nodeOutEdges, nodeInEdges]);

  // === Variable flow (legacy) ===
  useEffect(() => {
    if (viewMode !== "variable-flow" || !variableData) return;
    const rawNodes = toFlowNodes(variableData.nodes);
    const rawEdges = toFlowEdges(variableData.edges);
    const laid = computeDagreLayout(rawNodes, rawEdges, "LR");
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [variableData, viewMode]);

  // === Query result ===
  useEffect(() => {
    if (viewMode !== "query-result" || !queryResultData) return;
    const rawNodes = toFlowNodes(queryResultData.nodes);
    const rawEdges = toFlowEdges(queryResultData.edges);
    const laid = computeForceLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [queryResultData, viewMode]);

  // Re-fit the viewport whenever a new layout is applied
  useEffect(() => {
    if (layoutVersion === 0) return;
    const timer = setTimeout(() => {
      fitView({ padding: 0.1, duration: 200 });
    }, 50);
    return () => clearTimeout(timer);
  }, [layoutVersion, fitView]);

  // Editor → Graph: cursor/selection highlights matching graph nodes
  const selectedRange = useEditorStore((s) => s.selectedRange);
  const highlightNodes = useGraphStore((s) => s.highlightNodes);
  const clearHighlights = useGraphStore((s) => s.clearHighlights);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  useEffect(() => {
    if (!selectedRange) {
      clearHighlights();
      return;
    }
    const currentNodes = nodesRef.current;
    const matching = currentNodes.filter((n) => {
      const sl = typeof n.data.start_line === "number" ? n.data.start_line
        : typeof n.data.line === "number" ? n.data.line : null;
      const el = typeof n.data.end_line === "number" ? n.data.end_line : sl;
      if (sl === null || el === null) return false;
      return sl <= selectedRange.end && el >= selectedRange.start;
    });
    if (matching.length > 0) {
      highlightNodes(matching.map((n) => n.id));
    } else {
      clearHighlights();
    }
  }, [selectedRange, highlightNodes, clearHighlights]);

  // Graph → Node: apply highlight data
  const highlightedNodeIds = useGraphStore((s) => s.highlightedNodeIds);

  useEffect(() => {
    if (highlightedNodeIds.size === 0) {
      setNodes((prev) => {
        const anyHighlighted = prev.some((n) => n.data.highlighted === true);
        if (!anyHighlighted) return prev;
        return prev.map((n) =>
          n.data.highlighted ? { ...n, data: { ...n.data, highlighted: false } } : n,
        );
      });
      return;
    }
    setNodes((prev) =>
      prev.map((n) => {
        const shouldHighlight = highlightedNodeIds.has(n.id);
        if (n.data.highlighted === shouldHighlight) return n;
        return { ...n, data: { ...n.data, highlighted: shouldHighlight } };
      }),
    );
  }, [highlightedNodeIds]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      selectNode(node.id);

      const modulePath = typeof node.data.module_path === "string"
        ? node.data.module_path
        : "";
      const nodeName = typeof node.data.name === "string"
        ? node.data.name
        : node.id;
      const kind = typeof node.data.kind === "string"
        ? node.data.kind
        : "";
      const sourceText = typeof node.data.source_text === "string"
        ? node.data.source_text
        : "";

      // Open node source in editor
      if (sourceText) {
        openNodeView({
          nodeId: node.id,
          name: localName(nodeName),
          kind,
          sourceText,
          modulePath,
        });
      }

      // Drill into node on click
      if (viewMode === "knowledge-graph" && node.type === "LogicNode") {
        navigateToNode(node.id, localName(nodeName));
      } else if (viewMode === "node-detail" && node.type === "LogicNode" && node.id !== activeNodeId) {
        navigateToNode(node.id, localName(nodeName));
      } else if (node.type === "Variable") {
        useGraphStore.getState().navigateToVariable(nodeName);
      }
    },
    [viewMode, activeNodeId, selectNode, openNodeView, navigateToNode],
  );

  return (
    <div className="relative h-full w-full">
      <Breadcrumb />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.05}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
        className="bg-[var(--bg-primary)]"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border)"
        />
        <MiniMap
          nodeColor={(n) => {
            const kind = typeof n.data?.kind === "string" ? n.data.kind : "";
            switch (kind) {
              case "function":
              case "method":
              case "flow_function":
                return "var(--node-function)";
              case "class":
                return "var(--node-class)";
              default:
                return "var(--text-muted)";
            }
          }}
          maskColor="rgba(0, 0, 0, 0.7)"
          style={{ background: "var(--bg-secondary)" }}
        />
        <Controls
          showInteractive={false}
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
        />
      </ReactFlow>
      <SemanticDiffPanel diff={activeDiff} onClose={() => setActiveDiff(null)} />
    </div>
  );
}

function GraphCanvas() {
  return <GraphCanvasInner />;
}

export default GraphCanvas;
