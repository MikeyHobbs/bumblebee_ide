import { ChevronRight } from "lucide-react";
import { useGraphStore } from "@/store/graphStore";

function Breadcrumbs() {
  const breadcrumb = useGraphStore((s) => s.breadcrumb);
  const navigateBack = useGraphStore((s) => s.navigateBack);
  const goHome = useGraphStore((s) => s.goHome);

  if (breadcrumb.length <= 1) {
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
      {breadcrumb.map((entry, i) => (
        <span key={i} className="flex items-center gap-1 flex-shrink-0">
          {i > 0 && (
            <ChevronRight size={10} style={{ color: "var(--text-muted)" }} />
          )}
          {i < breadcrumb.length - 1 ? (
            <button
              onClick={() => {
                if (i === 0) {
                  goHome();
                } else {
                  navigateBack(i);
                }
              }}
              className="hover:underline"
              style={{ color: "var(--text-secondary)", cursor: "pointer", background: "none", border: "none" }}
            >
              {entry.label}
            </button>
          ) : (
            <span style={{ color: "var(--text-primary)" }}>
              {entry.label}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

export default Breadcrumbs;
