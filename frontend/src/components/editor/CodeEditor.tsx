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
import { provideCompletionItems } from "@/editor/completionService";

interface GraphNodeResponse {
  id: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
}

let definitionProviderRegistered = false;
let completionProviderRegistered = false;

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
  const graphAutoComplete = useEditorStore((s) => s.graphAutoComplete);
  const toggleGraphAutoComplete = useEditorStore((s) => s.toggleGraphAutoComplete);
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

      // Graph-aware autocomplete
      if (!completionProviderRegistered) {
        completionProviderRegistered = true;
        monaco.languages.registerCompletionItemProvider("python", {
          triggerCharacters: [".", " "],
          provideCompletionItems: (
            model: Monaco.editor.ITextModel,
            position: Monaco.Position,
            context: Monaco.languages.CompletionContext,
            token: Monaco.CancellationToken,
          ) => provideCompletionItems(model, position, context, token, monaco),
        });
      }

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

  // Graph autocomplete: listen for insertion events from Atlas canvas clicks
  useEffect(() => {
    const handler = (e: Event) => {
      const editor = editorRef.current;
      if (!editor) return;
      const { text } = (e as CustomEvent).detail as { text: string; nodeId: string };
      const position = editor.getPosition();
      if (!position) return;

      const model = editor.getModel();
      if (!model) return;

      // Insert on the next line after cursor, with proper indentation
      const currentLine = model.getLineContent(position.lineNumber);
      const indentMatch = currentLine.match(/^(\s*)/);
      const indent = indentMatch ? indentMatch[1]! : "";
      const insertLine = position.lineNumber + 1;
      const insertText = `\n${indent}${text}`;

      // Insert at end of current line
      const lineLength = currentLine.length;
      editor.executeEdits("graph-autocomplete", [{
        range: {
          startLineNumber: position.lineNumber,
          startColumn: lineLength + 1,
          endLineNumber: position.lineNumber,
          endColumn: lineLength + 1,
        },
        text: insertText,
      }]);

      // Move cursor to end of inserted text
      const newPos = { lineNumber: insertLine, column: indent.length + text.length + 1 };
      editor.setPosition(newPos);
      editor.focus();
    };

    window.addEventListener("bumblebee:insert-suggestion", handler);
    return () => window.removeEventListener("bumblebee:insert-suggestion", handler);
  }, []);

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
      <div className="flex-1 min-h-0 relative" style={{ display: activeTab ? undefined : "none" }}>
        {/* Graph Autocomplete toggle */}
        <button
          onClick={toggleGraphAutoComplete}
          className="absolute top-2 right-2 z-10 flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors"
          style={{
            background: graphAutoComplete ? "#4ec990" : "#1a1a1a",
            color: graphAutoComplete ? "#0a0a0a" : "#888",
            border: `1px solid ${graphAutoComplete ? "#4ec990" : "#333"}`,
          }}
          title="Toggle graph-aware autocomplete — suggestions highlight in the graph canvas. Click a node to insert its call."
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ opacity: graphAutoComplete ? 1 : 0.5 }}>
            <circle cx="4" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.2" />
            <circle cx="12" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.2" />
            <circle cx="8" cy="13" r="2.5" stroke="currentColor" strokeWidth="1.2" />
            <line x1="5.5" y1="5.8" x2="7" y2="11" stroke="currentColor" strokeWidth="1" />
            <line x1="10.5" y1="5.8" x2="9" y2="11" stroke="currentColor" strokeWidth="1" />
            <line x1="6" y1="4" x2="10" y2="4" stroke="currentColor" strokeWidth="1" />
          </svg>
          Graph AC
        </button>
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
            quickSuggestions: { other: true, strings: false, comments: false },
            suggestOnTriggerCharacters: true,
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
