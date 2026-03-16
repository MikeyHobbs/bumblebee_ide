import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function FolderNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "folder";

  return (
    <div
      className="px-3 py-1.5 text-sm font-mono rounded border"
      style={{
        background: "var(--bg-tertiary, #1a1a1a)",
        borderColor: "var(--text-muted)",
        color: "var(--text-secondary)",
        minWidth: 80,
      }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div className="text-center">{name}/</div>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  );
}

export default FolderNode;
