import { useGraphStore } from "@/store/graphStore";
import { useLogicPack } from "@/api/client";
import { useTypeShapeDetail } from "@/api/nodes";
import type { GraphEdge } from "@/types/graph";

function TypeShapePanel({ shapeId }: { shapeId: string }) {
  const { data: detail, isLoading } = useTypeShapeDetail(shapeId);
  const selectTypeShape = useGraphStore((s) => s.selectTypeShape);

  if (isLoading) {
    return (
      <div className="p-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Loading TypeShape...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-3 text-xs" style={{ color: "var(--text-muted)" }}>
        TypeShape not found
      </div>
    );
  }

  const def = detail.definition;
  const attrs = (def.attrs as string[]) ?? [];
  const methods = (def.methods as string[]) ?? [];
  const subscripts = (def.subscripts as string[]) ?? [];
  const kind = (def.kind as string) ?? detail.kind;
  const typeHint = (def.type as string) ?? "";
  const conn = detail.connections;

  return (
    <div
      className="flex flex-col h-full overflow-y-auto text-sm"
      style={{ background: "var(--bg-secondary)" }}
    >
      <div
        className="px-3 py-2 text-xs font-semibold border-b flex items-center justify-between"
        style={{ color: "var(--text-secondary)", borderColor: "var(--border)" }}
      >
        <span>TypeShape: {detail.base_type || typeHint || shapeId.slice(0, 8)}</span>
        <button
          onClick={() => selectTypeShape(null)}
          className="text-xs px-1"
          style={{ color: "var(--text-muted)", cursor: "pointer" }}
        >
          &times;
        </button>
      </div>

      <div className="px-3 py-2">
        <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Kind</div>
        <div className="text-xs font-mono" style={{ color: "#4dd0e1" }}>{kind}</div>
      </div>

      {detail.base_type && (
        <div className="px-3 py-1">
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Base type</div>
          <div className="text-xs font-mono" style={{ color: "var(--text-primary)" }}>{detail.base_type}</div>
        </div>
      )}

      {typeHint && (
        <div className="px-3 py-1">
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Type hint</div>
          <div className="text-xs font-mono" style={{ color: "var(--text-primary)" }}>{typeHint}</div>
        </div>
      )}

      {attrs.length > 0 && (
        <div className="px-3 py-2">
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Attributes ({attrs.length})
          </div>
          {attrs.map((a) => (
            <div key={a} className="text-xs font-mono px-2 py-0.5" style={{ color: "var(--text-primary)" }}>
              .{a}
            </div>
          ))}
        </div>
      )}

      {methods.length > 0 && (
        <div className="px-3 py-2">
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Methods ({methods.length})
          </div>
          {methods.map((m) => (
            <div key={m} className="text-xs font-mono px-2 py-0.5" style={{ color: "var(--text-primary)" }}>
              .{m}()
            </div>
          ))}
        </div>
      )}

      {subscripts.length > 0 && (
        <div className="px-3 py-2">
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Subscripts ({subscripts.length})
          </div>
          {subscripts.map((s) => (
            <div key={s} className="text-xs font-mono px-2 py-0.5" style={{ color: "var(--text-primary)" }}>
              [{s}]
            </div>
          ))}
        </div>
      )}

      {conn.variables.length > 0 && (
        <div className="px-3 py-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Variables ({conn.variables.length})
          </div>
          {conn.variables.map((v) => (
            <div
              key={v.id}
              className="text-xs font-mono px-2 py-0.5"
              style={{ color: "var(--node-variable)" }}
            >
              {v.name}{v.type_hint ? `: ${v.type_hint}` : ""}
            </div>
          ))}
        </div>
      )}

      {conn.accepting_functions.length > 0 && (
        <div className="px-3 py-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Accepted by ({conn.accepting_functions.length})
          </div>
          {conn.accepting_functions.map((f) => (
            <div
              key={f.id}
              className="text-xs font-mono px-2 py-0.5"
              style={{ color: "var(--node-function)" }}
            >
              {f.name}
            </div>
          ))}
        </div>
      )}

      {conn.producing_functions.length > 0 && (
        <div className="px-3 py-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Produced by ({conn.producing_functions.length})
          </div>
          {conn.producing_functions.map((f) => (
            <div
              key={f.id}
              className="text-xs font-mono px-2 py-0.5"
              style={{ color: "var(--node-function)" }}
            >
              {f.name}
            </div>
          ))}
        </div>
      )}

      {conn.compatible_shapes.length > 0 && (
        <div className="px-3 py-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Compatible shapes ({conn.compatible_shapes.length})
          </div>
          {conn.compatible_shapes.map((s) => (
            <button
              key={s.id}
              onClick={() => selectTypeShape(s.id)}
              className="block text-xs font-mono px-2 py-0.5"
              style={{ color: "#4dd0e1", cursor: "pointer" }}
            >
              {s.base_type || s.id.slice(0, 8)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CallContextSidebar() {
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const selectedTypeShapeId = useGraphStore((s) => s.selectedTypeShapeId);
  const selectNode = useGraphStore((s) => s.selectNode);
  const { data: logicPack } = useLogicPack(selectedNodeId, "call-context", 1);

  // TypeShape detail takes priority when set
  if (selectedTypeShapeId) {
    return <TypeShapePanel shapeId={selectedTypeShapeId} />;
  }

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
