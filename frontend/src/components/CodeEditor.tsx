import { useRef, useCallback, useEffect } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useEditorStore } from "@/store/editorStore";
import { useGraphStore } from "@/store/graphStore";
import { useFileContent } from "@/api/client";
import { getOrCreateModel } from "@/editor/ModelManager";
import MutationGutter from "./MutationGutter";

interface GraphNodeResponse {
  id: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
}

let definitionProviderRegistered = false;
let editorOpenerRegistered = false;

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

      // Intercept "open editor" requests from go-to-definition so we navigate using our stores
      if (!editorOpenerRegistered) {
        editorOpenerRegistered = true;
        monaco.editor.registerEditorOpener({
          openCodeEditor(
            _source: Monaco.editor.ICodeEditor,
            resource: Monaco.Uri,
            selectionOrPosition?: Monaco.IRange | Monaco.IPosition,
          ) {
            const filePath = resource.path.startsWith("/") ? resource.path.slice(1) : resource.path;
            if (filePath) {
              useEditorStore.getState().openFile(filePath);
              if (selectionOrPosition && "startLineNumber" in selectionOrPosition) {
                useEditorStore.getState().requestRevealLine(selectionOrPosition.startLineNumber);
              } else if (selectionOrPosition && "lineNumber" in selectionOrPosition) {
                useEditorStore.getState().requestRevealLine(selectionOrPosition.lineNumber);
              }
              // Also navigate the graph — find the node at this location
              void (async () => {
                const line = selectionOrPosition && "startLineNumber" in selectionOrPosition
                  ? selectionOrPosition.startLineNumber
                  : selectionOrPosition && "lineNumber" in selectionOrPosition
                    ? selectionOrPosition.lineNumber
                    : null;
                if (!line) return;
                try {
                  const res = await fetch(`/api/v1/graph/file-members/${filePath}`);
                  if (!res.ok) return;
                  const data = (await res.json()) as { nodes: GraphNodeResponse[] };
                  let best: GraphNodeResponse | null = null;
                  let bestSpan = Infinity;
                  for (const n of data.nodes) {
                    const sl = typeof n.properties["start_line"] === "number" ? n.properties["start_line"] : null;
                    const el = typeof n.properties["end_line"] === "number" ? n.properties["end_line"] : null;
                    if (sl !== null && el !== null && sl <= line && el >= line) {
                      const span = el - sl;
                      if (span < bestSpan) { bestSpan = span; best = n; }
                    }
                  }
                  if (best) {
                    const mp = typeof best.properties["module_path"] === "string" ? best.properties["module_path"] : filePath;
                    // First navigate to file in graph
                    const fileName = filePath.split("/").pop() ?? filePath;
                    useGraphStore.getState().drillIntoFile(filePath, fileName);
                    // Then drill into the function/class
                    if (best.label === "Function") {
                      useGraphStore.getState().drillIntoFunction(best.id, mp);
                    } else if (best.label === "Class") {
                      useGraphStore.getState().drillIntoClass(best.id, mp);
                    }
                  }
                } catch { /* non-critical */ }
              })();
            }
            return true; // We handled it
          },
        });
      }

      // Register go-to-definition provider backed by the code graph
      if (!definitionProviderRegistered) {
        definitionProviderRegistered = true;
        monaco.languages.registerDefinitionProvider("python", {
          provideDefinition: async (model: Monaco.editor.ITextModel, position: Monaco.Position) => {
            const word = model.getWordAtPosition(position);
            if (!word) return null;
            const symbol = word.word;

            // Query the graph for nodes matching this symbol name
            try {
              const res = await fetch("/api/v1/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  cypher: `MATCH (n) WHERE n.name ENDS WITH '.${symbol}' AND (n:Function OR n:Class) RETURN n LIMIT 5`,
                }),
              });
              if (!res.ok) return null;
              const data = (await res.json()) as { nodes: GraphNodeResponse[] };
              if (data.nodes.length === 0) {
                // Try exact name match
                const res2 = await fetch("/api/v1/query", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    cypher: `MATCH (n) WHERE n.name = '${symbol}' AND (n:Function OR n:Class OR n:Module) RETURN n LIMIT 5`,
                  }),
                });
                if (!res2.ok) return null;
                const data2 = (await res2.json()) as { nodes: GraphNodeResponse[] };
                if (data2.nodes.length === 0) return null;
                data.nodes = data2.nodes;
              }

              const results: Monaco.languages.Location[] = [];
              for (const node of data.nodes) {
                const mp = node.properties["module_path"];
                const sl = node.properties["start_line"];
                if (typeof mp === "string" && typeof sl === "number") {
                  const uri = monaco.Uri.parse(`file://${mp}`);
                  results.push({
                    uri,
                    range: {
                      startLineNumber: sl,
                      startColumn: 1,
                      endLineNumber: sl,
                      endColumn: 1,
                    },
                  });
                }
              }

              return results.length > 0 ? results : null;
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
