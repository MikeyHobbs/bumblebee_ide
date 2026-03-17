import type { Node } from "@xyflow/react";

export type SemanticZoomTier = "overview" | "module" | "detail";

const overviewLabels = new Set(["Module"]);
const moduleLabels = new Set(["Module", "Class", "Function"]);

/** Map React Flow zoom level to semantic tier. */
export function getSemanticZoomTier(zoom: number): SemanticZoomTier {
  if (zoom < 0.4) return "overview";
  if (zoom > 1.2) return "detail";
  return "module";
}

/** Map Sigma camera ratio to semantic tier (inverted: lower ratio = more zoomed in). */
export function getSigmaZoomTier(cameraRatio: number): SemanticZoomTier {
  if (cameraRatio > 2.5) return "overview";
  if (cameraRatio < 0.5) return "detail";
  return "module";
}

/** Label render threshold by tier — used to set Sigma's labelRenderedSizeThreshold. */
export function labelThresholdForTier(tier: SemanticZoomTier): number {
  switch (tier) {
    case "overview": return 999; // hide all labels
    case "module": return 6;    // show labels on larger nodes
    case "detail": return 2;    // show most labels
  }
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
