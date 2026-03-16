import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function ReadsEdge({
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
          stroke: "var(--edge-read)",
          strokeWidth: 1,
          strokeDasharray: "4 3",
          opacity: 0.7,
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "none",
            fontSize: 8,
            fontFamily: "monospace",
            fontWeight: 600,
            background: "var(--bg-secondary)",
            color: "var(--edge-read)",
            padding: "0 3px",
            borderRadius: 2,
            border: "1px solid var(--edge-read)",
          }}
        >
          R
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export default ReadsEdge;
