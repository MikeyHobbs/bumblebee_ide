import { useState } from "react";
import type { SemanticDiff } from "@/types/graph";

interface SemanticDiffProps {
  diff: SemanticDiff | null;
  onClose: () => void;
}

function SemanticDiffPanel({ diff, onClose }: SemanticDiffProps) {
  const [expanded, setExpanded] = useState(true);

  if (!diff) return null;

  const totalChanges = diff.added_nodes.length + diff.removed_nodes.length + diff.modified_nodes.length;
  if (totalChanges === 0 && diff.added_edges.length === 0 && diff.removed_edges.length === 0) {
    return (
      <div
        className="absolute bottom-3 right-3 z-10 px-3 py-2 text-xs font-mono rounded"
        style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
      >
        No differences found
        <button onClick={onClose} className="ml-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]">x</button>
      </div>
    );
  }

  return (
    <div
      className="absolute bottom-3 right-3 z-10 text-xs font-mono rounded overflow-hidden"
      style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", maxWidth: 320, maxHeight: "50vh" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer"
        style={{ borderBottom: "1px solid var(--border)" }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ color: "var(--text-primary)" }}>
          Diff: {diff.added_nodes.length} added, {diff.removed_nodes.length} removed, {diff.modified_nodes.length} modified
        </span>
        <div className="flex gap-1">
          <span>{expanded ? "\u2212" : "+"}</span>
          <button onClick={(e) => { e.stopPropagation(); onClose(); }} className="hover:text-[var(--text-primary)]" style={{ color: "var(--text-muted)" }}>x</button>
        </div>
      </div>

      {expanded && (
        <div className="px-3 py-2 overflow-auto" style={{ maxHeight: "40vh" }}>
          {diff.added_nodes.length > 0 && (
            <div className="mb-2">
              <div className="font-semibold mb-1" style={{ color: "#22c55e" }}>Added ({diff.added_nodes.length})</div>
              {diff.added_nodes.map((n) => (
                <div key={n.id} className="pl-2 py-0.5" style={{ color: "var(--text-secondary)" }}>
                  <span style={{ color: "#22c55e" }}>+ </span>{n.name} <span style={{ color: "var(--text-muted)" }}>({n.kind})</span>
                </div>
              ))}
            </div>
          )}
          {diff.removed_nodes.length > 0 && (
            <div className="mb-2">
              <div className="font-semibold mb-1" style={{ color: "#ef4444" }}>Removed ({diff.removed_nodes.length})</div>
              {diff.removed_nodes.map((n) => (
                <div key={n.id} className="pl-2 py-0.5" style={{ color: "var(--text-secondary)" }}>
                  <span style={{ color: "#ef4444" }}>- </span>{n.name} <span style={{ color: "var(--text-muted)" }}>({n.kind})</span>
                </div>
              ))}
            </div>
          )}
          {diff.modified_nodes.length > 0 && (
            <div className="mb-2">
              <div className="font-semibold mb-1" style={{ color: "#eab308" }}>Modified ({diff.modified_nodes.length})</div>
              {diff.modified_nodes.map((n) => (
                <div key={n.id} className="pl-2 py-0.5" style={{ color: "var(--text-secondary)" }}>
                  <span style={{ color: "#eab308" }}>~ </span>{n.id.slice(0, 8)}...
                </div>
              ))}
            </div>
          )}
          {(diff.added_edges.length > 0 || diff.removed_edges.length > 0) && (
            <div className="mt-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
              <div style={{ color: "var(--text-muted)" }}>
                Edges: +{diff.added_edges.length} / -{diff.removed_edges.length}
              </div>
            </div>
          )}
          {(diff.added_variables.length > 0 || diff.removed_variables.length > 0) && (
            <div className="mt-1">
              <div style={{ color: "var(--text-muted)" }}>
                Variables: +{diff.added_variables.length} / -{diff.removed_variables.length}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SemanticDiffPanel;
