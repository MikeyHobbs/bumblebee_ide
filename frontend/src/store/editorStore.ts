import { create } from "zustand";

interface CursorPosition {
  line: number;
  column: number;
}

interface EditorState {
  activeFile: string | null;
  openFiles: string[];
  cursorPosition: CursorPosition;
  pinnedFiles: Set<string>;
  openFile: (path: string) => void;
  closeFile: (path: string) => void;
  setActiveFile: (path: string | null) => void;
  setCursorPosition: (pos: CursorPosition) => void;
  pinFile: (path: string) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  activeFile: null,
  openFiles: [],
  cursorPosition: { line: 1, column: 1 },
  pinnedFiles: new Set<string>(),
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
}));
