import { useEffect, useRef } from "react";
import type * as Monaco from "monaco-editor";
import { useGraphStore } from "@/store/graphStore";

interface MutationGutterProps {
  editor: Monaco.editor.IStandaloneCodeEditor;
  filePath: string;
}

function MutationGutter({ editor, filePath }: MutationGutterProps) {
  const visibleEdges = useGraphStore((s) => s.visibleEdges);
  const decorationsRef = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null);

  useEffect(() => {
    const mutationLines = new Set<number>();
    const assignLines = new Set<number>();
    const readLines = new Set<number>();

    for (const edge of visibleEdges) {
      const edgeFile =
        typeof edge.properties["file"] === "string"
          ? edge.properties["file"]
          : null;
      if (edgeFile !== null && !filePath.endsWith(edgeFile)) continue;

      const line =
        typeof edge.properties["line"] === "number"
          ? edge.properties["line"]
          : null;
      if (line === null) continue;

      switch (edge.type) {
        case "MUTATES":
          mutationLines.add(line);
          break;
        case "ASSIGNS":
          assignLines.add(line);
          break;
        case "READS":
          readLines.add(line);
          break;
      }
    }

    const decorations: Monaco.editor.IModelDeltaDecoration[] = [];

    for (const line of mutationLines) {
      decorations.push({
        range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 },
        options: {
          isWholeLine: true,
          glyphMarginClassName: "mutation-gutter-icon",
          glyphMarginHoverMessage: { value: "Mutation" },
          overviewRuler: {
            color: "var(--edge-mutation)",
            position: 1 as Monaco.editor.OverviewRulerLane,
          },
        },
      });
    }

    for (const line of assignLines) {
      decorations.push({
        range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 },
        options: {
          isWholeLine: true,
          glyphMarginClassName: "assign-gutter-icon",
          glyphMarginHoverMessage: { value: "Assignment" },
        },
      });
    }

    for (const line of readLines) {
      decorations.push({
        range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 },
        options: {
          isWholeLine: true,
          glyphMarginClassName: "read-gutter-icon",
          glyphMarginHoverMessage: { value: "Read" },
        },
      });
    }

    if (decorationsRef.current) {
      decorationsRef.current.clear();
    }
    decorationsRef.current = editor.createDecorationsCollection(decorations);

    return () => {
      if (decorationsRef.current) {
        decorationsRef.current.clear();
      }
    };
  }, [editor, filePath, visibleEdges]);

  // This component renders no DOM - it only manages Monaco decorations
  return null;
}

export default MutationGutter;
