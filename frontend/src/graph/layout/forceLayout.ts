import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { Node, Edge } from "@xyflow/react";

interface SimNode extends SimulationNodeDatum {
  id: string;
}

type SimLink = SimulationLinkDatum<SimNode>;

export function computeForceLayout(
  nodes: Node[],
  edges: Edge[],
): Node[] {
  if (nodes.length === 0) return [];

  const simNodes: SimNode[] = nodes.map((n) => ({
    id: n.id,
    x: n.position.x || Math.random() * 800,
    y: n.position.y || Math.random() * 600,
  }));

  const simLinks: SimLink[] = edges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  const simulation = forceSimulation(simNodes)
    .force(
      "link",
      forceLink<SimNode, SimLink>(simLinks)
        .id((d) => d.id)
        .distance(200),
    )
    .force("charge", forceManyBody().strength(-600))
    .force("center", forceCenter(400, 300))
    .force("collide", forceCollide(100))
    .stop();

  for (let i = 0; i < 300; i++) {
    simulation.tick();
  }

  const posMap = new Map<string, { x: number; y: number }>();
  for (const sn of simNodes) {
    posMap.set(sn.id, { x: sn.x ?? 0, y: sn.y ?? 0 });
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
