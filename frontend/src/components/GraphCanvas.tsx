import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useViewport,
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
import { getSemanticZoomTier, filterByZoomTier } from "@/graph/layout/semanticZoom";
import { useGraphStore } from "@/store/graphStore";
import { useGraphNodes } from "@/api/client";
import type { GraphNode, GraphEdge } from "@/types/graph";

function toFlowNodes(graphNodes: GraphNode[]): Node[] {
  return graphNodes.map((gn) => ({
    id: gn.id,
    type: gn.label,
    position: { x: 0, y: 0 },
    data: {
      label: typeof gn.properties["name"] === "string" ? gn.properties["name"] : gn.id,
      ...gn.properties,
    },
  }));
}

function toFlowEdges(graphEdges: GraphEdge[]): Edge[] {
  return graphEdges.map((ge, idx) => ({
    id: `${ge.source}-${ge.type}-${ge.target}-${idx}`,
    source: ge.source,
    target: ge.target,
    type: ge.type,
    data: ge.properties,
  }));
}

function GraphCanvasInner() {
  const { zoom } = useViewport();
  const setZoomLevel = useGraphStore((s) => s.setZoomLevel);
  const selectNode = useGraphStore((s) => s.selectNode);
  const visibleGraphNodes = useGraphStore((s) => s.visibleNodes);
  const visibleGraphEdges = useGraphStore((s) => s.visibleEdges);
  const setVisibleGraph = useGraphStore((s) => s.setVisibleGraph);

  const { data: graphData } = useGraphNodes();

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    setZoomLevel(zoom);
  }, [zoom, setZoomLevel]);

  useEffect(() => {
    if (graphData?.nodes && graphData.nodes.length > 0) {
      setVisibleGraph(graphData.nodes, []);
    }
  }, [graphData, setVisibleGraph]);

  useEffect(() => {
    const tier = getSemanticZoomTier(zoom);
    const rawNodes = toFlowNodes(visibleGraphNodes);
    const rawEdges = toFlowEdges(visibleGraphEdges);
    const filtered = filterByZoomTier(rawNodes, tier);
    const filteredIds = new Set(filtered.map((n) => n.id));
    const filteredEdges = rawEdges.filter(
      (e) => filteredIds.has(e.source) && filteredIds.has(e.target),
    );
    const laid = computeForceLayout(filtered, filteredEdges);
    setNodes(laid);
    setEdges(filteredEdges);
  }, [visibleGraphNodes, visibleGraphEdges, zoom]);

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
    },
    [selectNode],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      fitView
      minZoom={0.1}
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
          switch (n.type) {
            case "Module":
              return "var(--node-module)";
            case "Class":
              return "var(--node-class)";
            case "Function":
              return "var(--node-function)";
            case "Variable":
              return "var(--node-variable)";
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
  );
}

function GraphCanvas() {
  return <GraphCanvasInner />;
}

export default GraphCanvas;
