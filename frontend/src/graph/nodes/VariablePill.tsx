import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function VariablePill({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "var";
  const typeHint = typeof data.type_hint === "string" ? data.type_hint : null;

  return (
    <div
      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono rounded-full border"
      style={{
        background: "var(--bg-tertiary)",
        borderColor: "var(--node-variable)",
        color: "var(--node-variable)",
      }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <span>{name}</span>
      {typeHint !== null && (
        <span style={{ color: "var(--text-muted)" }}>: {typeHint}</span>
      )}
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  );
}

export default memo(VariablePill);
