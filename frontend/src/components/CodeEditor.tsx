import { useRef, useCallback, useEffect, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useEditorStore } from "@/store/editorStore";
import { useGraphStore } from "@/store/graphStore";
import { getOrCreateNodeModel } from "@/editor/ModelManager";
import ExternalRefsPanel from "./ExternalRefsPanel";

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
  const activeNodeView = useEditorStore((s) => s.activeNodeView);
  const setCursorPosition = useEditorStore((s) => s.setCursorPosition);
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const [editorReady, setEditorReady] = useState(false);

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

  // Set Monaco model when activeNodeView changes
  useEffect(() => {
    if (!activeNodeView || !monacoRef.current || !editorRef.current) return;
    const model = getOrCreateNodeModel(
      monacoRef.current,
      activeNodeView.nodeId,
      activeNodeView.sourceText,
      activeNodeView.modulePath,
    );
    editorRef.current.setModel(model);
    editorRef.current.revealLineInCenter(1);
  }, [activeNodeView, editorReady]);

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

  if (!activeNodeView) {
    return (
      <div
        className="flex items-center justify-center h-full text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        Click a graph node to view its source
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-0">
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
            readOnly: true,
            scrollbar: {
              verticalScrollbarSize: 6,
              horizontalScrollbarSize: 6,
            },
          }}
        />
      </div>
      <ExternalRefsPanel nodeId={activeNodeView.nodeId} />
    </div>
  );
}

export default CodeEditor;
