import type { EdgeTypes } from "@xyflow/react";
import CallsEdge from "./CallsEdge";
import MutatesEdge from "./MutatesEdge";
import AssignsEdge from "./AssignsEdge";
import PassesToEdge from "./PassesToEdge";
import ReadsEdge from "./ReadsEdge";
import DefinesEdge from "./DefinesEdge";
import ImportsEdge from "./ImportsEdge";
import InheritsEdge from "./InheritsEdge";
import ContainsEdge from "./ContainsEdge";
import ReturnsEdge from "./ReturnsEdge";
import FeedsEdge from "./FeedsEdge";
import NextEdge from "./NextEdge";

export const edgeTypes: EdgeTypes = {
  CALLS: CallsEdge,
  MUTATES: MutatesEdge,
  ASSIGNS: AssignsEdge,
  PASSES_TO: PassesToEdge,
  READS: ReadsEdge,
  DEFINES: DefinesEdge,
  IMPORTS: ImportsEdge,
  INHERITS: InheritsEdge,
  CONTAINS: ContainsEdge,
  RETURNS: ReturnsEdge,
  FEEDS: FeedsEdge,
  NEXT: NextEdge,
};
