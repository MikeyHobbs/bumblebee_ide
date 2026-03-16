import type { Node, Edge } from "@xyflow/react";

const CF_NODE_SIZES: Record<string, { width: number; height: number }> = {
  Statement: { width: 280, height: 36 },
  ControlFlow: { width: 140, height: 80 },
  Branch: { width: 140, height: 40 },
  Function: { width: 160, height: 50 },
  Class: { width: 160, height: 50 },
  Terminal: { width: 80, height: 28 },
};

const DEFAULT_SIZE = { width: 140, height: 40 };
const VGAP = 40;
const HGAP = 120;
const MIN_BRANCH_LANE_WIDTH = 200;

interface Bounds {
  width: number;
  height: number;
}

/**
 * Custom control flow layout that respects execution order.
 *
 * - Sequential code flows top-to-bottom.
 * - if/elif/else branches appear side-by-side at the same Y level.
 * - for/while loops occupy one vertical block, code after continues below.
 * - External CALLS targets are positioned in a right-side column.
 */
export function computeControlFlowLayout(
  nodes: Node[],
  edges: Edge[],
): Node[] {
  if (nodes.length === 0) return [];

  // Separate external call targets from flow nodes
  const externalIds = new Set(
    nodes
      .filter(
        (n) =>
          (n.type === "Function" || n.type === "Class") &&
          n.data.external === true,
      )
      .map((n) => n.id),
  );

  const flowNodes = nodes.filter((n) => !externalIds.has(n.id));
  const externalNodes = nodes.filter((n) => externalIds.has(n.id));

  // Separate terminal nodes (not part of CONTAINS tree)
  const terminalNodes = flowNodes.filter((n) => n.type === "Terminal");
  const coreNodes = flowNodes.filter((n) => n.type !== "Terminal");

  // Build CONTAINS tree
  const containsChildren = new Map<string, string[]>();
  const containsTargets = new Set<string>();
  for (const e of edges) {
    if (e.type === "CONTAINS") {
      const children = containsChildren.get(e.source) ?? [];
      children.push(e.target);
      containsChildren.set(e.source, children);
      containsTargets.add(e.target);
    }
  }

  // Build node map
  const nodeMap = new Map<string, Node>();
  for (const n of coreNodes) {
    nodeMap.set(n.id, n);
  }

  // Find root: CONTAINS source that is not a CONTAINS target
  let rootId: string | null = null;
  for (const id of containsChildren.keys()) {
    if (!containsTargets.has(id) && nodeMap.has(id)) {
      rootId = id;
      break;
    }
  }
  if (!rootId) {
    const fnNode = coreNodes.find((n) => n.type === "Function" || n.type === "Class");
    rootId = fnNode?.id ?? coreNodes[0]?.id ?? null;
  }
  if (!rootId) return [...terminalNodes, ...coreNodes, ...externalNodes];

  // Helper: get start_line for ordering children
  function getStartLine(nodeId: string): number {
    const n = nodeMap.get(nodeId);
    if (!n) return 0;
    if (typeof n.data.start_line === "number") return n.data.start_line;
    if (typeof n.data.line === "number") return n.data.line;
    return 0;
  }

  // Helper: get sorted children of a node (only those in nodeMap)
  function getSortedChildren(parentId: string): string[] {
    return (containsChildren.get(parentId) ?? [])
      .filter((c) => nodeMap.has(c))
      .sort((a, b) => getStartLine(a) - getStartLine(b));
  }

  // Helper: get node size
  function nodeSize(nodeId: string): { width: number; height: number } {
    const n = nodeMap.get(nodeId);
    return CF_NODE_SIZES[n?.type ?? ""] ?? DEFAULT_SIZE;
  }

  // --- Pass 1: measure subtrees bottom-up ---
  const sizeCache = new Map<string, Bounds>();
  const laneWidthCache = new Map<string, number[]>();

  function measureSubtree(nodeId: string): Bounds {
    if (sizeCache.has(nodeId)) return sizeCache.get(nodeId)!;

    const size = nodeSize(nodeId);
    const children = getSortedChildren(nodeId);

    if (children.length === 0) {
      const bounds = { width: size.width, height: size.height };
      sizeCache.set(nodeId, bounds);
      return bounds;
    }

    const branchChildren = children.filter((c) => nodeMap.get(c)?.type === "Branch");
    const nonBranchChildren = children.filter((c) => nodeMap.get(c)?.type !== "Branch");

    if (branchChildren.length > 1) {
      // Branching construct: branches go side-by-side
      const branchBounds = branchChildren.map((b) => measureSubtree(b));
      // Enforce a minimum lane width so even small branches are clearly separated
      const laneWidths = branchBounds.map((b) => Math.max(b.width, MIN_BRANCH_LANE_WIDTH));
      const totalBranchWidth =
        laneWidths.reduce((s, w) => s + w, 0) +
        (branchChildren.length - 1) * HGAP;
      const maxBranchHeight = Math.max(...branchBounds.map((b) => b.height));

      // Non-branch children stack below the branches
      let seqHeight = 0;
      let seqWidth = 0;
      for (const c of nonBranchChildren) {
        const s = measureSubtree(c);
        if (seqHeight > 0) seqHeight += VGAP;
        seqHeight += s.height;
        seqWidth = Math.max(seqWidth, s.width);
      }

      const width = Math.max(size.width, totalBranchWidth, seqWidth);
      const height =
        size.height +
        VGAP +
        maxBranchHeight +
        (nonBranchChildren.length > 0 ? VGAP + seqHeight : 0);

      // Store lane widths for use during placement
      laneWidthCache.set(nodeId, laneWidths);
      sizeCache.set(nodeId, { width, height });
      return { width, height };
    }

    // Default: all children stacked vertically
    let childrenHeight = 0;
    let childrenWidth = 0;
    for (const c of children) {
      if (childrenHeight > 0) childrenHeight += VGAP;
      const s = measureSubtree(c);
      childrenHeight += s.height;
      childrenWidth = Math.max(childrenWidth, s.width);
    }

    const width = Math.max(size.width, childrenWidth);
    const height = size.height + VGAP + childrenHeight;

    sizeCache.set(nodeId, { width, height });
    return { width, height };
  }

  // --- Pass 2: place nodes top-down ---
  const positions = new Map<string, { x: number; y: number }>();

  function placeSubtree(nodeId: string, centerX: number, topY: number): void {
    const size = nodeSize(nodeId);

    // Place the node itself, centered horizontally
    positions.set(nodeId, {
      x: centerX - size.width / 2,
      y: topY,
    });

    const children = getSortedChildren(nodeId);
    if (children.length === 0) return;

    const branchChildren = children.filter((c) => nodeMap.get(c)?.type === "Branch");
    const nonBranchChildren = children.filter((c) => nodeMap.get(c)?.type !== "Branch");

    let y = topY + size.height + VGAP;

    if (branchChildren.length > 1) {
      // Place branches side-by-side, centered around parent
      const branchBounds = branchChildren.map((b) => sizeCache.get(b)!);
      const laneWidths = laneWidthCache.get(nodeId) ??
        branchBounds.map((b) => Math.max(b.width, MIN_BRANCH_LANE_WIDTH));
      const totalBranchWidth =
        laneWidths.reduce((s, w) => s + w, 0) +
        (branchChildren.length - 1) * HGAP;

      let bx = centerX - totalBranchWidth / 2;
      let maxBranchHeight = 0;

      for (let i = 0; i < branchChildren.length; i++) {
        const laneWidth = laneWidths[i]!;
        const bCenterX = bx + laneWidth / 2;
        placeSubtree(branchChildren[i]!, bCenterX, y);
        bx += laneWidth + HGAP;
        maxBranchHeight = Math.max(maxBranchHeight, branchBounds[i]!.height);
      }

      y += maxBranchHeight + VGAP;

      // Non-branch children below the branches
      for (const c of nonBranchChildren) {
        placeSubtree(c, centerX, y);
        const s = sizeCache.get(c)!;
        y += s.height + VGAP;
      }
    } else {
      // Stack all children vertically
      for (const c of children) {
        placeSubtree(c, centerX, y);
        const s = sizeCache.get(c)!;
        y += s.height + VGAP;
      }
    }
  }

  // Execute the two-pass layout
  const rootBounds = measureSubtree(rootId);
  const margin = 30;
  const rootCenterX = rootBounds.width / 2 + margin;
  placeSubtree(rootId, rootCenterX, margin);

  // Apply positions to core nodes
  const positionedCore = coreNodes.map((node) => {
    const pos = positions.get(node.id);
    return pos ? { ...node, position: pos } : { ...node, position: { x: 0, y: 0 } };
  });

  // Position terminal nodes relative to the laid-out flow
  const rootPos = positions.get(rootId) ?? { x: margin, y: margin };
  const rootSize = nodeSize(rootId);
  const termSize = CF_NODE_SIZES["Terminal"] ?? DEFAULT_SIZE;

  let maxFlowY = 0;
  for (const [id, pos] of positions) {
    const n = nodeMap.get(id);
    const s = CF_NODE_SIZES[n?.type ?? ""] ?? DEFAULT_SIZE;
    maxFlowY = Math.max(maxFlowY, pos.y + s.height);
  }

  const termCenterX = rootPos.x + rootSize.width / 2;
  const positionedTerminals = terminalNodes.map((node) => {
    if (node.id === "__start__") {
      return {
        ...node,
        position: {
          x: termCenterX - termSize.width / 2,
          y: rootPos.y - VGAP - termSize.height,
        },
      };
    }
    if (node.id === "__end__") {
      return {
        ...node,
        position: {
          x: termCenterX - termSize.width / 2,
          y: maxFlowY + VGAP,
        },
      };
    }
    return { ...node, position: { x: 0, y: 0 } };
  });

  // External call targets: position in right column aligned with callers
  const allPositioned = [...positionedCore, ...positionedTerminals];
  let maxX = 0;
  for (const n of positionedCore) {
    const s = CF_NODE_SIZES[n.type ?? ""] ?? DEFAULT_SIZE;
    const right = n.position.x + s.width;
    if (right > maxX) maxX = right;
  }
  const externalX = maxX + 80;

  const callsEdges = edges.filter(
    (e) => e.type === "CALLS" && externalIds.has(e.target),
  );
  const flowPositionMap = new Map<string, { x: number; y: number }>();
  for (const n of positionedCore) {
    flowPositionMap.set(n.id, n.position);
  }

  const externalYMap = new Map<string, number>();
  for (const ce of callsEdges) {
    const srcPos = flowPositionMap.get(ce.source);
    if (srcPos && !externalYMap.has(ce.target)) {
      externalYMap.set(ce.target, srcPos.y);
    }
  }

  let fallbackY = 0;
  const positionedExternal = externalNodes.map((node) => {
    const y = externalYMap.get(node.id) ?? fallbackY;
    fallbackY = y + 70;
    return { ...node, position: { x: externalX, y } };
  });

  // Build loop group background nodes
  const loopGroups = buildLoopGroups(allPositioned, edges);

  return [...loopGroups, ...positionedTerminals, ...positionedCore, ...positionedExternal];
}

/**
 * Build background group nodes for for/while loops by computing
 * bounding boxes of their CONTAINS descendants.
 */
function buildLoopGroups(positionedNodes: Node[], edges: Edge[]): Node[] {
  const containsChildren = new Map<string, string[]>();
  for (const e of edges) {
    if (e.type === "CONTAINS") {
      const children = containsChildren.get(e.source) ?? [];
      children.push(e.target);
      containsChildren.set(e.source, children);
    }
  }

  const nodeMap = new Map<string, Node>();
  for (const n of positionedNodes) {
    nodeMap.set(n.id, n);
  }

  const loopNodes = positionedNodes.filter(
    (n) => n.type === "ControlFlow" && (n.data.kind === "for" || n.data.kind === "while"),
  );

  const groups: Node[] = [];
  const padding = 16;

  for (const loop of loopNodes) {
    // BFS to collect all descendants via CONTAINS
    const descendants: string[] = [];
    const queue = [loop.id];
    const visited = new Set<string>();
    visited.add(loop.id);

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

    if (descendants.length === 0) continue;

    // Compute bounding box including the loop node itself
    let minX = loop.position.x;
    let minY = loop.position.y;
    let maxX = loop.position.x + (CF_NODE_SIZES["ControlFlow"]?.width ?? 140);
    let maxY = loop.position.y + (CF_NODE_SIZES["ControlFlow"]?.height ?? 80);

    for (const descId of descendants) {
      const node = nodeMap.get(descId);
      if (!node) continue;
      const size = CF_NODE_SIZES[node.type ?? ""] ?? DEFAULT_SIZE;
      minX = Math.min(minX, node.position.x);
      minY = Math.min(minY, node.position.y);
      maxX = Math.max(maxX, node.position.x + size.width);
      maxY = Math.max(maxY, node.position.y + size.height);
    }

    const condText = typeof loop.data.condition_text === "string" ? loop.data.condition_text : "";
    const kind = typeof loop.data.kind === "string" ? loop.data.kind : "loop";
    const label = condText ? `${kind} ${condText}` : kind;

    groups.push({
      id: `loop-group:${loop.id}`,
      type: "LoopGroup",
      position: { x: minX - padding, y: minY - padding },
      zIndex: -1,
      data: {
        width: maxX - minX + padding * 2,
        height: maxY - minY + padding * 2,
        label,
      },
    });
  }

  return groups;
}
