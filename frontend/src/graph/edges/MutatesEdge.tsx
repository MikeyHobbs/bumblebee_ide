import { BaseEdge, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function MutatesEdge({
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
        stroke: "var(--edge-mutation)",
        strokeWidth: 2,
        strokeDasharray: "6 3",
        animation: "dash 0.5s linear infinite",
      }}
    />
  );
}

export default MutatesEdge;
