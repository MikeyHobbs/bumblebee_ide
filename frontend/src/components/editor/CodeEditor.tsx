import { useRef, useCallback, useEffect, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useQueryClient } from "@tanstack/react-query";
import { useEditorStore } from "@/store/editorStore";
import { useGraphStore } from "@/store/graphStore";
import { getOrCreateNodeModel, getOrCreateTabModel } from "@/editor/ModelManager";
import ExternalRefsPanel from "../panels/ExternalRefsPanel";
import CypherEvalPanel from "../panels/CypherEvalPanel";
import { apiFetch } from "@/api/client";

interface GraphNodeResponse {
  id: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
}

let definitionProviderRegistered = false;

function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

function CodeEditor() {
  const activeTab = useEditorStore((s) => {
    const tab = s.tabs.find((t) => t.id === s.activeTabId);
    return tab ?? null;
  });
  const setCursorPosition = useEditorStore((s) => s.setCursorPosition);
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const [editorReady, setEditorReady] = useState(false);
  const contentListenerRef = useRef<Monaco.IDisposable | null>(null);

  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      monacoRef.current = monaco;
      setEditorReady(true);

      editor.onDidChangeCursorPosition((e) => {
        setCursorPosition({
          line: e.position.lineNumber,
          column: e.position.column,
        });
      });

      editor.onDidChangeCursorSelection((e) => {
        const { startLineNumber, endLineNumber } = e.selection;
        useEditorStore.getState().setSelectedRange({ start: startLineNumber, end: endLineNumber });
      });

      // Apply dark theme
      monaco.editor.defineTheme("bumblebee-dark", {
        base: "vs-dark",
        inherit: true,
        rules: [],
        colors: {
          "editor.background": "#0a0a0a",
          "editor.foreground": "#e0e0e0",
          "editorLineNumber.foreground": "#444444",
          "editorLineNumber.activeForeground": "#777777",
          "editor.selectionBackground": "#333333",
          "editor.lineHighlightBackground": "#111111",
          "editorCursor.foreground": "#4ec990",
        },
      });
      monaco.editor.setTheme("bumblebee-dark");

      // Cmd+S: save active tab
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        const state = useEditorStore.getState();
        const tab = state.tabs.find((t) => t.id === state.activeTabId);
        if (tab) {
          window.dispatchEvent(new CustomEvent("bumblebee:save-tab", { detail: { tabId: tab.id } }));
        }
      });

      // Cmd+Click / Ctrl+Click: resolve symbol to graph node and navigate
      if (!definitionProviderRegistered) {
        definitionProviderRegistered = true;
        monaco.languages.registerDefinitionProvider("python", {
          provideDefinition: async (model: Monaco.editor.ITextModel, position: Monaco.Position) => {
            const word = model.getWordAtPosition(position);
            if (!word) return null;
            const symbol = word.word;

            try {
              const graphNodes: GraphNodeResponse[] = [];

              // 1. suffix match
              const res1 = await fetch("/api/v1/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  cypher: `MATCH (n) WHERE n.name ENDS WITH '.${symbol}' AND (n:Function OR n:Class) RETURN n LIMIT 10`,
                }),
              });
              if (res1.ok) {
                const data = (await res1.json()) as { nodes: GraphNodeResponse[] };
                graphNodes.push(...data.nodes);
              }

              // 2. exact match
              if (graphNodes.length === 0) {
                const res2 = await fetch("/api/v1/query", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    cypher: `MATCH (n) WHERE n.name = '${symbol}' AND (n:Function OR n:Class OR n:Module) RETURN n LIMIT 10`,
                  }),
                });
                if (res2.ok) {
                  const data = (await res2.json()) as { nodes: GraphNodeResponse[] };
                  graphNodes.push(...data.nodes);
                }
              }

              if (graphNodes.length === 0) return null;

              // Navigate to the first match as a NodeView
              const target = graphNodes[0]!;
              const sourceText = typeof target.properties["source_text"] === "string"
                ? target.properties["source_text"]
                : "";
              const modulePath = typeof target.properties["module_path"] === "string"
                ? target.properties["module_path"]
                : "";
              const kind = typeof target.properties["kind"] === "string"
                ? target.properties["kind"]
                : "";
              const name = typeof target.properties["name"] === "string"
                ? target.properties["name"]
                : target.id;

              if (sourceText) {
                useEditorStore.getState().openNodeView({
                  nodeId: target.id,
                  name: localName(name),
                  kind,
                  sourceText,
                  modulePath,
                });

                // Also navigate graph to this node
                const shortName = name.split(".").pop() ?? name;
                useGraphStore.getState().navigateToNode(target.id, shortName);
              }

              return null; // We handle navigation ourselves
            } catch {
              return null;
            }
          },
        });
      }
    },
    [setCursorPosition],
  );

  // Set Monaco model when activeTab changes
  useEffect(() => {
    if (!activeTab || !monacoRef.current || !editorRef.current) return;

    // Dispose previous content listener
    contentListenerRef.current?.dispose();

    let model: Monaco.editor.ITextModel;
    if (activeTab.nodeId) {
      model = getOrCreateNodeModel(
        monacoRef.current,
        activeTab.nodeId,
        activeTab.content,
        activeTab.modulePath,
      );
    } else {
      model = getOrCreateTabModel(
        monacoRef.current,
        activeTab.id,
        activeTab.content,
        activeTab.language,
      );
    }
    editorRef.current.setModel(model);
    editorRef.current.revealLineInCenter(1);

    // Listen for content changes and sync to store
    contentListenerRef.current = editorRef.current.onDidChangeModelContent(() => {
      const state = useEditorStore.getState();
      const currentTabId = state.activeTabId;
      if (currentTabId) {
        const value = editorRef.current?.getModel()?.getValue() ?? "";
        state.updateTabContent(currentTabId, value);
      }
    });
  }, [activeTab?.id, activeTab?.nodeId, editorReady]);

  // Handle Cmd+S save via custom event
  useEffect(() => {
    const handler = async (e: Event) => {
      const tabId = (e as CustomEvent).detail?.tabId;
      if (!tabId) return;
      const state = useEditorStore.getState();
      const tab = state.tabs.find((t) => t.id === tabId);
      if (!tab) return;

      if (tab.nodeId) {
        // Save existing node
        try {
          const res = await apiFetch<{
            updated_node: { id: string };
            impacted_nodes: Array<{ id: string; name: string; reason: string }>;
          }>("/api/v1/compose/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: tab.nodeId, source: tab.content }),
          });
          useEditorStore.getState().markClean(tabId);
          if (res.impacted_nodes.length > 0) {
            useGraphStore.getState().setImpactedNodes(res.impacted_nodes.map((n) => n.id));
          }
        } catch (err) {
          console.error("Save failed:", err);
        }
      } else {
        // Parse compose buffer
        try {
          const res = await apiFetch<{
            report: { nodes_created: number };
            nodes: Array<{ id: string; name: string }>;
          }>("/api/v1/compose/parse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source: tab.content, module_path: tab.modulePath }),
          });
          useEditorStore.getState().markClean(tabId);

          // Update tab with the first created node
          if (res.nodes.length > 0) {
            const node = res.nodes[0]!;
            const shortName = node.name.split(".").pop() ?? node.name;
            useEditorStore.getState().updateTab(tabId, {
              nodeId: node.id,
              label: shortName,
            });

            // Force refetch graph overview so the new node appears in graphology,
            // then navigate/highlight once the data is available
            await queryClientRef.current.invalidateQueries({ queryKey: ["graph-overview"] });
            await queryClientRef.current.refetchQueries({ queryKey: ["graph-overview"] });

            // Small delay to let React render the incremental sync effect
            setTimeout(() => {
              useGraphStore.getState().navigateToNode(node.id, shortName);
              useGraphStore.getState().highlightNodes(res.nodes.map((n) => n.id));
            }, 300);
          }
        } catch (err) {
          console.error("Parse failed:", err);
        }
      }
    };

    window.addEventListener("bumblebee:save-tab", handler);
    return () => window.removeEventListener("bumblebee:save-tab", handler);
  }, []);

  // Graph → Editor highlight decorations
  const highlightedLines = useEditorStore((s) => s.highlightedLines);
  const highlightDecorationsRef = useRef<string[]>([]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (highlightedLines) {
      highlightDecorationsRef.current = editor.deltaDecorations(
        highlightDecorationsRef.current,
        [{
          range: {
            startLineNumber: highlightedLines.start,
            startColumn: 1,
            endLineNumber: highlightedLines.end,
            endColumn: 1,
          },
          options: { isWholeLine: true, className: "graph-highlight-line" },
        }],
      );
    } else {
      highlightDecorationsRef.current = editor.deltaDecorations(
        highlightDecorationsRef.current,
        [],
      );
    }
  }, [highlightedLines]);

  // Render CypherEvalPanel for __cypher_eval__ tabs
  if (activeTab?.modulePath === "__cypher_eval__") {
    return <CypherEvalPanel />;
  }

  return (
    <div className="flex flex-col h-full">
      {!activeTab && (
        <div
          className="flex items-center justify-center h-full text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          Click a graph node or press + to start editing
        </div>
      )}
      <div className="flex-1 min-h-0" style={{ display: activeTab ? undefined : "none" }}>
        <Editor
          defaultLanguage="plaintext"
          theme="bumblebee-dark"
          onMount={handleMount}
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'SF Mono', 'Consolas', monospace",
            lineNumbers: "on",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            renderWhitespace: "selection",
            tabSize: 4,
            wordWrap: "off",
            padding: { top: 8, bottom: 8 },
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 16,
            overviewRulerLanes: 0,
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            readOnly: false,
            scrollbar: {
              verticalScrollbarSize: 6,
              horizontalScrollbarSize: 6,
            },
          }}
        />
      </div>
      {activeTab?.nodeId && <ExternalRefsPanel nodeId={activeTab.nodeId} />}
    </div>
  );
}

export default CodeEditor;
