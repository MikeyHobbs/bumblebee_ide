import { create } from "zustand";

interface LayoutState {
  graphPanelWidth: number;
  editorPanelWidth: number;
  topRowHeight: number;
  collapsedPanels: Set<string>;
  setPanelWidth: (panel: "graph" | "editor", width: number) => void;
  setTopRowHeight: (height: number) => void;
  togglePanel: (panel: string) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  graphPanelWidth: 50,
  editorPanelWidth: 50,
  topRowHeight: 65,
  collapsedPanels: new Set<string>(),
  setPanelWidth: (panel, width) => {
    switch (panel) {
      case "graph":
        set({ graphPanelWidth: width });
        break;
      case "editor":
        set({ editorPanelWidth: width });
        break;
    }
  },
  setTopRowHeight: (height) => set({ topRowHeight: height }),
  togglePanel: (panel) =>
    set((state) => {
      const next = new Set(state.collapsedPanels);
      if (next.has(panel)) {
        next.delete(panel);
      } else {
        next.add(panel);
      }
      return { collapsedPanels: next };
    }),
}));
