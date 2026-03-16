import { create } from "zustand";

interface CursorPosition {
  line: number;
  column: number;
}

interface LineRange {
  start: number;
  end: number;
}

interface EditorState {
  activeFile: string | null;
  openFiles: string[];
  cursorPosition: CursorPosition;
  revealLine: number | null;
  pinnedFiles: Set<string>;
  highlightedLines: LineRange | null;
  selectedRange: LineRange | null;
  openFile: (path: string) => void;
  closeFile: (path: string) => void;
  setActiveFile: (path: string | null) => void;
  setCursorPosition: (pos: CursorPosition) => void;
  requestRevealLine: (line: number) => void;
  clearRevealLine: () => void;
  pinFile: (path: string) => void;
  setHighlightedLines: (range: LineRange | null) => void;
  setSelectedRange: (range: LineRange | null) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  activeFile: null,
  openFiles: [],
  cursorPosition: { line: 1, column: 1 },
  revealLine: null,
  pinnedFiles: new Set<string>(),
  highlightedLines: null,
  selectedRange: null,
  openFile: (path) =>
    set((state) => {
      if (state.openFiles.includes(path)) {
        return { activeFile: path };
      }
      return { openFiles: [...state.openFiles, path], activeFile: path };
    }),
  closeFile: (path) =>
    set((state) => {
      const filtered = state.openFiles.filter((f) => f !== path);
      const nextActive =
        state.activeFile === path
          ? filtered[filtered.length - 1] ?? null
          : state.activeFile;
      const nextPinned = new Set(state.pinnedFiles);
      nextPinned.delete(path);
      return {
        openFiles: filtered,
        activeFile: nextActive,
        pinnedFiles: nextPinned,
      };
    }),
  setActiveFile: (path) => set({ activeFile: path }),
  setCursorPosition: (pos) => set({ cursorPosition: pos }),
  requestRevealLine: (line) => set({ revealLine: line }),
  clearRevealLine: () => set({ revealLine: null }),
  pinFile: (path) =>
    set((state) => {
      const next = new Set(state.pinnedFiles);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return { pinnedFiles: next };
    }),
  setHighlightedLines: (range) => set({ highlightedLines: range }),
  setSelectedRange: (range) => set({ selectedRange: range }),
}));
