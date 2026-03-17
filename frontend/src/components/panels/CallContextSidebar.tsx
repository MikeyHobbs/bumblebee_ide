import { useGraphStore } from "@/store/graphStore";
import { useLogicPack } from "@/api/client";
import type { GraphEdge } from "@/types/graph";

function CallContextSidebar() {
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const selectNode = useGraphStore((s) => s.selectNode);
  const { data: logicPack } = useLogicPack(selectedNodeId, "call-context", 1);

  if (!selectedNodeId) {
    return (
      <div
        className="p-3 text-xs"
        style={{ color: "var(--text-muted)" }}
      >
        Select a node to view call context
      </div>
    );
  }

  const passesTo: GraphEdge[] =
    logicPack?.edges.filter((e) => e.type === "PASSES_TO") ?? [];
  const callers: GraphEdge[] =
    logicPack?.edges.filter(
      (e) => e.type === "CALLS" && e.target === selectedNodeId,
    ) ?? [];
  const callees: GraphEdge[] =
    logicPack?.edges.filter(
      (e) => e.type === "CALLS" && e.source === selectedNodeId,
    ) ?? [];

  const handleNavigate = (nodeId: string) => {
    selectNode(nodeId);
  };

  return (
    <div
      className="flex flex-col h-full overflow-y-auto text-sm"
      style={{ background: "var(--bg-secondary)" }}
    >
      <div
        className="px-3 py-2 text-xs font-semibold border-b"
        style={{
          color: "var(--text-secondary)",
          borderColor: "var(--border)",
        }}
      >
        Call Context: {selectedNodeId}
      </div>

      {callers.length > 0 && (
        <div className="px-3 py-2">
          <div
            className="text-xs mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            Called by
          </div>
          {callers.map((e, idx) => (
            <button
              key={`caller-${idx}`}
              onClick={() => handleNavigate(e.source)}
              className="block w-full text-left px-2 py-1 text-xs font-mono border mb-1"
              style={{
                background: "var(--bg-tertiary)",
                borderColor: "var(--border)",
                color: "var(--node-function)",
                cursor: "pointer",
              }}
            >
              {e.source}
            </button>
          ))}
        </div>
      )}

      {callees.length > 0 && (
        <div className="px-3 py-2">
          <div
            className="text-xs mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            Calls
          </div>
          {callees.map((e, idx) => (
            <button
              key={`callee-${idx}`}
              onClick={() => handleNavigate(e.target)}
              className="block w-full text-left px-2 py-1 text-xs font-mono border mb-1"
              style={{
                background: "var(--bg-tertiary)",
                borderColor: "var(--border)",
                color: "var(--node-function)",
                cursor: "pointer",
              }}
            >
              {e.target}
            </button>
          ))}
        </div>
      )}

      {passesTo.length > 0 && (
        <div className="px-3 py-2">
          <div
            className="text-xs mb-1"
            style={{ color: "var(--text-muted)" }}
          >
            Data flow (PASSES_TO)
          </div>
          {passesTo.map((e, idx) => (
            <div
              key={`pass-${idx}`}
              className="flex items-center gap-1 text-xs font-mono px-2 py-1 border mb-1"
              style={{
                background: "var(--bg-tertiary)",
                borderColor: "var(--border)",
                color: "var(--edge-pass)",
              }}
            >
              <span>{e.source}</span>
              <span style={{ color: "var(--text-muted)" }}>&rarr;</span>
              <span>{e.target}</span>
            </div>
          ))}
        </div>
      )}

      {callers.length === 0 &&
        callees.length === 0 &&
        passesTo.length === 0 && (
          <div
            className="p-3 text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            No call context available
          </div>
        )}
    </div>
  );
}

export default CallContextSidebar;
