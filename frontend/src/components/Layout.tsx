import { useCallback, useRef, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import GraphCanvas from "./GraphCanvas";
import CodeEditor from "./CodeEditor";
import TerminalChat from "./TerminalChat";
import TabBar from "./TabBar";
import Breadcrumbs from "./Breadcrumbs";
import { useLayoutStore } from "@/store/layoutStore";

function HResizeHandle({
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

function VResizeHandle({
  onDrag,
}: {
  onDrag: (deltaY: number) => void;
}) {
  const dragging = useRef(false);
  const lastY = useRef(0);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      lastY.current = e.clientY;

      const handleMouseMove = (ev: MouseEvent) => {
        if (!dragging.current) return;
        const delta = ev.clientY - lastY.current;
        lastY.current = ev.clientY;
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
      className="h-1 cursor-row-resize flex-shrink-0 hover:bg-[var(--border-focus)]"
      style={{ background: "var(--border)" }}
      onMouseDown={handleMouseDown}
    />
  );
}

function Layout() {
  const graphWidth = useLayoutStore((s) => s.graphPanelWidth);
  const topRowHeight = useLayoutStore((s) => s.topRowHeight);
  const setPanelWidth = useLayoutStore((s) => s.setPanelWidth);
  const setTopRowHeight = useLayoutStore((s) => s.setTopRowHeight);
  const collapsedPanels = useLayoutStore((s) => s.collapsedPanels);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [containerHeight, setContainerHeight] = useState(0);

  const measureContainer = useCallback((el: HTMLDivElement | null) => {
    if (el) {
      containerRef.current = el;
      setContainerWidth(el.clientWidth);
      setContainerHeight(el.clientHeight);
      const observer = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry) {
          setContainerWidth(entry.contentRect.width);
          setContainerHeight(entry.contentRect.height);
        }
      });
      observer.observe(el);
    }
  }, []);

  const handleHResize = useCallback(
    (deltaX: number) => {
      if (containerWidth === 0) return;
      const pctDelta = (deltaX / containerWidth) * 100;
      const newGraph = Math.max(20, Math.min(80, graphWidth + pctDelta));
      setPanelWidth("graph", newGraph);
    },
    [containerWidth, graphWidth, setPanelWidth],
  );

  const handleVResize = useCallback(
    (deltaY: number) => {
      if (containerHeight === 0) return;
      const pctDelta = (deltaY / containerHeight) * 100;
      const newTop = Math.max(20, Math.min(85, topRowHeight + pctDelta));
      setTopRowHeight(newTop);
    },
    [containerHeight, topRowHeight, setTopRowHeight],
  );

  const graphCollapsed = collapsedPanels.has("graph");
  const editorCollapsed = collapsedPanels.has("editor");
  const terminalCollapsed = collapsedPanels.has("terminal");

  const effectiveGraph = graphCollapsed ? 0 : graphWidth;
  const effectiveEditor = editorCollapsed ? 0 : 100 - effectiveGraph;
  const effectiveTopHeight = terminalCollapsed ? 100 : topRowHeight;

  return (
    <div
      ref={measureContainer}
      className="flex flex-col h-screen w-screen overflow-hidden"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Top row: Graph + Editor side-by-side */}
      <div
        className="flex overflow-hidden flex-shrink-0"
        style={{ height: `${effectiveTopHeight}%` }}
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
          <HResizeHandle onDrag={handleHResize} />
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
      </div>

      {/* Vertical resize handle */}
      {!terminalCollapsed && <VResizeHandle onDrag={handleVResize} />}

      {/* Bottom row: Terminal full-width */}
      {!terminalCollapsed && (
        <div className="flex-1 overflow-hidden min-h-0">
          <TerminalChat />
        </div>
      )}
    </div>
  );
}

export default Layout;
