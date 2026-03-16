import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";

interface BadgeInfo {
  text: string;
  color: string;
}

function getBadge(kind: string, sourceText: string): BadgeInfo | null {
  switch (kind) {
    case "return":
      return { text: "RET", color: "var(--edge-mutation)" };
    case "yield":
      return { text: "YLD", color: "#9b59b6" };
    case "raise":
      return { text: "ERR", color: "var(--edge-mutation)" };
    case "assert":
      return { text: "AST", color: "var(--node-variable)" };
    case "pass":
      return { text: "---", color: "var(--text-muted)" };
    case "delete":
      return { text: "DEL", color: "var(--text-secondary)" };
    case "global":
      return { text: "GLB", color: "var(--text-secondary)" };
    case "nonlocal":
      return { text: "NL", color: "var(--text-secondary)" };
    case "assignment":
      return { text: "=", color: "var(--node-variable)" };
    case "expression":
      return sourceText.includes("(")
        ? { text: "f()", color: "var(--node-function)" }
        : null;
    default:
      return null;
  }
}

function StatementNode({ data }: NodeProps) {
  const code = typeof data.label === "string" ? data.label : "";
  const line = typeof data.line === "number" ? data.line : null;
  const kind = typeof data.kind === "string" ? data.kind : "";
  const sourceText = typeof data.source_text === "string" ? data.source_text : code;
  const isReturn = kind === "return";
  const highlighted = data.highlighted === true;
  const duplicateGroup = typeof data.duplicateGroup === "string" ? data.duplicateGroup : null;
  const nestingDepth = typeof data.nestingDepth === "number" ? data.nestingDepth : 0;
  const badge = getBadge(kind, sourceText);

  const depthClamped = Math.min(nestingDepth, 5);
  const borderLeftWidth = depthClamped > 0 ? 2 + depthClamped : 0;
  const borderLeftOpacity = 0.2 + depthClamped * 0.15;

  return (
    <div
      className="relative px-2 py-1 text-xs font-mono border"
      style={{
        background: isReturn ? "rgba(217,68,68,0.08)" : "var(--bg-tertiary)",
        borderColor: isReturn ? "var(--edge-mutation)" : "var(--border)",
        borderWidth: isReturn ? 2 : 1,
        borderLeftWidth: borderLeftWidth > 0 ? borderLeftWidth : undefined,
        borderLeftColor: borderLeftWidth > 0
          ? `rgba(96, 165, 250, ${borderLeftOpacity})`
          : undefined,
        color: "var(--text-primary)",
        maxWidth: 280,
        whiteSpace: "pre",
        overflow: "hidden",
        textOverflow: "ellipsis",
        boxShadow: highlighted ? "0 0 0 2px var(--node-function)" : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <div className="flex items-center gap-2">
        {badge && (
          <span style={{ color: badge.color, fontWeight: 600, fontSize: 9 }}>
            {badge.text}
          </span>
        )}
        {line !== null && (
          <span style={{ color: "var(--text-muted)", minWidth: 24 }}>
            {line}
          </span>
        )}
        <span>{code}</span>
      </div>
      {duplicateGroup && (
        <span
          className="absolute top-1 right-1"
          style={{
            width: 4,
            height: 4,
            borderRadius: "50%",
            background: duplicateGroup,
            display: "inline-block",
          }}
        />
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

export default StatementNode;
