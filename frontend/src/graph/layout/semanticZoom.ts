import type { Node } from "@xyflow/react";

export type SemanticZoomTier = "overview" | "module" | "detail";

const overviewLabels = new Set(["Module"]);
const moduleLabels = new Set(["Module", "Class", "Function"]);

export function getSemanticZoomTier(zoom: number): SemanticZoomTier {
  if (zoom < 0.4) return "overview";
  if (zoom > 1.2) return "detail";
  return "module";
}

export function filterByZoomTier(
  nodes: Node[],
  tier: SemanticZoomTier,
): Node[] {
  switch (tier) {
    case "overview":
      return nodes.filter((n) => overviewLabels.has(n.type ?? ""));
    case "module":
      return nodes.filter((n) => moduleLabels.has(n.type ?? ""));
    case "detail":
      return nodes;
  }
}
