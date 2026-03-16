import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function FunctionNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "fn";
  const params = typeof data.params === "string" ? data.params : "";
  const line = typeof data.line === "number" ? data.line : null;

  return (
    <div
      className="px-3 py-2 text-sm font-mono border"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--node-function)",
        color: "var(--text-primary)",
        minWidth: 100,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="font-semibold" style={{ color: "var(--node-function)" }}>
        {name}
        <span style={{ color: "var(--text-secondary)" }}>
          ({params})
        </span>
      </div>
      {line !== null && (
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          L{line}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default FunctionNode;
