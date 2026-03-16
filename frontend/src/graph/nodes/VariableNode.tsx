import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function VariableNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "var";

  return (
    <div
      className="flex items-center justify-center text-sm font-mono"
      style={{ width: 80, height: 80 }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div
        className="flex items-center justify-center border"
        style={{
          width: 60,
          height: 60,
          background: "var(--bg-secondary)",
          borderColor: "var(--node-variable)",
          color: "var(--node-variable)",
          transform: "rotate(45deg)",
        }}
      >
        <span style={{ transform: "rotate(-45deg)" }}>{name}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default VariableNode;
