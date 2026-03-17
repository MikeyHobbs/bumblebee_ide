import { create } from "zustand";

interface CursorPosition {
  line: number;
  column: number;
}

interface LineRange {
  start: number;
  end: number;
}

export interface NodeView {
  nodeId: string;
  name: string;
  kind: string;
  sourceText: string;
  modulePath: string;
}

interface EditorState {
  activeNodeView: NodeView | null;
  nodeViewHistory: NodeView[];
  cursorPosition: CursorPosition;
  highlightedLines: LineRange | null;
  selectedRange: LineRange | null;
  openNodeView: (view: NodeView) => void;
  goBackNode: () => void;
  clearNodeView: () => void;
  setCursorPosition: (pos: CursorPosition) => void;
  setHighlightedLines: (range: LineRange | null) => void;
  setSelectedRange: (range: LineRange | null) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  activeNodeView: null,
  nodeViewHistory: [],
  cursorPosition: { line: 1, column: 1 },
  highlightedLines: null,
  selectedRange: null,
  openNodeView: (view) =>
    set((state) => {
      const history = state.activeNodeView
        ? [...state.nodeViewHistory, state.activeNodeView]
        : state.nodeViewHistory;
      return { activeNodeView: view, nodeViewHistory: history };
    }),
  goBackNode: () =>
    set((state) => {
      if (state.nodeViewHistory.length === 0) {
        return { activeNodeView: null };
      }
      const history = [...state.nodeViewHistory];
      const prev = history.pop()!;
      return { activeNodeView: prev, nodeViewHistory: history };
    }),
  clearNodeView: () => set({ activeNodeView: null, nodeViewHistory: [] }),
  setCursorPosition: (pos) => set({ cursorPosition: pos }),
  setHighlightedLines: (range) => set({ highlightedLines: range }),
  setSelectedRange: (range) => set({ selectedRange: range }),
}));
