import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

function FlowNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "flow";
  const description = typeof data.description === "string" ? data.description : "";

  return (
    <div
      className="px-4 py-3 text-sm font-mono border-2 border-dashed rounded-lg"
      style={{
        background: "rgba(var(--node-module-rgb, 59, 130, 246), 0.05)",
        borderColor: "var(--node-module)",
        color: "var(--text-primary)",
        minWidth: 160,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] font-bold px-1 rounded"
          style={{ background: "var(--node-module)", color: "var(--bg-primary)" }}
        >
          FLOW
        </span>
        <span className="font-semibold" style={{ color: "var(--node-module)" }}>
          {name}
        </span>
      </div>
      {description && (
        <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          {description}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default FlowNode;
