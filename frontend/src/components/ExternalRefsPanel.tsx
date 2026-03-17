import { useNodeEdges, useLogicNodes, type LogicNodeResponse } from "@/api/client";
import { useEditorStore, type NodeView } from "@/store/editorStore";

interface ExternalRefsPanelProps {
  nodeId: string;
}

function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

/** Group edges by type and resolve target/source node data for clickable navigation. */
function ExternalRefsPanel({ nodeId }: ExternalRefsPanelProps) {
  const { data: outEdges } = useNodeEdges(nodeId, "outgoing");
  const { data: inEdges } = useNodeEdges(nodeId, "incoming");
  const { data: allNodes } = useLogicNodes(undefined, undefined, 500);
  const openNodeView = useEditorStore((s) => s.openNodeView);

  if (!outEdges && !inEdges) return null;

  const nodeMap = new Map<string, LogicNodeResponse>();
  if (allNodes) {
    for (const n of allNodes) {
      nodeMap.set(n.id, n);
    }
  }

  // Group outgoing edges by type
  const outgoing = new Map<string, string[]>();
  for (const e of outEdges ?? []) {
    const list = outgoing.get(e.type) ?? [];
    list.push(e.target);
    outgoing.set(e.type, list);
  }

  // Group incoming edges by type (show as "CALLED_BY", "INHERITED_BY", etc.)
  const incoming = new Map<string, string[]>();
  for (const e of inEdges ?? []) {
    const list = incoming.get(e.type) ?? [];
    list.push(e.source);
    incoming.set(e.type, list);
  }

  const hasRefs = outgoing.size > 0 || incoming.size > 0;
  if (!hasRefs) return null;

  function handleClick(targetNodeId: string) {
    const node = nodeMap.get(targetNodeId);
    if (!node) return;
    const view: NodeView = {
      nodeId: node.id,
      name: localName(node.name),
      kind: node.kind,
      sourceText: node.source_text,
      modulePath: node.module_path,
    };
    openNodeView(view);
  }

  function renderGroup(label: string, type: string, nodeIds: string[]) {
    const unique = [...new Set(nodeIds)];
    return (
      <div key={`${label}-${type}`} className="flex items-start gap-2 text-xs">
        <span
          className="shrink-0 font-mono uppercase"
          style={{ color: "var(--text-muted)", minWidth: 100 }}
        >
          {label}
        </span>
        <div className="flex flex-wrap gap-1">
          {unique.map((id) => {
            const node = nodeMap.get(id);
            const name = node ? localName(node.name) : id.split(":").pop() ?? id;
            return (
              <button
                key={id}
                onClick={() => handleClick(id)}
                className="px-1.5 py-0.5 font-mono hover:underline"
                style={{
                  color: "var(--node-function)",
                  background: "var(--bg-tertiary)",
                  border: "none",
                  cursor: node ? "pointer" : "default",
                  opacity: node ? 1 : 0.5,
                }}
              >
                {name}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      className="border-t px-3 py-2 space-y-1 overflow-y-auto"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border)",
        maxHeight: 160,
      }}
    >
      <div
        className="text-xs font-mono mb-1"
        style={{ color: "var(--text-secondary)" }}
      >
        References
      </div>
      {[...outgoing.entries()].map(([type, ids]) =>
        renderGroup(type, type, ids),
      )}
      {[...incoming.entries()].map(([type, ids]) =>
        renderGroup(`${type} (in)`, type, ids),
      )}
    </div>
  );
}

export default ExternalRefsPanel;
