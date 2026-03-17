import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function ClassNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "Class";
  const isExternal = data.external === true;

  return (
    <div
      className="px-3 py-2 text-sm font-mono border"
      style={{
        background: "var(--bg-secondary)",
        borderColor: isExternal ? "var(--text-muted)" : "var(--node-class)",
        borderStyle: isExternal ? "dashed" : "solid",
        color: "var(--text-primary)",
        opacity: isExternal ? 0.7 : 1,
        minWidth: 120,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="font-semibold" style={{ color: isExternal ? "var(--text-muted)" : "var(--node-class)" }}>
        {name}
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default memo(ClassNode);
