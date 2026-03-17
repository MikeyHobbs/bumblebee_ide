import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function BranchNode({ data }: NodeProps) {
  const label = typeof data.label === "string" ? data.label : "branch";
  const highlighted = data.highlighted === true;
  const duplicateGroup = typeof data.duplicateGroup === "string" ? data.duplicateGroup : null;
  const nestingDepth = typeof data.nestingDepth === "number" ? data.nestingDepth : 0;

  const depthClamped = Math.min(nestingDepth, 5);
  const borderLeftWidth = 2 + depthClamped;
  const borderLeftOpacity = 0.2 + depthClamped * 0.15;

  return (
    <div
      className="relative px-3 py-2 text-sm font-mono"
      style={{
        background: "var(--bg-tertiary)",
        borderLeft: `${borderLeftWidth}px solid rgba(96, 165, 250, ${borderLeftOpacity})`,
        color: "var(--text-primary)",
        minWidth: 80,
        minHeight: 40,
        boxShadow: highlighted ? "0 0 0 2px var(--node-function)" : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div
        className="text-xs font-semibold mb-1"
        style={{ color: "var(--node-variable)" }}
      >
        {label}
      </div>
      {duplicateGroup && (
        <span
          className="absolute top-1 right-1"
          style={{
            width: 4,
            height: 4,
            borderRadius: "50%",
            background: duplicateGroup,
            display: "inline-block",
          }}
        />
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default memo(BranchNode);
