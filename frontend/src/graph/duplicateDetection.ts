import type { Node, Edge } from "@xyflow/react";

const DUPE_PALETTE = ["#d94444", "#5b8dd9", "#e8a838", "#4ec990", "#9b59b6"];

/**
 * Detect branches with identical logic shape by fingerprinting their descendants.
 *
 * Returns a map of nodeId -> color string for nodes belonging to duplicate groups.
 */
export function detectDuplicateBranches(
  nodes: Node[],
  edges: Edge[],
): Map<string, string> {
  const result = new Map<string, string>();

  // Build adjacency for CONTAINS edges (parent -> children)
  const containsChildren = new Map<string, string[]>();
  for (const e of edges) {
    if (e.type === "CONTAINS") {
      const children = containsChildren.get(e.source) ?? [];
      children.push(e.target);
      containsChildren.set(e.source, children);
    }
  }

  const nodeMap = new Map<string, Node>();
  for (const n of nodes) {
    nodeMap.set(n.id, n);
  }

  // Find all Branch nodes
  const branchNodes = nodes.filter((n) => n.type === "Branch");
  if (branchNodes.length < 2) return result;

  // For each branch, BFS descendants and build fingerprint
  const branchFingerprints = new Map<string, string>();
  const branchDescendants = new Map<string, string[]>();

  for (const branch of branchNodes) {
    const descendants: string[] = [];
    const queue = [branch.id];
    const visited = new Set<string>();
    visited.add(branch.id);

    while (queue.length > 0) {
      const current = queue.shift()!;
      const children = containsChildren.get(current) ?? [];
      for (const childId of children) {
        if (!visited.has(childId)) {
          visited.add(childId);
          descendants.push(childId);
          queue.push(childId);
        }
      }
    }

    // Sort descendants by seq if available
    descendants.sort((a, b) => {
      const nodeA = nodeMap.get(a);
      const nodeB = nodeMap.get(b);
      const seqA = typeof nodeA?.data.seq === "number" ? nodeA.data.seq : 0;
      const seqB = typeof nodeB?.data.seq === "number" ? nodeB.data.seq : 0;
      return seqA - seqB;
    });

    // Build fingerprint from descendant kinds and call targets
    const parts: string[] = [];
    for (const id of descendants) {
      const node = nodeMap.get(id);
      if (!node) continue;
      const kind = typeof node.data.kind === "string" ? node.data.kind : node.type ?? "";
      const callTarget = typeof node.data.call_target === "string" ? node.data.call_target : "";
      parts.push(`${kind}:${callTarget}`);
    }

    const fingerprint = parts.join("|");
    if (fingerprint.length > 0) {
      branchFingerprints.set(branch.id, fingerprint);
      branchDescendants.set(branch.id, descendants);
    }
  }

  // Group branches by fingerprint
  const fingerprintGroups = new Map<string, string[]>();
  for (const [branchId, fp] of branchFingerprints) {
    const group = fingerprintGroups.get(fp) ?? [];
    group.push(branchId);
    fingerprintGroups.set(fp, group);
  }

  // Assign colors to groups with 2+ members
  let colorIdx = 0;
  for (const group of fingerprintGroups.values()) {
    if (group.length < 2) continue;
    const color = DUPE_PALETTE[colorIdx % DUPE_PALETTE.length]!;
    colorIdx++;

    for (const branchId of group) {
      result.set(branchId, color);
      const descendants = branchDescendants.get(branchId) ?? [];
      for (const descId of descendants) {
        result.set(descId, color);
      }
    }
  }

  return result;
}
