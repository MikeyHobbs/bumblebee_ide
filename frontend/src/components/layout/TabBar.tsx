import { Plus, X } from "lucide-react";
import { useEditorStore } from "@/store/editorStore";
import type { EditorTab } from "@/store/editorStore";

function TabBar() {
  const tabs = useEditorStore((s) => s.tabs);
  const activeTabId = useEditorStore((s) => s.activeTabId);
  const setActiveTab = useEditorStore((s) => s.setActiveTab);
  const closeTab = useEditorStore((s) => s.closeTab);
  const openTab = useEditorStore((s) => s.openTab);

  const handleNewTab = () => {
    const id = crypto.randomUUID();
    const tab: EditorTab = {
      id,
      label: "Untitled",
      nodeId: null,
      modulePath: `__compose__.${id}`,
      content: "",
      language: "python",
      sourceNodeIds: [],
      flowId: null,
      gaps: null,
      isDirty: false,
    };
    openTab(tab);
  };

  return (
    <div
      className="h-8 flex items-center overflow-x-auto border-b"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId;
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="flex items-center gap-1 px-3 h-full text-xs font-mono border-r shrink-0"
            style={{
              background: isActive ? "var(--bg-primary)" : "var(--bg-secondary)",
              borderColor: "var(--border)",
              borderBottom: isActive ? "1px solid var(--bg-primary)" : "none",
              color: isActive ? "var(--text-primary)" : "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            {tab.isDirty && (
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: "#f59e0b" }}
              />
            )}
            <span>{tab.nodeId ? tab.label : tab.label || "Untitled"}</span>
            <span
              onClick={(e) => {
                e.stopPropagation();
                closeTab(tab.id);
              }}
              className="ml-1 opacity-50 hover:opacity-100"
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
            >
              <X size={12} />
            </span>
          </button>
        );
      })}
      <button
        onClick={handleNewTab}
        className="flex items-center justify-center w-8 h-full shrink-0"
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--text-muted)",
        }}
        title="New compose tab"
      >
        <Plus size={14} />
      </button>
    </div>
  );
}

export default TabBar;
