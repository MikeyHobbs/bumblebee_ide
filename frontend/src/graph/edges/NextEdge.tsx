import { memo } from "react";
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function NextEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const branchKind = typeof data?.branch_kind === "string" ? data.branch_kind : "";

  return (
    <>
      <BaseEdge
        path={edgePath}
        {...(markerEnd != null ? { markerEnd } : {})}
        style={{
          stroke: "var(--text-muted)",
          strokeWidth: 1.5,
          opacity: 0.7,
        }}
      />
      {branchKind && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "none",
              fontSize: 9,
              fontFamily: "monospace",
              background: "var(--bg-secondary)",
              color: "var(--node-variable)",
              padding: "1px 4px",
              borderRadius: 2,
            }}
          >
            {branchKind}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(NextEdge);
