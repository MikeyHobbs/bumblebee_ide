import type { EdgeTypes } from "@xyflow/react";
import CallsEdge from "./CallsEdge";
import MutatesEdge from "./MutatesEdge";
import AssignsEdge from "./AssignsEdge";
import PassesToEdge from "./PassesToEdge";
import ReadsEdge from "./ReadsEdge";

export const edgeTypes: EdgeTypes = {
  CALLS: CallsEdge,
  MUTATES: MutatesEdge,
  ASSIGNS: AssignsEdge,
  PASSES_TO: PassesToEdge,
  READS: ReadsEdge,
};
