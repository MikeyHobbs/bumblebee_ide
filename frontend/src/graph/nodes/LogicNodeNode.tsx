import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

const KIND_CONFIG: Record<string, { color: string; icon: string }> = {
  function: { color: "var(--node-function)", icon: "fn" },
  method: { color: "var(--node-function)", icon: "m()" },
  class: { color: "var(--node-class)", icon: "C" },
  constant: { color: "var(--text-muted)", icon: "K" },
  type_alias: { color: "var(--text-muted)", icon: "T" },
  flow_function: { color: "var(--node-module)", icon: "F>" },
};

function LogicNodeNode({ data }: NodeProps) {
  const name = typeof data.label === "string" ? data.label : "node";
  const kind = typeof data.kind === "string" ? data.kind : "function";
  const status = typeof data.status === "string" ? data.status : "active";
  const signature = typeof data.signature === "string" ? data.signature : "";
  const highlighted = data.highlighted === true;
  const config = KIND_CONFIG[kind] ?? KIND_CONFIG.function!;

  const sigDisplay = signature.length > 50 ? signature.slice(0, 47) + "..." : signature;

  return (
    <div
      className="px-3 py-2 text-sm font-mono border rounded"
      style={{
        background: "var(--bg-secondary)",
        borderColor: highlighted ? "var(--border-focus)" : config.color,
        borderWidth: highlighted ? 2 : 1,
        color: "var(--text-primary)",
        minWidth: 120,
        boxShadow: highlighted ? `0 0 8px ${config.color}` : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] font-bold px-1 rounded"
          style={{ background: config.color, color: "var(--bg-primary)" }}
        >
          {config.icon}
        </span>
        <span className="font-semibold" style={{ color: config.color }}>
          {name}
        </span>
        {status === "deprecated" && (
          <span className="w-2 h-2 rounded-full bg-red-500 inline-block" title="Deprecated" />
        )}
      </div>
      {sigDisplay && (
        <div className="text-xs mt-1 truncate" style={{ color: "var(--text-muted)", maxWidth: 200 }}>
          {sigDisplay}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default LogicNodeNode;
