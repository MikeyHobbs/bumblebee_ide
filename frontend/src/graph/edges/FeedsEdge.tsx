import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function FeedsEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        path={edgePath}
        {...(markerEnd != null ? { markerEnd } : {})}
        style={{
          stroke: "var(--node-variable)",
          strokeWidth: 1,
          strokeDasharray: "4 2",
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "none",
            fontSize: 10,
            fontFamily: "monospace",
            fontWeight: 600,
            background: "var(--bg-secondary)",
            color: "var(--node-variable)",
            padding: "0 3px",
            borderRadius: 2,
            border: "1px solid var(--node-variable)",
          }}
        >
          &rarr;
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export default FeedsEdge;
