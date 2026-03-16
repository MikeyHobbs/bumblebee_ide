import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function TerminalNode({ data }: NodeProps) {
  const label = typeof data.label === "string" ? data.label : "START";

  return (
    <div
      className="flex items-center justify-center text-xs font-mono font-semibold"
      style={{
        width: 80,
        height: 28,
        borderRadius: 14,
        background: "var(--bg-tertiary)",
        border: "1px solid var(--border)",
        color: "var(--text-muted)",
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      {label}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default TerminalNode;
