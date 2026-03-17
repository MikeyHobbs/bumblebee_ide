import { useEffect, useState, useCallback } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "@/graph/nodes";
import { edgeTypes } from "@/graph/edges";
import { computeTimelineLayout } from "@/graph/layout/timelineLayout";
import { useLogicPack } from "@/api/client";
import { useGraphStore } from "@/store/graphStore";

function LogicPackInner() {
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const { data: logicPack } = useLogicPack(selectedNodeId);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    if (!logicPack) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const flowNodes: Node[] = logicPack.nodes.map((gn) => ({
      id: gn.id,
      type: gn.label,
      position: { x: 0, y: 0 },
      data: {
        label:
          typeof gn.properties["name"] === "string"
            ? gn.properties["name"]
            : gn.id,
        ...gn.properties,
      },
    }));

    const flowEdges: Edge[] = logicPack.edges.map((ge, idx) => ({
      id: `lp-${ge.source}-${ge.type}-${ge.target}-${idx}`,
      source: ge.source,
      target: ge.target,
      type: ge.type,
      data: ge.properties,
    }));

    const laid = computeTimelineLayout(flowNodes, flowEdges, "TB");
    setNodes(laid);
    setEdges(flowEdges);
  }, [logicPack]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  if (!selectedNodeId) {
    return (
      <div
        className="flex items-center justify-center h-full text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        Select a node to view its Logic Pack
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      fitView
      proOptions={{ hideAttribution: true }}
      className="bg-[var(--bg-primary)]"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={16}
        size={1}
        color="var(--border)"
      />
    </ReactFlow>
  );
}

function LogicPackPanel() {
  return (
    <ReactFlowProvider>
      <LogicPackInner />
    </ReactFlowProvider>
  );
}

export default LogicPackPanel;
