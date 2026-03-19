import { create } from "zustand";
import { useGraphStore } from "./graphStore";

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

export interface Gap {
  type: string;
  message: string;
  line?: number;
}

export interface EditorTab {
  id: string;
  label: string;
  nodeId: string | null;
  modulePath: string;
  content: string;
  language: string;
  sourceNodeIds: string[];
  flowId: string | null;
  gaps: Gap[] | null;
  isDirty: boolean;
}

interface EditorState {
  tabs: EditorTab[];
  activeTabId: string | null;
  cursorPosition: CursorPosition;
  highlightedLines: LineRange | null;
  selectedRange: LineRange | null;

  // Tab actions
  openTab: (tab: EditorTab) => void;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateTabContent: (tabId: string, content: string) => void;
  markDirty: (tabId: string) => void;
  markClean: (tabId: string) => void;
  updateTab: (tabId: string, patch: Partial<Pick<EditorTab, "nodeId" | "label" | "modulePath" | "sourceNodeIds">>) => void;

  // Backward compat — creates/reuses tab with matching nodeId
  openNodeView: (view: NodeView) => void;

  // Cursor (unchanged)
  setCursorPosition: (pos: CursorPosition) => void;
  setHighlightedLines: (range: LineRange | null) => void;
  setSelectedRange: (range: LineRange | null) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  tabs: [],
  activeTabId: null,
  cursorPosition: { line: 1, column: 1 },
  highlightedLines: null,
  selectedRange: null,

  openTab: (tab) =>
    set((state) => ({
      tabs: [...state.tabs, tab],
      activeTabId: tab.id,
    })),

  closeTab: (tabId) =>
    set((state) => {
      const closedTab = state.tabs.find((t) => t.id === tabId);
      const newTabs = state.tabs.filter((t) => t.id !== tabId);
      let newActiveId = state.activeTabId;
      if (state.activeTabId === tabId) {
        // Switch to the last remaining tab, or null
        newActiveId = newTabs.length > 0 ? newTabs[newTabs.length - 1]!.id : null;
      }
      // Remove the closed tab's node from graph highlights
      if (closedTab?.nodeId) {
        useGraphStore.getState().removeHighlightNode(closedTab.nodeId);
      }
      return { tabs: newTabs, activeTabId: newActiveId };
    }),

  setActiveTab: (tabId) => set({ activeTabId: tabId }),

  updateTabContent: (tabId, content) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === tabId ? { ...t, content, isDirty: true } : t,
      ),
    })),

  markDirty: (tabId) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === tabId ? { ...t, isDirty: true } : t,
      ),
    })),

  markClean: (tabId) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === tabId ? { ...t, isDirty: false } : t,
      ),
    })),

  updateTab: (tabId, patch) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === tabId ? { ...t, ...patch } : t,
      ),
    })),

  openNodeView: (view) =>
    set((state) => {
      // Check if a tab with this nodeId already exists
      const existing = state.tabs.find((t) => t.nodeId === view.nodeId);
      if (existing) {
        // Update content if changed, then switch to it
        const tabs = state.tabs.map((t) =>
          t.id === existing.id && t.content !== view.sourceText && !t.isDirty
            ? { ...t, content: view.sourceText }
            : t,
        );
        return { tabs, activeTabId: existing.id };
      }
      // Create a new tab
      const newTab: EditorTab = {
        id: crypto.randomUUID(),
        label: view.name,
        nodeId: view.nodeId,
        modulePath: view.modulePath,
        content: view.sourceText,
        language: "python",
        sourceNodeIds: [],
        flowId: null,
        gaps: null,
        isDirty: false,
      };
      return {
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      };
    }),

  setCursorPosition: (pos) => set({ cursorPosition: pos }),
  setHighlightedLines: (range) => set({ highlightedLines: range }),
  setSelectedRange: (range) => set({ selectedRange: range }),
}));
