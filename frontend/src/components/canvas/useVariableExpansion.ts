import { useEffect } from "react";
import type Graph from "graphology";
import type Sigma from "sigma";
import type { NodeVariable } from "@/api/client";
import { localName } from "./useGraphSync";

const VARIABLE_COLOR = "#ffd54f";   // local / assign / mutate
const PARAM_COLOR = "#81d4fa";      // input parameters
const ATTR_COLOR = "#ce93d8";       // attributes
const RETURN_COLOR = "#a5d6a7";     // return values
const READS_COLOR = "#ffab91";      // required data (globals, reads)

export { VARIABLE_COLOR };

export function varColor(v: { is_parameter: boolean; is_attribute: boolean; edge_type: string }): string {
  if (v.is_parameter) return PARAM_COLOR;
  if (v.edge_type === "RETURNS") return RETURN_COLOR;
  if (v.edge_type === "READS") return READS_COLOR;
  if (v.is_attribute) return ATTR_COLOR;
  return VARIABLE_COLOR;
}

/**
 * Handle variable expansion: show real variable nodes orbiting the parent node.
 */
export function useVariableExpansion(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  expandedNodeId: string | null,
  expandedVariables: NodeVariable[] | undefined,
) {
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    // Remove any existing variable nodes first
    const toRemove: string[] = [];
    graph.forEachNode((node, attrs) => {
      if (attrs.isVariable) toRemove.push(node);
    });
    for (const nodeId of toRemove) {
      graph.dropNode(nodeId);
    }

    // Add variable nodes from the fetched variable data
    if (expandedNodeId && expandedVariables && graph.hasNode(expandedNodeId)) {
      const parentAttrs = graph.getNodeAttributes(expandedNodeId);
      const parentX = parentAttrs.x as number;
      const parentY = parentAttrs.y as number;

      // Compute graph extent from actual node positions
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      graph.forEachNode((_, attrs) => {
        const nx = attrs.x as number;
        const ny = attrs.y as number;
        if (nx < minX) minX = nx;
        if (nx > maxX) maxX = nx;
        if (ny < minY) minY = ny;
        if (ny > maxY) maxY = ny;
      });
      const graphSpan = Math.max(maxX - minX, maxY - minY) || 100;

      // Orbit radius = ~3% of the total graph span — tight orbit
      const radius = graphSpan * 0.03;

      const angleStep = expandedVariables.length > 0 ? (2 * Math.PI) / expandedVariables.length : 0;

      expandedVariables.forEach((v, i) => {
        const angle = angleStep * i;
        const varId = `var:${v.id}`;
        if (graph.hasNode(varId)) return;

        const shortName = localName(v.name);
        const typeStr = v.type_hint ? `: ${v.type_hint}` : "";
        const label = `${shortName}${typeStr}`;
        const col = varColor(v);

        graph.addNode(varId, {
          x: parentX + radius * Math.cos(angle),
          y: parentY + radius * Math.sin(angle),
          size: 1.5,
          color: col,
          originalColor: col,
          label,
          kind: "variable",
          isVariable: true,
          realNodeId: v.id,
          fixed: true,
        });

        try {
          graph.addEdge(expandedNodeId, varId, {
            color: col + "66",
            size: 0.5,
            type: "arrow",
            edgeType: v.edge_type,
            isVariable: true,
          });
        } catch {
          // skip duplicate
        }
      });
    }

    sigmaRef.current?.refresh();
  }, [expandedNodeId, expandedVariables, graphRef, sigmaRef]);
}

/**
 * Handle variable trace: highlight connected LogicNodes.
 */
export function useVariableTrace(
  graphRef: React.RefObject<Graph | null>,
  sigmaRef: React.RefObject<Sigma | null>,
  traceRef: React.MutableRefObject<Set<string>>,
  tracedVariableId: string | null,
  traceVariables: NodeVariable[] | undefined,
) {
  useEffect(() => {
    if (tracedVariableId && traceVariables) {
      const traced = new Set<string>();
      traced.add(tracedVariableId);
      const graph = graphRef.current;
      if (graph) {
        // Find all LogicNodes that share an edge with this variable
        for (const v of traceVariables) {
          const varNodeId = `var:${v.id}`;
          if (graph.hasNode(varNodeId)) traced.add(varNodeId);
        }
        // Also trace the origin node
        graph.forEachNode((node, attrs) => {
          if (!attrs.isVariable) {
            // Check if any variable edge connects this node to the traced variable
            for (const v of traceVariables) {
              if (v.id === tracedVariableId || `var:${v.id}` === tracedVariableId) {
                traced.add(node);
              }
            }
          }
        });
      }
      traceRef.current = traced;
    } else {
      traceRef.current = new Set();
    }
    sigmaRef.current?.refresh();
  }, [tracedVariableId, traceVariables, graphRef, sigmaRef, traceRef]);
}
