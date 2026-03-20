import { create } from "zustand";
import { useGraphStore } from "./graphStore";
import type { GraphCompletionItem } from "@/api/suggestions";

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

  // Graph autocomplete mode
  graphAutoComplete: boolean;
  pendingSuggestions: GraphCompletionItem[];
  suggestionContext: { variableName: string; trigger: string } | null;

  // Tab actions
  openTab: (tab: EditorTab) => void;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateTabContent: (tabId: string, content: string) => void;
  markDirty: (tabId: string) => void;
  markClean: (tabId: string) => void;
  updateTab: (tabId: string, patch: Partial<Pick<EditorTab, "nodeId" | "label" | "modulePath" | "sourceNodeIds">>) => void;

  // Clear all tabs (e.g. on codebase switch)
  clearAllTabs: () => void;

  // Backward compat — creates/reuses tab with matching nodeId
  openNodeView: (view: NodeView) => void;

  // Graph autocomplete
  toggleGraphAutoComplete: () => void;
  setPendingSuggestions: (items: GraphCompletionItem[], context: { variableName: string; trigger: string } | null) => void;
  clearPendingSuggestions: () => void;

  // VFS session (Graph AC click-to-add/remove)
  addNodeToVfsSession: (nodeId: string, name: string, sourceText: string, modulePath: string) => void;
  removeNodeFromVfsSession: (nodeId: string) => void;

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
  graphAutoComplete: false,
  pendingSuggestions: [],
  suggestionContext: null,

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

  clearAllTabs: () => set({ tabs: [], activeTabId: null }),

  toggleGraphAutoComplete: () =>
    set((state) => {
      const next = !state.graphAutoComplete;
      if (!next) {
        // Turning off — clear suggestion highlights
        useGraphStore.getState().clearHighlights();
      }
      return { graphAutoComplete: next, pendingSuggestions: next ? state.pendingSuggestions : [], suggestionContext: next ? state.suggestionContext : null };
    }),

  setPendingSuggestions: (items, context) =>
    set((state) => {
      if (!state.graphAutoComplete) return state;
      // Highlight suggestion nodes in the graph
      const nodeIds = items.map((i) => i.node_id).filter(Boolean);
      if (nodeIds.length > 0) {
        useGraphStore.getState().highlightNodes(nodeIds);
      } else {
        useGraphStore.getState().clearHighlights();
      }
      return { pendingSuggestions: items, suggestionContext: context };
    }),

  clearPendingSuggestions: () =>
    set((state) => {
      if (state.pendingSuggestions.length === 0) return state;
      useGraphStore.getState().clearHighlights();
      return { pendingSuggestions: [], suggestionContext: null };
    }),

  addNodeToVfsSession: (nodeId, _name, sourceText, _modulePath) =>
    set((state) => {
      // Find existing VFS session tab (active preferred, else any __vfs_session__ tab)
      let vfsTab = state.tabs.find(
        (t) => t.id === state.activeTabId && t.modulePath.startsWith("__vfs_session__"),
      );
      if (!vfsTab) {
        vfsTab = state.tabs.find((t) => t.modulePath.startsWith("__vfs_session__"));
      }

      if (vfsTab) {
        // Already in this tab? no-op
        if (vfsTab.sourceNodeIds.includes(nodeId)) return state;
        const newContent = vfsTab.content
          ? `${vfsTab.content}\n\n${sourceText}`
          : sourceText;
        const newSourceNodeIds = [...vfsTab.sourceNodeIds, nodeId];
        // Update highlight set
        useGraphStore.getState().highlightNodes(newSourceNodeIds);
        return {
          tabs: state.tabs.map((t) =>
            t.id === vfsTab!.id
              ? { ...t, content: newContent, sourceNodeIds: newSourceNodeIds }
              : t,
          ),
          activeTabId: vfsTab.id,
        };
      }

      // No VFS session tab yet — create one
      const tabId = crypto.randomUUID();
      const newTab: EditorTab = {
        id: tabId,
        label: "vfs session",
        nodeId: null,
        modulePath: `__vfs_session__.${tabId}`,
        content: sourceText,
        language: "python",
        sourceNodeIds: [nodeId],
        flowId: null,
        gaps: null,
        isDirty: false,
      };
      useGraphStore.getState().highlightNodes([nodeId]);
      return {
        tabs: [...state.tabs, newTab],
        activeTabId: tabId,
      };
    }),

  removeNodeFromVfsSession: (nodeId) =>
    set((state) => {
      const vfsTab = state.tabs.find(
        (t) => t.modulePath.startsWith("__vfs_session__") && t.sourceNodeIds.includes(nodeId),
      );
      if (!vfsTab) return state;

      const newSourceNodeIds = vfsTab.sourceNodeIds.filter((id) => id !== nodeId);

      // If empty after removal, close the tab
      if (newSourceNodeIds.length === 0) {
        useGraphStore.getState().clearHighlights();
        const newTabs = state.tabs.filter((t) => t.id !== vfsTab.id);
        return {
          tabs: newTabs,
          activeTabId:
            state.activeTabId === vfsTab.id
              ? newTabs.length > 0
                ? newTabs[newTabs.length - 1]!.id
                : null
              : state.activeTabId,
        };
      }

      // Rebuild content by re-fetching source per remaining node isn't feasible here,
      // so we strip the removed node's source by splitting on double-newline blocks.
      // A simpler approach: just remove the highlight and keep content as-is for now,
      // then refetch assembled content from the remaining nodes.
      useGraphStore.getState().highlightNodes(newSourceNodeIds);

      // We need to rebuild content. Dispatch an event so the component can refetch.
      setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent("bumblebee:vfs-rebuild", {
            detail: { tabId: vfsTab.id, nodeIds: newSourceNodeIds },
          }),
        );
      }, 0);

      return {
        tabs: state.tabs.map((t) =>
          t.id === vfsTab.id
            ? { ...t, sourceNodeIds: newSourceNodeIds }
            : t,
        ),
      };
    }),

  setCursorPosition: (pos) => set({ cursorPosition: pos }),
  setHighlightedLines: (range) => set({ highlightedLines: range }),
  setSelectedRange: (range) => set({ selectedRange: range }),
}));

/** Open the Cypher eval comparison panel as an editor tab. */
export function openCypherEvalTab(): void {
  const state = useEditorStore.getState();
  const existing = state.tabs.find((t) => t.modulePath === "__cypher_eval__");
  if (existing) {
    state.setActiveTab(existing.id);
    return;
  }
  state.openTab({
    id: crypto.randomUUID(),
    label: "Cypher Eval",
    nodeId: null,
    modulePath: "__cypher_eval__",
    content: "",
    language: "plaintext",
    sourceNodeIds: [],
    flowId: null,
    gaps: null,
    isDirty: false,
  });
}

/** Check if a node is currently in any VFS session tab. */
export function isNodeInVfsSession(nodeId: string): boolean {
  return useEditorStore.getState().tabs.some(
    (t) => t.modulePath.startsWith("__vfs_session__") && t.sourceNodeIds.includes(nodeId),
  );
}
