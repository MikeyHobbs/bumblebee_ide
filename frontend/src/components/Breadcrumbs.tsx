import { ChevronRight } from "lucide-react";
import { useNavigationStore } from "@/store/navigationStore";
import { useGraphStore } from "@/store/graphStore";

function Breadcrumbs() {
  const stack = useNavigationStore((s) => s.navigationStack);
  const popNavigation = useNavigationStore((s) => s.popNavigation);
  const clearNavigation = useNavigationStore((s) => s.clearNavigation);
  const selectNode = useGraphStore((s) => s.selectNode);

  if (stack.length === 0) {
    return (
      <div
        className="h-7 flex items-center px-2 text-xs border-b"
        style={{
          background: "var(--bg-secondary)",
          borderColor: "var(--border)",
          color: "var(--text-muted)",
        }}
      >
        Graph
      </div>
    );
  }

  return (
    <div
      className="h-7 flex items-center px-2 text-xs border-b gap-1 overflow-x-auto"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border)",
        color: "var(--text-secondary)",
      }}
    >
      <button
        onClick={() => {
          clearNavigation();
          selectNode(null);
        }}
        className="hover:underline flex-shrink-0"
        style={{ color: "var(--text-secondary)", cursor: "pointer", background: "none", border: "none" }}
      >
        Graph
      </button>
      {stack.map((nodeId, idx) => (
        <span key={`${nodeId}-${idx}`} className="flex items-center gap-1 flex-shrink-0">
          <ChevronRight size={10} style={{ color: "var(--text-muted)" }} />
          <button
            onClick={() => {
              // Pop back to this item
              const popCount = stack.length - idx - 1;
              for (let i = 0; i < popCount; i++) {
                popNavigation();
              }
              selectNode(nodeId);
            }}
            className="hover:underline"
            style={{
              color: idx === stack.length - 1 ? "var(--text-primary)" : "var(--text-secondary)",
              cursor: "pointer",
              background: "none",
              border: "none",
            }}
          >
            {nodeId}
          </button>
        </span>
      ))}
    </div>
  );
}

export default Breadcrumbs;
