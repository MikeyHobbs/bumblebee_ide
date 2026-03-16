import { create } from "zustand";

interface NavigationState {
  navigationStack: string[];
  pushNavigation: (nodeId: string) => void;
  popNavigation: () => void;
  clearNavigation: () => void;
}

export const useNavigationStore = create<NavigationState>((set) => ({
  navigationStack: [],
  pushNavigation: (nodeId) =>
    set((state) => ({
      navigationStack: [...state.navigationStack, nodeId],
    })),
  popNavigation: () =>
    set((state) => ({
      navigationStack: state.navigationStack.slice(0, -1),
    })),
  clearNavigation: () => set({ navigationStack: [] }),
}));
