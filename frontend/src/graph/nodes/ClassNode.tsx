import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function ClassNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "Class";
  const methods =
    Array.isArray(data.methods) ? data.methods.length : 0;

  return (
    <div
      className="px-3 py-2 text-sm font-mono border"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--node-class)",
        color: "var(--text-primary)",
        minWidth: 120,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="font-semibold" style={{ color: "var(--node-class)" }}>
        {name}
      </div>
      {methods > 0 && (
        <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
          {methods} method{methods !== 1 ? "s" : ""}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default ClassNode;
