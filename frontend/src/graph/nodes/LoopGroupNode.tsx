import type { NodeProps } from "@xyflow/react";

function LoopGroupNode({ data }: NodeProps) {
  const width = typeof data.width === "number" ? data.width : 200;
  const height = typeof data.height === "number" ? data.height : 100;
  const label = typeof data.label === "string" ? data.label : "";

  return (
    <div
      style={{
        width,
        height,
        border: "1px dashed var(--node-variable)",
        borderRadius: 8,
        background: "rgba(232, 168, 56, 0.04)",
        position: "relative",
        pointerEvents: "none",
      }}
    >
      <span
        className="absolute top-1 left-2 text-[10px] font-mono"
        style={{ color: "var(--node-variable)", opacity: 0.6 }}
      >
        {label}
      </span>
    </div>
  );
}

export default LoopGroupNode;
