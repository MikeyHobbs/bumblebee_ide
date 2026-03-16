import { create } from "zustand";

interface LayoutState {
  graphPanelWidth: number;
  editorPanelWidth: number;
  terminalPanelWidth: number;
  collapsedPanels: Set<string>;
  setPanelWidth: (panel: "graph" | "editor" | "terminal", width: number) => void;
  togglePanel: (panel: string) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  graphPanelWidth: 30,
  editorPanelWidth: 40,
  terminalPanelWidth: 30,
  collapsedPanels: new Set<string>(),
  setPanelWidth: (panel, width) => {
    switch (panel) {
      case "graph":
        set({ graphPanelWidth: width });
        break;
      case "editor":
        set({ editorPanelWidth: width });
        break;
      case "terminal":
        set({ terminalPanelWidth: width });
        break;
    }
  },
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
