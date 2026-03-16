import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function StatementNode({ data }: NodeProps) {
  const code = typeof data.label === "string" ? data.label : "";
  const line = typeof data.line === "number" ? data.line : null;

  return (
    <div
      className="px-2 py-1 text-xs font-mono border"
      style={{
        background: "var(--bg-tertiary)",
        borderColor: "var(--border)",
        color: "var(--text-primary)",
        maxWidth: 280,
        whiteSpace: "pre",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="flex items-center gap-2">
        {line !== null && (
          <span style={{ color: "var(--text-muted)", minWidth: 24 }}>
            {line}
          </span>
        )}
        <span>{code}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default StatementNode;
