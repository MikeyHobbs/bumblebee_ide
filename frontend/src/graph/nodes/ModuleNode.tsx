import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function ModuleNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "module";

  return (
    <div
      className="px-3 py-2 text-sm font-mono rounded-md border"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--node-module)",
        color: "var(--text-primary)",
        minWidth: 100,
      }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div className="text-center">{name}</div>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  );
}

export default memo(ModuleNode);
