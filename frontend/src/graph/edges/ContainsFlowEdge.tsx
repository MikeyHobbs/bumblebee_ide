import { memo } from "react";
import { BaseEdge, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function ContainsFlowEdge({
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
        stroke: "var(--node-module)",
        strokeWidth: 1,
        strokeDasharray: "6 3",
      }}
    />
  );
}

export default memo(ContainsFlowEdge);
