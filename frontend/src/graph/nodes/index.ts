import type { NodeTypes } from "@xyflow/react";
import ModuleNode from "./ModuleNode";
import ClassNode from "./ClassNode";
import FunctionNode from "./FunctionNode";
import VariableNode from "./VariableNode";
import StatementNode from "./StatementNode";
import ControlFlowNode from "./ControlFlowNode";
import BranchNode from "./BranchNode";
import VariablePill from "./VariablePill";

export const nodeTypes: NodeTypes = {
  Module: ModuleNode,
  Class: ClassNode,
  Function: FunctionNode,
  Variable: VariableNode,
  Statement: StatementNode,
  ControlFlow: ControlFlowNode,
  Branch: BranchNode,
  VariablePill: VariablePill,
};
