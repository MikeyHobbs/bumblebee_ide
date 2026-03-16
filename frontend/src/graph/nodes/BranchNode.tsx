import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function BranchNode({ data }: NodeProps) {
  const label = typeof data.label === "string" ? data.label : "branch";

  return (
    <div
      className="px-3 py-2 text-sm font-mono border-l-2"
      style={{
        background: "var(--bg-tertiary)",
        borderLeftColor: "var(--node-variable)",
        color: "var(--text-primary)",
        minWidth: 80,
        minHeight: 40,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div
        className="text-xs font-semibold mb-1"
        style={{ color: "var(--node-variable)" }}
      >
        {label}
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default BranchNode;
