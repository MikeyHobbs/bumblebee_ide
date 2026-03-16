import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function ControlFlowNode({ data }: NodeProps) {
  const condition = typeof data.label === "string" ? data.label : "?";
  const kind = typeof data.kind === "string" ? data.kind : "if";

  return (
    <div
      className="flex items-center justify-center"
      style={{ width: 120, height: 80 }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <svg width="120" height="80" viewBox="0 0 120 80">
        <polygon
          points="60,2 118,40 60,78 2,40"
          fill="var(--bg-secondary)"
          stroke="var(--node-variable)"
          strokeWidth="1"
        />
        <text
          x="60"
          y="36"
          textAnchor="middle"
          fill="var(--node-variable)"
          fontSize="10"
          fontFamily="monospace"
        >
          {kind}
        </text>
        <text
          x="60"
          y="50"
          textAnchor="middle"
          fill="var(--text-secondary)"
          fontSize="9"
          fontFamily="monospace"
        >
          {condition.length > 14 ? condition.slice(0, 12) + ".." : condition}
        </text>
      </svg>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default ControlFlowNode;
