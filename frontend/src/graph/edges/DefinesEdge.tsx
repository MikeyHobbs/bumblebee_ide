import { BaseEdge, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function DefinesEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <BaseEdge
      path={edgePath}
      {...(markerEnd != null ? { markerEnd } : {})}
      style={{
        stroke: "var(--text-muted)",
        strokeWidth: 1,
        strokeDasharray: "6 3",
      }}
    />
  );
}

export default DefinesEdge;
