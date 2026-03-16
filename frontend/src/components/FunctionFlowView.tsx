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

interface FunctionFlowViewProps {
  functionNodeId: string;
}

const FLOW_NODE_TYPES = new Set(["Statement", "ControlFlow", "Branch"]);

function FunctionFlowInner({ functionNodeId }: FunctionFlowViewProps) {
  const { data: logicPack } = useLogicPack(functionNodeId, "flow", 1);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    if (!logicPack) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const flowNodes: Node[] = logicPack.nodes
      .filter((gn) => FLOW_NODE_TYPES.has(gn.label))
      .map((gn) => ({
        id: gn.id,
        type: gn.label,
        position: { x: 0, y: 0 },
        data: {
          label:
            typeof gn.properties["name"] === "string"
              ? gn.properties["name"]
              : typeof gn.properties["code"] === "string"
                ? gn.properties["code"]
                : gn.id,
          ...gn.properties,
        },
      }));

    const nodeIds = new Set(flowNodes.map((n) => n.id));

    const flowEdges: Edge[] = logicPack.edges
      .filter((ge) => nodeIds.has(ge.source) && nodeIds.has(ge.target))
      .map((ge, idx) => {
        const base = {
          id: `ff-${ge.source}-${ge.type}-${ge.target}-${idx}`,
          source: ge.source,
          target: ge.target,
          data: ge.properties,
        };
        if (ge.type in edgeTypes) {
          return { ...base, type: ge.type };
        }
        return base;
      });

    const laid = computeTimelineLayout(flowNodes, flowEdges, "TB");
    setNodes(laid);
    setEdges(flowEdges);
  }, [logicPack]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={useCallback<OnNodesChange>(
        (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
        [],
      )}
      onEdgesChange={useCallback<OnEdgesChange>(
        (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
        [],
      )}
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

function FunctionFlowView({ functionNodeId }: FunctionFlowViewProps) {
  return (
    <ReactFlowProvider>
      <FunctionFlowInner functionNodeId={functionNodeId} />
    </ReactFlowProvider>
  );
}

export default FunctionFlowView;
