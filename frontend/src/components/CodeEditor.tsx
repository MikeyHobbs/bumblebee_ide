import { useRef, useCallback, useEffect } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useEditorStore } from "@/store/editorStore";
import { useGraphStore } from "@/store/graphStore";
import { useFileContent } from "@/api/client";
import { getOrCreateModel } from "@/editor/ModelManager";
import MutationGutter from "./MutationGutter";
import type { GraphNode, GraphEdge } from "@/types/graph";

interface GraphNodeResponse {
  id: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
}

interface UsagesResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

let definitionProviderRegistered = false;
let editorOpenerRegistered = false;

/**
 * Stash of resolved definition targets keyed by "filePath:line".
 * The DefinitionProvider populates this, the EditorOpener reads it
 * to know which node the user navigated to and fetches its usages graph.
 */
const resolvedTargets = new Map<string, string>(); // "path:line" → qualified node name

function CodeEditor() {
  const activeFile = useEditorStore((s) => s.activeFile);
  const setCursorPosition = useEditorStore((s) => s.setCursorPosition);
  const { data: fileData } = useFileContent(activeFile);
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);

  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      monacoRef.current = monaco;

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

      // Intercept navigation from go-to-definition — open file, scroll, and show usages graph
      if (!editorOpenerRegistered) {
        editorOpenerRegistered = true;
        monaco.editor.registerEditorOpener({
          openCodeEditor(
            _source: Monaco.editor.ICodeEditor,
            resource: Monaco.Uri,
            selectionOrPosition?: Monaco.IRange | Monaco.IPosition,
          ) {
            const filePath = resource.path.startsWith("/") ? resource.path.slice(1) : resource.path;
            if (!filePath) return true;

            // Open file and scroll
            useEditorStore.getState().openFile(filePath);
            const line = selectionOrPosition && "startLineNumber" in selectionOrPosition
              ? selectionOrPosition.startLineNumber
              : selectionOrPosition && "lineNumber" in selectionOrPosition
                ? selectionOrPosition.lineNumber
                : null;
            if (line !== null) {
              useEditorStore.getState().requestRevealLine(line);
            }

            // Look up which node this target corresponds to and show its usages graph
            const targetKey = `${filePath}:${line ?? 0}`;
            const nodeName = resolvedTargets.get(targetKey);
            if (nodeName) {
              void (async () => {
                try {
                  const res = await fetch(`/api/v1/graph/usages/${encodeURIComponent(nodeName)}`);
                  if (res.ok) {
                    const usages = (await res.json()) as UsagesResponse;
                    if (usages.nodes.length > 0) {
                      const shortName = nodeName.split(".").pop() ?? nodeName;
                      useGraphStore.getState().showQueryResult(shortName, usages.nodes, usages.edges);
                    }
                  }
                } catch { /* non-critical */ }
              })();
            }

            return true;
          },
        });
      }

      // Cmd+Click / Ctrl+Click: resolve symbol to graph nodes
      // Returns ALL matches — Monaco shows a picker if ambiguous, single-click if unique
      if (!definitionProviderRegistered) {
        definitionProviderRegistered = true;
        monaco.languages.registerDefinitionProvider("python", {
          provideDefinition: async (model: Monaco.editor.ITextModel, position: Monaco.Position) => {
            const word = model.getWordAtPosition(position);
            if (!word) return null;
            const symbol = word.word;

            try {
              // Find all graph nodes matching this symbol
              const allNodes: GraphNodeResponse[] = [];

              // 1. suffix match: module.Class.symbol
              const res1 = await fetch("/api/v1/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  cypher: `MATCH (n) WHERE n.name ENDS WITH '.${symbol}' AND (n:Function OR n:Class) RETURN n LIMIT 10`,
                }),
              });
              if (res1.ok) {
                const data = (await res1.json()) as { nodes: GraphNodeResponse[] };
                allNodes.push(...data.nodes);
              }

              // 2. exact match: just "symbol" (for top-level functions/modules)
              if (allNodes.length === 0) {
                const res2 = await fetch("/api/v1/query", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    cypher: `MATCH (n) WHERE n.name = '${symbol}' AND (n:Function OR n:Class OR n:Module) RETURN n LIMIT 10`,
                  }),
                });
                if (res2.ok) {
                  const data = (await res2.json()) as { nodes: GraphNodeResponse[] };
                  allNodes.push(...data.nodes);
                }
              }

              if (allNodes.length === 0) return null;

              // Build definition locations and stash node names for the EditorOpener
              resolvedTargets.clear();
              const locations: Monaco.languages.Location[] = [];

              for (const node of allNodes) {
                const mp = node.properties["module_path"];
                const sl = node.properties["start_line"];
                const name = typeof node.properties["name"] === "string"
                  ? node.properties["name"] as string
                  : node.id;

                if (typeof mp === "string" && typeof sl === "number") {
                  const targetKey = `${mp}:${sl}`;
                  resolvedTargets.set(targetKey, name);
                  locations.push({
                    uri: monaco.Uri.parse(`file://${mp}`),
                    range: {
                      startLineNumber: sl,
                      startColumn: 1,
                      endLineNumber: sl,
                      endColumn: 1,
                    },
                  });
                }
              }

              // If only one match, also eagerly show its usages graph
              if (locations.length === 1 && allNodes.length === 1) {
                const nodeName = typeof allNodes[0]!.properties["name"] === "string"
                  ? allNodes[0]!.properties["name"] as string
                  : allNodes[0]!.id;
                void (async () => {
                  try {
                    const usagesRes = await fetch(`/api/v1/graph/usages/${encodeURIComponent(nodeName)}`);
                    if (usagesRes.ok) {
                      const usages = (await usagesRes.json()) as UsagesResponse;
                      if (usages.nodes.length > 0) {
                        const shortName = nodeName.split(".").pop() ?? nodeName;
                        useGraphStore.getState().showQueryResult(shortName, usages.nodes, usages.edges);
                      }
                    }
                  } catch { /* non-critical */ }
                })();
              }

              return locations.length > 0 ? locations : null;
            } catch {
              return null;
            }
          },
        });
      }
    },
    [setCursorPosition],
  );

  const revealLine = useEditorStore((s) => s.revealLine);
  const clearRevealLine = useEditorStore((s) => s.clearRevealLine);

  useEffect(() => {
    if (!activeFile || !fileData || !monacoRef.current || !editorRef.current) return;
    const model = getOrCreateModel(
      monacoRef.current,
      activeFile,
      fileData.content,
    );
    editorRef.current.setModel(model);
  }, [activeFile, fileData]);

  useEffect(() => {
    if (revealLine === null || !editorRef.current) return;
    editorRef.current.revealLineInCenter(revealLine);
    editorRef.current.setPosition({ lineNumber: revealLine, column: 1 });
    clearRevealLine();
  }, [revealLine, clearRevealLine]);

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

  if (!activeFile) {
    return (
      <div
        className="flex items-center justify-center h-full text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        No file open
      </div>
    );
  }

  return (
    <div className="relative h-full">
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
          glyphMargin: true,
          folding: true,
          lineDecorationsWidth: 16,
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
          overviewRulerBorder: false,
          scrollbar: {
            verticalScrollbarSize: 6,
            horizontalScrollbarSize: 6,
          },
        }}
      />
      {activeFile && editorRef.current && (
        <MutationGutter
          editor={editorRef.current}
          filePath={activeFile}
        />
      )}
    </div>
  );
}

export default CodeEditor;
