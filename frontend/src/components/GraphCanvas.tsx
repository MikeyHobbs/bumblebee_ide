import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  MarkerType,
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
import {
  useVariableDetail,
} from "@/api/client";
import type { GraphNode, GraphEdge } from "@/types/graph";
import SemanticDiffPanel from "./SemanticDiff";
import AtlasOverview from "./AtlasOverview";


function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
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


/** Legacy ReactFlow views for variable-flow and query-result */
function LegacyReactFlowView() {
  const viewMode = useGraphStore((s) => s.viewMode);
  const activeNodeId = useGraphStore((s) => s.activeNodeId);
  const activeDiff = useGraphStore((s) => s.activeDiff);
  const setActiveDiff = useGraphStore((s) => s.setActiveDiff);

  // Variable flow
  const { data: variableData } = useVariableDetail(
    viewMode === "variable-flow" ? activeNodeId : null,
  );

  // Query result
  const queryResultData = useGraphStore((s) => s.queryResultData);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Variable flow
  useEffect(() => {
    if (viewMode !== "variable-flow" || !variableData) return;
    const rawNodes = toFlowNodes(variableData.nodes);
    const rawEdges = toFlowEdges(variableData.edges);
    const laid = computeDagreLayout(rawNodes, rawEdges, "LR");
    setNodes(laid);
    setEdges(rawEdges);
  }, [variableData, viewMode]);

  // Query result
  useEffect(() => {
    if (viewMode !== "query-result" || !queryResultData) return;
    const rawNodes = toFlowNodes(queryResultData.nodes);
    const rawEdges = toFlowEdges(queryResultData.edges);
    const laid = computeForceLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
  }, [queryResultData, viewMode]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  return (
    <div className="relative h-full w-full">
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
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
      </ReactFlowProvider>
      <SemanticDiffPanel diff={activeDiff} onClose={() => setActiveDiff(null)} />
    </div>
  );
}


function GraphCanvas() {
  const viewMode = useGraphStore((s) => s.viewMode);
  const activeDiff = useGraphStore((s) => s.activeDiff);
  const setActiveDiff = useGraphStore((s) => s.setActiveDiff);

  // Knowledge graph: single Sigma canvas
  if (viewMode === "knowledge-graph") {
    return (
      <div className="relative h-full w-full">
        <AtlasOverview />
        <SemanticDiffPanel diff={activeDiff} onClose={() => setActiveDiff(null)} />
      </div>
    );
  }

  // Legacy views: variable-flow, query-result
  return <LegacyReactFlowView />;
}

export default GraphCanvas;
