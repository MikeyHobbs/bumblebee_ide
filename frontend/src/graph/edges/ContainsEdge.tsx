import { BaseEdge, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function ContainsEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
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
      style={{
        stroke: "var(--text-muted)",
        strokeWidth: 1,
        opacity: 0.4,
      }}
    />
  );
}

export default ContainsEdge;
