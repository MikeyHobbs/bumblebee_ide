import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  MarkerType,
  useViewport,
  useReactFlow,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "@/graph/nodes";
import { edgeTypes } from "@/graph/edges";
import { computeForceLayout } from "@/graph/layout/forceLayout";
import { computeDagreLayout } from "@/graph/layout/dagreLayout";
import { computeControlFlowLayout } from "@/graph/layout/controlFlowLayout";
import { detectDuplicateBranches } from "@/graph/duplicateDetection";
import { useGraphStore } from "@/store/graphStore";
import { useEditorStore } from "@/store/editorStore";
import {
  useModuleGraph,
  useFileMembers,
  useClassDetail,
  useFunctionDetail,
  useFunctionControlFlow,
  useVariableDetail,
} from "@/api/client";
import type { GraphNode, GraphEdge } from "@/types/graph";


function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

function controlFlowLabel(gn: GraphNode): string {
  const kind = typeof gn.properties["kind"] === "string" ? gn.properties["kind"] : "";
  const condText = typeof gn.properties["condition_text"] === "string" ? gn.properties["condition_text"] : "";
  const sourceText = typeof gn.properties["source_text"] === "string" ? gn.properties["source_text"] : "";

  if (gn.label === "Statement") {
    const text = sourceText || gn.id;
    return text.length > 60 ? text.slice(0, 57) + "..." : text;
  }
  if (gn.label === "ControlFlow") {
    const parts = [kind, condText].filter(Boolean);
    return parts.join(" ") || gn.id;
  }
  if (gn.label === "Branch") {
    if (condText) return `${kind} ${condText}`.trim();
    return kind || gn.id;
  }
  return localName(typeof gn.properties["name"] === "string" ? gn.properties["name"] : gn.id);
}

function toFlowNodes(graphNodes: GraphNode[], useControlFlowLabels = false): Node[] {
  return graphNodes.map((gn) => {
    const fullName = typeof gn.properties["name"] === "string" ? gn.properties["name"] : gn.id;
    const isFlowType = gn.label === "Statement" || gn.label === "ControlFlow" || gn.label === "Branch";
    const label = useControlFlowLabels && isFlowType
      ? controlFlowLabel(gn)
      : localName(fullName);
    return {
      id: gn.id,
      type: gn.label,
      position: { x: 0, y: 0 },
      data: {
        label,
        ...gn.properties,
      },
    };
  });
}

function toFlowEdges(graphEdges: GraphEdge[]): Edge[] {
  return graphEdges.map((ge, idx) => ({
    id: `${ge.source}-${ge.type}-${ge.target}-${idx}`,
    source: ge.source,
    target: ge.target,
    type: ge.type,
    data: ge.properties,
    ...(ge.type === "NEXT"
      ? { markerEnd: { type: MarkerType.ArrowClosed, color: "var(--text-muted)" } }
      : {}),
  }));
}

function computeNestingDepth(nodes: Node[], edges: Edge[]): Map<string, number> {
  const depthMap = new Map<string, number>();
  const containsChildren = new Map<string, string[]>();
  const containsTargets = new Set<string>();

  for (const e of edges) {
    if (e.type === "CONTAINS") {
      const children = containsChildren.get(e.source) ?? [];
      children.push(e.target);
      containsChildren.set(e.source, children);
      containsTargets.add(e.target);
    }
  }

  const nodeIds = new Set(nodes.map((n) => n.id));
  const roots: string[] = [];
  for (const id of nodeIds) {
    if (containsChildren.has(id) && !containsTargets.has(id)) {
      roots.push(id);
    }
  }

  const queue: Array<{ id: string; depth: number }> = roots.map((id) => ({ id, depth: 0 }));
  while (queue.length > 0) {
    const { id, depth } = queue.shift()!;
    if (depthMap.has(id)) continue;
    depthMap.set(id, depth);
    const children = containsChildren.get(id) ?? [];
    for (const childId of children) {
      if (!depthMap.has(childId)) {
        queue.push({ id: childId, depth: depth + 1 });
      }
    }
  }

  return depthMap;
}

function injectTerminalMarkers(
  nodes: Node[],
  edges: Edge[],
): { nodes: Node[]; edges: Edge[] } {
  if (nodes.length === 0) return { nodes, edges };

  const containsSources = new Set<string>();
  const containsTargets = new Set<string>();
  const containsFirstChild = new Map<string, string>();

  for (const e of edges) {
    if (e.type === "CONTAINS") {
      containsSources.add(e.source);
      containsTargets.add(e.target);
      if (!containsFirstChild.has(e.source)) {
        containsFirstChild.set(e.source, e.target);
      }
    }
  }

  let rootId: string | null = null;
  for (const id of containsSources) {
    if (!containsTargets.has(id)) {
      rootId = id;
      break;
    }
  }

  if (!rootId) return { nodes, edges };

  const firstChildId = containsFirstChild.get(rootId);
  if (!firstChildId) return { nodes, edges };

  const hasOutgoingNext = new Set<string>();
  for (const e of edges) {
    if (e.type === "NEXT") {
      hasOutgoingNext.add(e.source);
    }
  }

  const flowNodeIds = new Set(
    nodes
      .filter((n) =>
        n.type === "Statement" || n.type === "ControlFlow" || n.type === "Branch",
      )
      .map((n) => n.id),
  );

  const terminalIds: string[] = [];
  for (const id of flowNodeIds) {
    if (!hasOutgoingNext.has(id)) {
      terminalIds.push(id);
    }
  }

  const startNode: Node = {
    id: "__start__",
    type: "Terminal",
    position: { x: 0, y: 0 },
    data: { label: "START", terminalKind: "start" },
  };

  const endNode: Node = {
    id: "__end__",
    type: "Terminal",
    position: { x: 0, y: 0 },
    data: { label: "END", terminalKind: "end" },
  };

  const newEdges: Edge[] = [
    {
      id: "__start__-NEXT-" + firstChildId,
      source: "__start__",
      target: firstChildId,
      type: "NEXT",
    },
    ...terminalIds.map((tid) => ({
      id: tid + "-NEXT-__end__",
      source: tid,
      target: "__end__",
      type: "NEXT",
    })),
  ];

  return {
    nodes: [startNode, ...nodes, endNode],
    edges: [...edges, ...newEdges],
  };
}

function buildFileTree(
  moduleNodes: GraphNode[],
  moduleEdges: GraphEdge[],
): { nodes: Node[]; edges: Edge[] } {
  const folderSet = new Set<string>();
  const fileNodes: Node[] = [];

  for (const mod of moduleNodes) {
    const filePath = typeof mod.properties["module_path"] === "string"
      ? mod.properties["module_path"]
      : "";
    const parts = filePath.split("/");
    const fileName = parts[parts.length - 1] || mod.id;

    for (let i = 1; i < parts.length; i++) {
      folderSet.add(parts.slice(0, i).join("/"));
    }

    fileNodes.push({
      id: mod.id,
      type: "Module",
      position: { x: 0, y: 0 },
      data: {
        label: String(fileName),
        name: typeof mod.properties["name"] === "string" ? mod.properties["name"] : mod.id,
        module_path: filePath,
        ...mod.properties,
      },
    });
  }

  const folderNodes: Node[] = [];
  for (const folderPath of folderSet) {
    const parts = folderPath.split("/");
    folderNodes.push({
      id: `folder:${folderPath}`,
      type: "Folder",
      position: { x: 0, y: 0 },
      data: { label: parts[parts.length - 1] },
    });
  }

  const containEdges: Edge[] = [];
  let edgeIdx = 0;

  for (const folderPath of folderSet) {
    const parts = folderPath.split("/");
    if (parts.length > 1) {
      const parentPath = parts.slice(0, -1).join("/");
      if (folderSet.has(parentPath)) {
        containEdges.push({
          id: `contain-${edgeIdx++}`,
          source: `folder:${parentPath}`,
          target: `folder:${folderPath}`,
          type: "CONTAINS",
        });
      }
    }
  }

  for (const mod of moduleNodes) {
    const filePath = typeof mod.properties["module_path"] === "string"
      ? mod.properties["module_path"]
      : "";
    const parts = filePath.split("/");
    if (parts.length > 1) {
      const parentPath = parts.slice(0, -1).join("/");
      if (folderSet.has(parentPath)) {
        containEdges.push({
          id: `contain-${edgeIdx++}`,
          source: `folder:${parentPath}`,
          target: mod.id,
          type: "CONTAINS",
        });
      }
    }
  }

  const importEdges: Edge[] = moduleEdges.map((ge, idx) => ({
    id: `${ge.source}-${ge.type}-${ge.target}-${idx}`,
    source: ge.source,
    target: ge.target,
    type: ge.type,
    data: ge.properties,
  }));

  return {
    nodes: [...folderNodes, ...fileNodes],
    edges: [...containEdges, ...importEdges],
  };
}

function Breadcrumb() {
  const breadcrumb = useGraphStore((s) => s.breadcrumb);
  const navigateTo = useGraphStore((s) => s.navigateTo);

  if (breadcrumb.length <= 1) return null;

  return (
    <div
      className="absolute top-3 left-3 z-10 flex items-center gap-1 px-2 py-1 text-xs font-mono"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border)",
      }}
    >
      {breadcrumb.map((entry, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && (
            <span style={{ color: "var(--text-muted)" }}>/</span>
          )}
          {i < breadcrumb.length - 1 ? (
            <button
              onClick={() => navigateTo(i)}
              className="cursor-pointer hover:underline"
              style={{ color: "var(--node-module)" }}
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

/** Fetch usages for a node and expand them inline in the graph. */
async function fetchUsages(nodeName: string): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] } | null> {
  try {
    const res = await fetch(`/api/v1/graph/usages/${encodeURIComponent(nodeName)}?direction=in`);
    if (!res.ok) return null;
    const data = (await res.json()) as { nodes: GraphNode[]; edges: GraphEdge[] };
    return data.nodes.length > 0 ? data : null;
  } catch {
    return null;
  }
}

function GraphCanvasInner() {
  const { zoom } = useViewport();
  const { fitView } = useReactFlow();
  const setZoomLevel = useGraphStore((s) => s.setZoomLevel);
  const selectNode = useGraphStore((s) => s.selectNode);
  const isIndexing = useGraphStore((s) => s.indexing);
  const viewMode = useGraphStore((s) => s.viewMode);
  const activeModulePath = useGraphStore((s) => s.activeModulePath);
  const activeNodeName = useGraphStore((s) => s.activeNodeName);
  const drillIntoFile = useGraphStore((s) => s.drillIntoFile);
  const drillIntoClass = useGraphStore((s) => s.drillIntoClass);
  const drillIntoFunction = useGraphStore((s) => s.drillIntoFunction);
  const drillIntoVariable = useGraphStore((s) => s.drillIntoVariable);
  const goBack = useGraphStore((s) => s.goBack);
  const goForward = useGraphStore((s) => s.goForward);

  const openFile = useEditorStore((s) => s.openFile);
  const requestRevealLine = useEditorStore((s) => s.requestRevealLine);

  // Control flow is the default view
  const [showControlFlow, setShowControlFlow] = useState(true);

  // Data fetching — only the active view's hook is enabled
  const { data: moduleGraphData } = useModuleGraph(isIndexing ? 2000 : false);
  const { data: fileMembersData } = useFileMembers(
    viewMode === "file-members" ? activeModulePath : null,
  );
  const { data: classDetailData } = useClassDetail(
    viewMode === "class-detail" ? activeNodeName : null,
  );
  const { data: functionData } = useFunctionDetail(
    viewMode === "function-detail" && !showControlFlow ? activeNodeName : null,
  );
  const { data: controlFlowData } = useFunctionControlFlow(
    viewMode === "function-detail" && showControlFlow ? activeNodeName : null,
  );
  const { data: variableData } = useVariableDetail(
    viewMode === "variable-flow" ? activeNodeName : null,
  );
  const queryResultData = useGraphStore((s) => s.queryResultData);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [layoutVersion, setLayoutVersion] = useState(0);

  useEffect(() => {
    setZoomLevel(zoom);
  }, [zoom, setZoomLevel]);

  // === Keyboard shortcuts: Cmd+[ / Cmd+] for back/forward ===
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "[") {
        e.preventDefault();
        goBack();
      } else if (e.key === "]") {
        e.preventDefault();
        goForward();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goBack, goForward]);

  // === Level 1: File tree ===
  const fileTree = useMemo(() => {
    if (viewMode !== "modules" || !moduleGraphData) return null;
    return buildFileTree(moduleGraphData.nodes, moduleGraphData.edges);
  }, [moduleGraphData, viewMode]);

  useEffect(() => {
    if (viewMode !== "modules" || !fileTree) return;
    const containEdges = fileTree.edges.filter((e) => e.type === "CONTAINS");
    const laid = computeDagreLayout(fileTree.nodes, containEdges, "LR");
    setNodes(laid);
    setEdges(fileTree.edges);
    setLayoutVersion((v) => v + 1);
  }, [fileTree, viewMode]);

  // === Level 2: File members ===
  useEffect(() => {
    if (viewMode !== "file-members" || !fileMembersData) return;
    const rawNodes = toFlowNodes(fileMembersData.nodes);
    const rawEdges = toFlowEdges(fileMembersData.edges);
    const laid = computeDagreLayout(rawNodes, rawEdges, "LR");
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [fileMembersData, viewMode]);

  // === Level 2b: Class detail ===
  useEffect(() => {
    if (viewMode !== "class-detail" || !classDetailData) return;
    const rawNodes = toFlowNodes(classDetailData.nodes);
    const rawEdges = toFlowEdges(classDetailData.edges);
    const laid = computeDagreLayout(rawNodes, rawEdges, "TB");
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [classDetailData, viewMode]);

  // === Level 3a: Function detail — control flow view (DEFAULT) ===
  useEffect(() => {
    if (viewMode !== "function-detail" || !showControlFlow || !controlFlowData) return;
    const rawNodes = toFlowNodes(controlFlowData.nodes, true);
    const rawEdges = toFlowEdges(controlFlowData.edges);

    const { nodes: withTerminals, edges: edgesWithTerminals } = injectTerminalMarkers(rawNodes, rawEdges);
    const laid = computeControlFlowLayout(withTerminals, edgesWithTerminals);
    const depthMap = computeNestingDepth(laid, edgesWithTerminals);
    const dupeMap = detectDuplicateBranches(laid, edgesWithTerminals);
    const withData = laid.map((n) => {
      const group = dupeMap.get(n.id);
      const nestingDepth = depthMap.get(n.id) ?? 0;
      return {
        ...n,
        data: {
          ...n.data,
          ...(group ? { duplicateGroup: group } : {}),
          nestingDepth,
        },
      };
    });

    setNodes(withData);
    setEdges(edgesWithTerminals);
    setLayoutVersion((v) => v + 1);
  }, [controlFlowData, viewMode, showControlFlow]);

  // === Level 3b: Function detail — semantic view ===
  useEffect(() => {
    if (viewMode !== "function-detail" || showControlFlow || !functionData) return;
    const rawNodes = toFlowNodes(functionData.nodes);
    const rawEdges = toFlowEdges(functionData.edges);
    const laid = computeForceLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [functionData, viewMode, showControlFlow]);

  // === Level 4: Variable flow ===
  useEffect(() => {
    if (viewMode !== "variable-flow" || !variableData) return;
    const rawNodes = toFlowNodes(variableData.nodes);
    const rawEdges = toFlowEdges(variableData.edges);
    const laid = computeDagreLayout(rawNodes, rawEdges, "LR");
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [variableData, viewMode]);

  // === Level 5: Query result / expanded usages ===
  useEffect(() => {
    if (viewMode !== "query-result" || !queryResultData) return;
    const rawNodes = toFlowNodes(queryResultData.nodes);
    const rawEdges = toFlowEdges(queryResultData.edges);
    const laid = computeForceLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    setLayoutVersion((v) => v + 1);
  }, [queryResultData, viewMode]);

  // Re-fit the viewport whenever a new layout is applied
  useEffect(() => {
    if (layoutVersion === 0) return;
    const timer = setTimeout(() => {
      fitView({ padding: 0.1, duration: 200 });
    }, 50);
    return () => clearTimeout(timer);
  }, [layoutVersion, fitView]);

  // Editor → Graph: cursor/selection highlights matching graph nodes
  const selectedRange = useEditorStore((s) => s.selectedRange);
  const highlightNodes = useGraphStore((s) => s.highlightNodes);
  const clearHighlights = useGraphStore((s) => s.clearHighlights);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  useEffect(() => {
    if (!selectedRange) {
      clearHighlights();
      return;
    }
    const currentNodes = nodesRef.current;
    const matching = currentNodes.filter((n) => {
      const sl = typeof n.data.start_line === "number" ? n.data.start_line
        : typeof n.data.line === "number" ? n.data.line : null;
      const el = typeof n.data.end_line === "number" ? n.data.end_line : sl;
      if (sl === null || el === null) return false;
      return sl <= selectedRange.end && el >= selectedRange.start;
    });
    if (matching.length > 0) {
      highlightNodes(matching.map((n) => n.id));
    } else {
      clearHighlights();
    }
  }, [selectedRange, highlightNodes, clearHighlights]);

  // Graph → Node: apply highlight data based on highlightedNodeIds
  const highlightedNodeIds = useGraphStore((s) => s.highlightedNodeIds);

  useEffect(() => {
    if (highlightedNodeIds.size === 0) {
      setNodes((prev) => {
        const anyHighlighted = prev.some((n) => n.data.highlighted === true);
        if (!anyHighlighted) return prev;
        return prev.map((n) =>
          n.data.highlighted ? { ...n, data: { ...n.data, highlighted: false } } : n,
        );
      });
      return;
    }
    setNodes((prev) =>
      prev.map((n) => {
        const shouldHighlight = highlightedNodeIds.has(n.id);
        if (n.data.highlighted === shouldHighlight) return n;
        return { ...n, data: { ...n.data, highlighted: shouldHighlight } };
      }),
    );
  }, [highlightedNodeIds]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  const handleNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (node.type === "Folder") return;

      const isMetaClick = event.metaKey || event.ctrlKey;
      const modulePath = typeof node.data.module_path === "string"
        ? node.data.module_path
        : "";
      const nodeName = typeof node.data.name === "string"
        ? node.data.name
        : node.id;
      const startLine = typeof node.data.start_line === "number"
        ? node.data.start_line
        : typeof node.data.line === "number"
          ? node.data.line
          : null;

      selectNode(node.id);

      // ---------------------------------------------------------------
      // Cmd+Click on a Function/Class: expand usages inline (neo4j-style)
      // Adds new nodes/edges to the current canvas without changing view
      // ---------------------------------------------------------------
      if (isMetaClick && (node.type === "Function" || node.type === "Class")) {
        // Open file + scroll in editor
        if (modulePath) openFile(modulePath);
        if (startLine !== null) {
          requestRevealLine(startLine);
          const endLine = typeof node.data.end_line === "number" ? node.data.end_line : startLine;
          useEditorStore.getState().setHighlightedLines({ start: startLine, end: endLine });
        }
        // Fetch usages and merge into current canvas
        void (async () => {
          const data = await fetchUsages(nodeName);
          if (!data) return;
          const newFlowNodes = toFlowNodes(data.nodes);
          const newFlowEdges = toFlowEdges(data.edges);
          setNodes((prev) => {
            const existingIds = new Set(prev.map((n) => n.id));
            const toAdd = newFlowNodes.filter((n) => !existingIds.has(n.id));
            // Position new nodes around the clicked node
            const cx = node.position.x;
            const cy = node.position.y;
            const positioned = toAdd.map((n, i) => ({
              ...n,
              position: {
                x: cx + 250 + (i % 3) * 200,
                y: cy - 100 + Math.floor(i / 3) * 120,
              },
            }));
            return [...prev, ...positioned];
          });
          setEdges((prev) => {
            const existingKeys = new Set(prev.map((e) => `${e.source}-${e.type}-${e.target}`));
            const toAdd = newFlowEdges.filter((e) => {
              const key = `${e.source}-${e.type}-${e.target}`;
              return !existingKeys.has(key);
            });
            return [...prev, ...toAdd];
          });
        })();
        return;
      }

      // ---------------------------------------------------------------
      // Normal Click: open file in editor + navigate graph
      // ---------------------------------------------------------------
      if (modulePath) {
        openFile(modulePath);
      }
      if (startLine !== null) {
        requestRevealLine(startLine);
        const endLine = typeof node.data.end_line === "number" ? node.data.end_line : startLine;
        useEditorStore.getState().setHighlightedLines({ start: startLine, end: endLine });
      } else {
        useEditorStore.getState().setHighlightedLines(null);
      }

      // Control flow leaf nodes and terminal markers: just scroll to line, don't drill
      if (
        node.type === "Statement" ||
        node.type === "ControlFlow" ||
        node.type === "Branch" ||
        node.type === "Terminal"
      ) {
        return;
      }

      // Drill into the appropriate next level
      if (viewMode === "modules" && node.type === "Module") {
        const fileName = modulePath.split("/").pop() ?? nodeName;
        drillIntoFile(modulePath, fileName);
      } else if (viewMode === "file-members" && node.type === "Class") {
        drillIntoClass(nodeName, modulePath);
      } else if (viewMode === "class-detail" && node.type === "Function") {
        drillIntoFunction(nodeName, modulePath);
      } else if (
        (viewMode === "file-members" || viewMode === "function-detail") &&
        (node.type === "Function" || node.type === "Class")
      ) {
        if (node.type === "Function") {
          drillIntoFunction(nodeName, modulePath);
        } else {
          drillIntoClass(nodeName, modulePath);
        }
      } else if (
        (viewMode === "function-detail" || viewMode === "file-members") &&
        node.type === "Variable"
      ) {
        drillIntoVariable(nodeName, modulePath);
      } else if (viewMode === "query-result") {
        if (node.type === "Module") {
          const fileName = modulePath.split("/").pop() ?? nodeName;
          drillIntoFile(modulePath, fileName);
        } else if (node.type === "Class") {
          drillIntoClass(nodeName, modulePath);
        } else if (node.type === "Function") {
          drillIntoFunction(nodeName, modulePath);
        } else if (node.type === "Variable") {
          drillIntoVariable(nodeName, modulePath);
        }
      }
    },
    [viewMode, selectNode, openFile, requestRevealLine, drillIntoFile, drillIntoClass, drillIntoFunction, drillIntoVariable],
  );

  return (
    <div className="relative h-full w-full">
      <Breadcrumb />
      {viewMode === "function-detail" && (
        <button
          onClick={() => setShowControlFlow((v) => !v)}
          className="absolute top-3 right-3 z-10 px-3 py-1 text-xs font-mono cursor-pointer"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        >
          {showControlFlow ? "Semantic View" : "Control Flow"}
        </button>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.1}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
        className="bg-[var(--bg-primary)]"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border)"
        />
        <MiniMap
          nodeColor={(n) => {
            switch (n.type) {
              case "Module":
                return "var(--node-module)";
              case "Class":
                return "var(--node-class)";
              case "Function":
                return "var(--node-function)";
              case "Variable":
                return "var(--node-variable)";
              case "Folder":
                return "var(--text-muted)";
              default:
                return "var(--text-muted)";
            }
          }}
          maskColor="rgba(0, 0, 0, 0.7)"
          style={{ background: "var(--bg-secondary)" }}
        />
        <Controls
          showInteractive={false}
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
        />
      </ReactFlow>
    </div>
  );
}

function GraphCanvas() {
  return <GraphCanvasInner />;
}

export default GraphCanvas;
