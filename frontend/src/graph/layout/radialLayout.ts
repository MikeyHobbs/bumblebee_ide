import type { Node, Edge } from "@xyflow/react";

export function computeRadialLayout(
  nodes: Node[],
  edges: Edge[],
  centerNodeId?: string,
): Node[] {
  if (nodes.length === 0) return [];

  const centerX = 400;
  const centerY = 300;
  const ringGap = 120;

  const adjacency = new Map<string, Set<string>>();
  for (const n of nodes) {
    adjacency.set(n.id, new Set());
  }
  for (const e of edges) {
    adjacency.get(e.source)?.add(e.target);
    adjacency.get(e.target)?.add(e.source);
  }

  const centerId = centerNodeId ?? nodes[0]?.id;
  if (centerId === undefined) return nodes;

  const visited = new Set<string>();
  const rings: string[][] = [];

  const queue: Array<{ id: string; depth: number }> = [
    { id: centerId, depth: 0 },
  ];
  visited.add(centerId);

  while (queue.length > 0) {
    const item = queue.shift();
    if (!item) break;

    while (rings.length <= item.depth) {
      rings.push([]);
    }
    const ring = rings[item.depth];
    if (ring) {
      ring.push(item.id);
    }

    const neighbors = adjacency.get(item.id);
    if (neighbors) {
      for (const neighbor of neighbors) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push({ id: neighbor, depth: item.depth + 1 });
        }
      }
    }
  }

  // Place unvisited nodes in the outermost ring
  for (const n of nodes) {
    if (!visited.has(n.id)) {
      const lastRing = rings[rings.length - 1];
      if (lastRing) {
        lastRing.push(n.id);
      } else {
        rings.push([n.id]);
      }
    }
  }

  const posMap = new Map<string, { x: number; y: number }>();

  for (let ringIdx = 0; ringIdx < rings.length; ringIdx++) {
    const ring = rings[ringIdx];
    if (!ring) continue;

    if (ringIdx === 0) {
      for (const id of ring) {
        posMap.set(id, { x: centerX, y: centerY });
      }
      continue;
    }

    const radius = ringIdx * ringGap;
    const angleStep = (2 * Math.PI) / ring.length;

    for (let i = 0; i < ring.length; i++) {
      const id = ring[i];
      if (id === undefined) continue;
      posMap.set(id, {
        x: centerX + radius * Math.cos(i * angleStep - Math.PI / 2),
        y: centerY + radius * Math.sin(i * angleStep - Math.PI / 2),
      });
    }
  }

  return nodes.map((n) => {
    const pos = posMap.get(n.id);
    return {
      ...n,
      position: {
        x: pos?.x ?? n.position.x,
        y: pos?.y ?? n.position.y,
      },
    };
  });
}
