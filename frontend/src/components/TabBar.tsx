import { X, Pin } from "lucide-react";
import { useEditorStore } from "@/store/editorStore";

function TabBar() {
  const openFiles = useEditorStore((s) => s.openFiles);
  const activeFile = useEditorStore((s) => s.activeFile);
  const pinnedFiles = useEditorStore((s) => s.pinnedFiles);
  const setActiveFile = useEditorStore((s) => s.setActiveFile);
  const closeFile = useEditorStore((s) => s.closeFile);
  const pinFile = useEditorStore((s) => s.pinFile);

  if (openFiles.length === 0) {
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
      className="h-8 flex items-stretch overflow-x-auto border-b"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border)",
      }}
    >
      {openFiles.map((filePath) => {
        const isActive = filePath === activeFile;
        const isPinned = pinnedFiles.has(filePath);
        const fileName = filePath.split("/").pop() ?? filePath;

        return (
          <div
            key={filePath}
            className="flex items-center gap-1 px-3 text-xs font-mono border-r cursor-pointer"
            style={{
              background: isActive
                ? "var(--bg-primary)"
                : "var(--bg-secondary)",
              borderColor: "var(--border)",
              color: isActive
                ? "var(--text-primary)"
                : "var(--text-secondary)",
              borderBottom: isActive
                ? "1px solid var(--bg-primary)"
                : "none",
            }}
            onClick={() => setActiveFile(filePath)}
          >
            {isPinned && (
              <Pin
                size={10}
                style={{ color: "var(--node-variable)" }}
              />
            )}
            <span>{fileName}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeFile(filePath);
              }}
              className="ml-1 opacity-50 hover:opacity-100"
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
            >
              <X size={12} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                pinFile(filePath);
              }}
              className="opacity-30 hover:opacity-100"
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
              title={isPinned ? "Unpin" : "Pin"}
            >
              <Pin size={10} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default TabBar;
