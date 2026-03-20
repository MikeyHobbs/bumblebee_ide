import { useEffect } from "react";
import type Graph from "graphology";
import type Sigma from "sigma";
import { useEditorStore, isNodeInVfsSession } from "@/store/editorStore";
import { useGraphStore } from "@/store/graphStore";
import { apiFetch } from "@/api/client";
import { getSigmaZoomTier, labelThresholdForTier } from "@/graph/layout/semanticZoom";
import { buildCallInsertion } from "@/editor/completionService";
import { localName } from "./useGraphSync";

interface CallbacksRef {
  navigateToNode: (id: string, label: string) => void;
  goHome: () => void;
  expandNode: (id: string) => void;
  collapseExpanded: () => void;
  openNodeView: (params: { nodeId: string; name: string; kind: string; sourceText: string; modulePath: string }) => void;
  traceVariable: (id: string) => void;
  clearTrace: () => void;
  showConsumers: (id: string) => void;
  expandHighlight: (nodeId: string, neighbors: string[]) => void;
}

/**
 * Register all Sigma event listeners: hover, click, double-click, drag-and-drop, semantic zoom.
 */
export function useGraphInteractions(
  sigma: Sigma | null,
  container: HTMLDivElement | null,
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  focusRef: React.MutableRefObject<{ focusedNodeId: string | null; expandedNodeId: string | null }>,
  hoveredNode: React.MutableRefObject<string | null>,
  wasDragged: React.MutableRefObject<boolean>,
  isDragging: React.MutableRefObject<boolean>,
  draggedNode: React.MutableRefObject<string | null>,
  callbacksRef: React.MutableRefObject<CallbacksRef>,
  highlightRef: React.MutableRefObject<Set<string>>,
  traceRef: React.MutableRefObject<Set<string>>,
) {
  useEffect(() => {
    if (!sigma || !container) return;

    // Hover events — debounce refresh via rAF to avoid 60+ refreshes/sec
    let hoverRafId = 0;
    const scheduleRefresh = () => {
      cancelAnimationFrame(hoverRafId);
      hoverRafId = requestAnimationFrame(() => sigma.refresh());
    };

    sigma.on("enterNode", ({ node }) => {
      hoveredNode.current = node;
      scheduleRefresh();
      container.style.cursor = "pointer";
    });

    sigma.on("leaveNode", () => {
      hoveredNode.current = null;
      scheduleRefresh();
      container.style.cursor = "default";
    });

    // Single click: focus on node (skip if we were dragging)
    // Cmd+click: expand highlights with neighbors
    sigma.on("clickNode", ({ node, event }) => {
      if (wasDragged.current) {
        wasDragged.current = false;
        return;
      }

      // Graph autocomplete mode: click a highlighted suggestion node to insert its call
      const edState = useEditorStore.getState();
      if (edState.graphAutoComplete && edState.pendingSuggestions.length > 0) {
        const suggestion = edState.pendingSuggestions.find((s) => s.node_id === node);
        if (suggestion) {
          const varName = edState.suggestionContext?.variableName ?? "";
          const insertion = buildCallInsertion(suggestion, varName);
          // Dispatch a custom event that CodeEditor listens to for insertion
          window.dispatchEvent(new CustomEvent("bumblebee:insert-suggestion", {
            detail: { text: insertion, nodeId: node },
          }));
          edState.clearPendingSuggestions();
          return;
        }
      }

      // Graph AC mode (no pending suggestions): click to toggle node in/out of VFS session
      if (edState.graphAutoComplete) {
        const graph = graphRef.current;
        const attrs = graph?.getNodeAttributes(node);
        if (attrs?.isVariable) return; // skip variables

        if (isNodeInVfsSession(node)) {
          // Deselect — remove from VFS session
          edState.removeNodeFromVfsSession(node);
        } else {
          // Add to VFS session — fetch source_text then add
          const nodeName = typeof attrs?.name === "string" ? attrs.name : node;
          const modulePath = typeof attrs?.modulePath === "string" ? attrs.modulePath : "";
          void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
            .then((full) => {
              useEditorStore.getState().addNodeToVfsSession(
                node,
                localName(nodeName),
                full.source_text ?? "",
                modulePath,
              );
            })
            .catch((err) => console.warn(`Failed to fetch node ${node} for VFS session:`, err));
        }
        return;
      }

      const graph = graphRef.current;
      const attrs = graph?.getNodeAttributes(node);
      if (!attrs || attrs.isVariable) return;

      // TypeShape nodes: project to VFS and open in editor
      if (attrs.isTypeShape) {
        const shapeId = node.startsWith("ts:") ? node.slice(3) : node;
        const label = typeof attrs.label === "string" ? attrs.label : "TypeShape";
        void apiFetch<{ source: string; file_path: string }>(`/api/v1/vfs/type-shape/${shapeId}?project=true`)
          .then((res) => {
            callbacksRef.current.openNodeView({
              nodeId: `ts:${shapeId}`,
              name: label,
              kind: "type_shape",
              sourceText: res.source,
              modulePath: `__typeshapes__.${label}`,
            });
          })
          .catch((err) => console.warn(`Failed to project TypeShape ${shapeId}:`, err));
        return;
      }

      const nodeName = typeof attrs.name === "string" ? attrs.name : node;
      const kind = typeof attrs.kind === "string" ? attrs.kind : "";
      const modulePath = typeof attrs.modulePath === "string" ? attrs.modulePath : "";
      const isMeta = event.original.metaKey || event.original.ctrlKey;

      if (isMeta && graph) {
        // Cmd+click: expand highlight set with this node + its neighbors
        const neighbors = graph.neighbors(node).filter((n) => {
          const na = graph.getNodeAttributes(n);
          return !na.isVariable;
        });
        callbacksRef.current.expandHighlight(node, neighbors);

        // Also fetch + open in editor
        void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
          .then((full) => {
            callbacksRef.current.openNodeView({
              nodeId: node,
              name: localName(nodeName),
              kind,
              sourceText: full.source_text,
              modulePath,
            });
          })
          .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
        return;
      }

      // Plain click with active highlights: focus within set, pan to node
      if (highlightRef.current.size > 0) {
        focusRef.current = { ...focusRef.current, focusedNodeId: node };
        useGraphStore.setState({ focusedNodeId: node, selectedNodeId: null });
        // Pan to center on node without changing zoom
        const nodeVp = sigma.graphToViewport({ x: attrs.x as number, y: attrs.y as number });
        const fc = sigma.viewportToFramedGraph(nodeVp);
        sigma.getCamera().animate({ x: fc.x, y: fc.y }, { duration: 300 });
        sigma.refresh();

        void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
          .then((full) => {
            callbacksRef.current.openNodeView({
              nodeId: node,
              name: localName(nodeName),
              kind,
              sourceText: full.source_text,
              modulePath,
            });
          })
          .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
        return;
      }

      // Plain click, no highlights: navigate (existing behavior)
      callbacksRef.current.navigateToNode(node, localName(nodeName));

      // Fetch source_text on demand — overview payload omits it for performance
      void apiFetch<{ source_text: string }>(`/api/v1/nodes/${node}`)
        .then((full) => {
          callbacksRef.current.openNodeView({
            nodeId: node,
            name: localName(nodeName),
            kind,
            sourceText: full.source_text,
            modulePath,
          });
        })
        .catch((err) => console.warn(`Failed to fetch node ${node}:`, err));
    });

    // Double click: expand or trace
    sigma.on("doubleClickNode", ({ node, preventSigmaDefault }) => {
      preventSigmaDefault();
      const attrs = graphRef.current?.getNodeAttributes(node);

      if (attrs?.isVariable) {
        callbacksRef.current.showConsumers(node);
        return;
      }

      callbacksRef.current.expandNode(node);
    });

    sigma.on("doubleClickStage", ({ preventSigmaDefault }) => {
      preventSigmaDefault();
      if (focusRef.current.focusedNodeId || traceRef.current.size > 0 || highlightRef.current.size > 0) {
        callbacksRef.current.clearTrace();
        callbacksRef.current.collapseExpanded();
        callbacksRef.current.goHome();
        sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 500 });
      }
    });

    // Node drag-and-drop
    sigma.on("downNode", ({ node, event }) => {
      isDragging.current = true;
      draggedNode.current = node;
      sigma.getCamera().disable();
      event.original.preventDefault();
      event.original.stopPropagation();
    });

    sigma.getMouseCaptor().on("mousemovebody", (event) => {
      if (!isDragging.current || !draggedNode.current) return;
      wasDragged.current = true;
      const graph = graphRef.current;
      if (!graph) return;

      const pos = sigma.viewportToGraph(event);
      graph.setNodeAttribute(draggedNode.current, "x", pos.x);
      graph.setNodeAttribute(draggedNode.current, "y", pos.y);
    });

    sigma.getMouseCaptor().on("mouseup", () => {
      if (isDragging.current) {
        isDragging.current = false;
        draggedNode.current = null;
        sigma.getCamera().enable();
      }
    });

    // Semantic zoom: adjust label threshold
    // Guard against calling setSetting on a killed Sigma instance
    // (camera animations can outlive the Sigma lifecycle)
    sigma.getCamera().on("updated", () => {
      if (sigmaRef.current !== sigma) return;
      const ratio = sigma.getCamera().ratio;
      const tier = getSigmaZoomTier(ratio);
      const threshold = labelThresholdForTier(tier);
      sigma.setSetting("labelRenderedSizeThreshold", threshold);
    });
  }, [sigma, container, graphRef, sigmaRef, focusRef, hoveredNode, wasDragged, isDragging, draggedNode, callbacksRef, highlightRef, traceRef]);
}
