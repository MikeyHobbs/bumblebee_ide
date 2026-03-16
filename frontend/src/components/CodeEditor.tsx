import { useRef, useCallback, useEffect } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useEditorStore } from "@/store/editorStore";
import { useFileContent } from "@/api/client";
import { getOrCreateModel } from "@/editor/ModelManager";
import MutationGutter from "./MutationGutter";

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
    },
    [setCursorPosition],
  );

  useEffect(() => {
    if (!activeFile || !fileData || !monacoRef.current || !editorRef.current) return;
    const model = getOrCreateModel(
      monacoRef.current,
      activeFile,
      fileData.content,
    );
    editorRef.current.setModel(model);
  }, [activeFile, fileData]);

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
