import { ArrowLeft, X } from "lucide-react";
import { useEditorStore } from "@/store/editorStore";

function TabBar() {
  const activeNodeView = useEditorStore((s) => s.activeNodeView);
  const nodeViewHistory = useEditorStore((s) => s.nodeViewHistory);
  const goBackNode = useEditorStore((s) => s.goBackNode);
  const clearNodeView = useEditorStore((s) => s.clearNodeView);

  if (!activeNodeView) {
    return (
      <div
        className="h-8 border-b"
        style={{
          background: "var(--bg-secondary)",
          borderColor: "var(--border)",
        }}
      />
    );
  }

  return (
    <div
      className="h-8 flex items-center overflow-x-auto border-b"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border)",
      }}
    >
      {nodeViewHistory.length > 0 && (
        <button
          onClick={goBackNode}
          className="flex items-center px-2 h-full"
          style={{
            background: "none",
            border: "none",
            borderRight: "1px solid var(--border)",
            cursor: "pointer",
            color: "var(--text-secondary)",
          }}
          title="Go back"
        >
          <ArrowLeft size={14} />
        </button>
      )}
      {/* History breadcrumb */}
      {nodeViewHistory.map((view, i) => (
        <button
          key={`${view.nodeId}-${i}`}
          onClick={() => {
            // Navigate back to this point in history
            const store = useEditorStore.getState();
            const stepsBack = nodeViewHistory.length - i;
            for (let s = 0; s < stepsBack; s++) {
              store.goBackNode();
            }
          }}
          className="flex items-center px-3 h-full text-xs font-mono border-r"
          style={{
            background: "var(--bg-secondary)",
            borderColor: "var(--border)",
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          {view.name}
        </button>
      ))}
      {/* Active node tab */}
      <div
        className="flex items-center gap-1 px-3 h-full text-xs font-mono border-r"
        style={{
          background: "var(--bg-primary)",
          borderColor: "var(--border)",
          color: "var(--text-primary)",
          borderBottom: "1px solid var(--bg-primary)",
        }}
      >
        <span
          className="text-[10px] uppercase mr-1"
          style={{ color: "var(--text-muted)" }}
        >
          {activeNodeView.kind}
        </span>
        <span>{activeNodeView.name}</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            clearNodeView();
          }}
          className="ml-1 opacity-50 hover:opacity-100"
          style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

export default TabBar;
