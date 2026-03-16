import { useCallback, useRef, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import GraphCanvas from "./GraphCanvas";
import CodeEditor from "./CodeEditor";
import TerminalChat from "./TerminalChat";
import TabBar from "./TabBar";
import Breadcrumbs from "./Breadcrumbs";
import { useLayoutStore } from "@/store/layoutStore";

function ResizeHandle({
  onDrag,
}: {
  onDrag: (deltaX: number) => void;
}) {
  const dragging = useRef(false);
  const lastX = useRef(0);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      lastX.current = e.clientX;

      const handleMouseMove = (ev: MouseEvent) => {
        if (!dragging.current) return;
        const delta = ev.clientX - lastX.current;
        lastX.current = ev.clientX;
        onDrag(delta);
      };

      const handleMouseUp = () => {
        dragging.current = false;
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [onDrag],
  );

  return (
    <div
      className="w-1 cursor-col-resize flex-shrink-0 hover:bg-[var(--border-focus)]"
      style={{ background: "var(--border)" }}
      onMouseDown={handleMouseDown}
    />
  );
}

function Layout() {
  const graphWidth = useLayoutStore((s) => s.graphPanelWidth);
  const editorWidth = useLayoutStore((s) => s.editorPanelWidth);
  const setPanelWidth = useLayoutStore((s) => s.setPanelWidth);
  const collapsedPanels = useLayoutStore((s) => s.collapsedPanels);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  const measureContainer = useCallback((el: HTMLDivElement | null) => {
    if (el) {
      containerRef.current = el;
      setContainerWidth(el.clientWidth);
      const observer = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry) {
          setContainerWidth(entry.contentRect.width);
        }
      });
      observer.observe(el);
    }
  }, []);

  const handleLeftResize = useCallback(
    (deltaX: number) => {
      if (containerWidth === 0) return;
      const pctDelta = (deltaX / containerWidth) * 100;
      const newGraph = Math.max(15, Math.min(60, graphWidth + pctDelta));
      const newEditor = Math.max(15, editorWidth - pctDelta);
      setPanelWidth("graph", newGraph);
      setPanelWidth("editor", newEditor);
    },
    [containerWidth, graphWidth, editorWidth, setPanelWidth],
  );

  const handleRightResize = useCallback(
    (deltaX: number) => {
      if (containerWidth === 0) return;
      const pctDelta = (deltaX / containerWidth) * 100;
      const termWidth = 100 - graphWidth - editorWidth;
      const newEditor = Math.max(15, Math.min(60, editorWidth + pctDelta));
      const newTerm = Math.max(15, termWidth - pctDelta);
      setPanelWidth("editor", newEditor);
      setPanelWidth("terminal", newTerm);
    },
    [containerWidth, graphWidth, editorWidth, setPanelWidth],
  );

  const graphCollapsed = collapsedPanels.has("graph");
  const editorCollapsed = collapsedPanels.has("editor");
  const terminalCollapsed = collapsedPanels.has("terminal");

  const effectiveGraph = graphCollapsed ? 0 : graphWidth;
  const effectiveEditor = editorCollapsed ? 0 : editorWidth;
  const effectiveTerm = terminalCollapsed
    ? 0
    : 100 - effectiveGraph - effectiveEditor;

  return (
    <div
      ref={measureContainer}
      className="flex h-screen w-screen overflow-hidden"
      style={{ background: "var(--bg-primary)" }}
    >
      {!graphCollapsed && (
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: `${effectiveGraph}%` }}
        >
          <Breadcrumbs />
          <div className="flex-1 overflow-hidden">
            <ReactFlowProvider>
              <GraphCanvas />
            </ReactFlowProvider>
          </div>
        </div>
      )}

      {!graphCollapsed && !editorCollapsed && (
        <ResizeHandle onDrag={handleLeftResize} />
      )}

      {!editorCollapsed && (
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: `${effectiveEditor}%` }}
        >
          <TabBar />
          <div className="flex-1 overflow-hidden">
            <CodeEditor />
          </div>
        </div>
      )}

      {!editorCollapsed && !terminalCollapsed && (
        <ResizeHandle onDrag={handleRightResize} />
      )}

      {!terminalCollapsed && (
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: `${effectiveTerm}%` }}
        >
          <TerminalChat />
        </div>
      )}
    </div>
  );
}

export default Layout;
