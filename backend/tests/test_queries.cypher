-- Test Cypher queries for manual smoke testing in TerminalChat
-- All queries verified against the sample_app graph data.
--
-- SCHEMA NOTES:
--   - :LogicNode with kind = 'function' | 'method' | 'class'
--   - Names are module-qualified: 'services.register_user', 'ingestion_flow.run'
--   - module_path is ABSOLUTE. Use CONTAINS for matching.
--   - Variable names include scope: 'ingestion_flow.run.parsed'

-- ===========================================================================
-- Basic node lookups
-- ===========================================================================

-- Find a function by name (use CONTAINS since names are qualified)
MATCH (n:LogicNode) WHERE n.name CONTAINS 'register_user' RETURN n.name, n.kind, n.module_path

-- All classes
MATCH (n:LogicNode {kind: 'class'}) RETURN n.name, n.module_path

-- All methods (NOTE: kind is 'method' for ALL functions until re-import fixes this to 'function')
MATCH (n:LogicNode {kind: 'method'}) RETURN n.name LIMIT 10

-- ===========================================================================
-- CALLS — who calls whom
-- ===========================================================================

-- What does register_user call?
MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode)
WHERE f.name CONTAINS 'register_user'
RETURN f.name AS caller, g.name AS callee

-- What does the ingestion pipeline's run() call?
MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode)
WHERE f.name CONTAINS 'ingestion_flow.run'
RETURN f.name AS caller, g.name AS callee

-- Who calls authenticate?
MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode)
WHERE target.name CONTAINS 'authenticate'
RETURN caller.name, target.name

-- All CALLS edges
MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode)
RETURN a.name AS caller, b.name AS callee

-- Cross-file calls
MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode)
WHERE a.module_path <> b.module_path
RETURN a.name AS caller, b.name AS callee LIMIT 10

-- Functions with high fan-out (many outgoing calls)
MATCH (n:LogicNode)-[r:CALLS]->()
WITH n, count(r) AS calls
WHERE calls > 2
RETURN n.name, calls ORDER BY calls DESC

-- ===========================================================================
-- Inheritance & class membership
-- ===========================================================================

-- Inheritance chain
MATCH (child:LogicNode)-[:INHERITS]->(parent:LogicNode)
RETURN child.name AS child, parent.name AS parent

-- Methods of OrderRepository
MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode)
WHERE c.name CONTAINS 'OrderRepository'
RETURN m.name AS method

-- All class methods
MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode {kind: 'class'})
RETURN c.name AS class, m.name AS method LIMIT 15

-- ===========================================================================
-- Variables — ASSIGNS, READS, MUTATES, RETURNS
-- ===========================================================================

-- Variables assigned by a function
MATCH (f:LogicNode)-[:ASSIGNS]->(v:Variable)
WHERE f.name CONTAINS 'register_user'
RETURN v.name, v.type_hint, v.origin_line ORDER BY v.origin_line

-- Variables mutated (side effects)
MATCH (fn:LogicNode)-[:MUTATES]->(v:Variable)
RETURN fn.name, v.name LIMIT 10

-- What does a function return?
MATCH (f:LogicNode)-[:RETURNS]->(v:Variable)
WHERE f.name CONTAINS 'parse_input'
RETURN f.name, v.name

-- Full variable lifecycle for a function
MATCH (fn:LogicNode)-[r]->(v:Variable)
WHERE fn.name CONTAINS 'ingestion_flow.run'
RETURN type(r) AS action, v.name, v.type_hint, v.is_parameter
ORDER BY v.origin_line

-- Cross-function variable flow: who reads what another assigns
MATCH (writer:LogicNode)-[:ASSIGNS]->(v:Variable)<-[:READS]-(reader:LogicNode)
WHERE writer <> reader
RETURN writer.name AS writer, v.name AS variable, reader.name AS reader
LIMIT 10

-- ===========================================================================
-- Data flow — PASSES_TO and FEEDS
-- ===========================================================================

-- PASSES_TO: trace arguments flowing across function calls
MATCH (v:Variable)-[:PASSES_TO]->(p:Variable)
RETURN v.name AS argument, p.name AS parameter LIMIT 10

-- Data flow through the ingestion pipeline
MATCH (v:Variable)-[:PASSES_TO]->(p:Variable)
WHERE v.name CONTAINS 'ingestion_flow.run.'
RETURN v.name AS from_var, p.name AS to_param

-- FEEDS: intra-function data flow (reads feeding into assignments)
MATCH (v1:Variable)-[:FEEDS]->(v2:Variable)
RETURN v1.name AS source, v2.name AS target LIMIT 10

-- Full pipeline trace: CALLS + PASSES_TO joined via Variable.scope
MATCH (caller:LogicNode)-[:CALLS]->(callee:LogicNode),
      (arg:Variable)-[:PASSES_TO]->(param:Variable)
WHERE caller.name = 'ingestion_flow.run'
  AND arg.scope = caller.name
  AND param.scope = callee.name
RETURN caller.name AS caller, callee.name AS callee,
       arg.name AS argument, param.name AS parameter

-- ===========================================================================
-- TypeShape queries
-- ===========================================================================

-- Functions that accept an Event type
MATCH (fn:LogicNode)-[:ACCEPTS]->(ts:TypeShape)
WHERE ts.base_type = 'Event'
RETURN fn.name, ts.kind, ts.definition

-- Functions that accept a Request type
MATCH (fn:LogicNode)-[:ACCEPTS]->(ts:TypeShape)
WHERE ts.base_type = 'Request'
RETURN fn.name, ts.kind

-- All distinct base types in the graph
MATCH (ts:TypeShape)
WHERE ts.base_type <> ''
RETURN DISTINCT ts.base_type, count(ts) AS cnt ORDER BY cnt DESC

-- Variable shapes (structural duck-typing evidence)
MATCH (v:Variable)-[:HAS_SHAPE]->(ts:TypeShape {kind: 'structural'})
RETURN v.name, ts.definition LIMIT 10

-- Compatible type shapes (non-trivial matches)
MATCH (ts1:TypeShape)-[:COMPATIBLE_WITH]->(ts2:TypeShape)
WHERE ts1.base_type <> '' AND ts2.base_type <> ''
RETURN ts1.base_type, ts2.base_type, ts1.kind, ts2.kind LIMIT 10

-- ===========================================================================
-- Duplicate detection
-- ===========================================================================

-- Functions with duplicate AST hashes
MATCH (n:LogicNode)
WHERE n.status = 'active'
WITH n.ast_hash AS hash, collect(n) AS nodes
WHERE size(nodes) > 2
UNWIND nodes AS n
RETURN n.name, n.module_path

-- Functions with duplicate structural hashes
MATCH (n:LogicNode)
WHERE n.status = 'active'
WITH n.structural_hash AS hash, collect(n) AS nodes
WHERE size(nodes) > 2
UNWIND nodes AS n
RETURN n.name, n.module_path

-- ===========================================================================
-- VFS projection queries (prefix with "vfs" in TerminalChat)
-- ===========================================================================

-- Project all functions
vfs MATCH (n:LogicNode) WHERE n.kind IN ['function', 'method'] RETURN n

-- Project a specific function and neighbours
vfs MATCH (n:LogicNode) WHERE n.name CONTAINS 'register_user' RETURN n

-- Project all classes and their methods
vfs MATCH (c:LogicNode {kind: 'class'})<-[:MEMBER_OF]-(m:LogicNode) RETURN c, m

-- Project cross-file calls
vfs MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode) WHERE a.module_path <> b.module_path RETURN a, b LIMIT 20

-- Project high fan-out functions
vfs MATCH (n:LogicNode)-[r:CALLS]->() WITH n, count(r) AS calls WHERE calls > 2 RETURN n ORDER BY calls DESC

-- Project functions that mutate variables
vfs MATCH (fn:LogicNode)-[:MUTATES]->(v:Variable) RETURN DISTINCT fn

-- Project all active nodes
vfs MATCH (n:LogicNode {status: 'active'}) RETURN n

-- ===========================================================================
-- Flow discovery — call chain tracing
-- ===========================================================================

-- Chain 5 (shallowest, 3 hops): handle_generate_report call tree
MATCH (entry:LogicNode)-[:CALLS*1..3]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_generate_report'
RETURN entry.name AS entry, callee.name AS callee

-- Chain 2 (deepest, 6 hops): full call tree from handle_process_payment
MATCH (entry:LogicNode)-[:CALLS*1..6]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_process_payment'
RETURN entry.name AS entry, callee.name AS callee

-- Chain 1: notification pipeline (5 hops)
MATCH (entry:LogicNode)-[:CALLS*1..5]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_send_notification'
RETURN entry.name AS entry, callee.name AS callee

-- Chain 6: authenticated request through middleware (6 hops)
MATCH (entry:LogicNode)-[:CALLS*1..6]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_authenticated_request'
RETURN entry.name AS entry, callee.name AS callee

-- Chain 7: bulk import pipeline (5 hops)
MATCH (entry:LogicNode)-[:CALLS*1..5]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_bulk_import'
RETURN entry.name AS entry, callee.name AS callee

-- ===========================================================================
-- Convergence / fan-in — shared functions called by many chains
-- ===========================================================================

-- Who calls audit_log? (should be 7+ callers — all chains converge here)
MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode)
WHERE target.name CONTAINS 'audit_log'
RETURN caller.name AS caller, target.name AS target

-- Who calls format_notification? (should be send_notification, send_welcome, flag_content)
MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode)
WHERE target.name CONTAINS 'format_notification'
RETURN caller.name AS caller, target.name AS target

-- Who calls resolve_user_context? (should be send_notification, process_payment, flag_content)
MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode)
WHERE target.name CONTAINS 'resolve_user_context'
RETURN caller.name AS caller, target.name AS target

-- Diamond dependency: functions that call BOTH audit_log AND format_notification
MATCH (fn:LogicNode)-[:CALLS]->(a:LogicNode),
      (fn)-[:CALLS]->(b:LogicNode)
WHERE a.name CONTAINS 'audit_log' AND b.name CONTAINS 'format_notification'
RETURN fn.name AS diamond_node

-- All shared convergence points: functions called by 3+ distinct callers
MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode)
WITH target, count(DISTINCT caller) AS fan_in
WHERE fan_in >= 3
RETURN target.name, fan_in ORDER BY fan_in DESC

-- ===========================================================================
-- Cross-module chain analysis
-- ===========================================================================

-- Full cross-module call paths from any handler (handlers.py → services → utils/auth)
MATCH path = (h:LogicNode)-[:CALLS*1..6]->(leaf:LogicNode)
WHERE h.name CONTAINS 'handle_'
  AND h.module_path CONTAINS 'handlers'
  AND leaf.module_path <> h.module_path
RETURN h.name AS handler, leaf.name AS leaf, length(path) AS depth
ORDER BY depth DESC LIMIT 20

-- Modules touched by the payment chain
MATCH (entry:LogicNode)-[:CALLS*1..6]->(callee:LogicNode)
WHERE entry.name CONTAINS 'handle_process_payment'
RETURN DISTINCT callee.module_path AS module ORDER BY module

-- ===========================================================================
-- Chain depth / shape analysis
-- ===========================================================================

-- Max depth reachable from each handler entry point
MATCH path = (h:LogicNode)-[:CALLS*1..8]->(leaf:LogicNode)
WHERE h.name CONTAINS 'handle_'
  AND h.module_path CONTAINS 'handlers'
  AND NOT (leaf)-[:CALLS]->()
RETURN h.name AS handler, max(length(path)) AS max_depth
ORDER BY max_depth DESC

-- Leaf functions (called but don't call anything) in sample_app
MATCH (caller:LogicNode)-[:CALLS]->(leaf:LogicNode)
WHERE NOT (leaf)-[:CALLS]->()
RETURN DISTINCT leaf.name AS leaf_function, leaf.module_path
ORDER BY leaf.module_path

-- Entry points (call others but nobody calls them)
MATCH (entry:LogicNode)-[:CALLS]->()
WHERE NOT ()-[:CALLS]->(entry)
  AND entry.module_path CONTAINS 'handlers'
RETURN entry.name AS entry_point

-- ===========================================================================
-- VFS projections for flow discovery chains
-- ===========================================================================

-- Project full payment chain subgraph
vfs MATCH (entry:LogicNode)-[:CALLS*1..6]->(callee:LogicNode) WHERE entry.name CONTAINS 'handle_process_payment' RETURN entry, callee

-- Project all handler entry points and their direct callees
vfs MATCH (h:LogicNode)-[:CALLS]->(callee:LogicNode) WHERE h.name CONTAINS 'handle_' AND h.module_path CONTAINS 'handlers' RETURN h, callee

-- Project the audit_log convergence subgraph (all callers + audit_log)
vfs MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode) WHERE target.name CONTAINS 'audit_log' RETURN caller, target

-- Project the notification formatting subgraph
vfs MATCH (caller:LogicNode)-[:CALLS]->(target:LogicNode) WHERE target.name CONTAINS 'format_notification' RETURN caller, target

-- ===========================================================================
-- Reachability — "can I get from X to Y?"
-- ===========================================================================

-- Can handle_process_payment reach audit_log? (yes — 3 hops via process_payment)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_process_payment'
  AND goal.name CONTAINS 'audit_log'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_send_notification reach generate_id? (yes — via audit_log → generate_id)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_send_notification'
  AND goal.name CONTAINS 'generate_id'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_process_payment reach discounted_price? (yes — deepest: 6 hops)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_process_payment'
  AND goal.name CONTAINS 'discounted_price'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_generate_report reach validate_email? (no — should return empty)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_generate_report'
  AND goal.name CONTAINS 'validate_email'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_bulk_import reach store_record? (yes — via run_bulk_import)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_bulk_import'
  AND goal.name CONTAINS 'store_record'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_onboard_user reach title_case? (yes — via send_welcome → format_notification → title_case)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_onboard_user'
  AND goal.name CONTAINS 'title_case'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Can handle_flag_content reach broadcast? (no — flag_content doesn't call broadcast)
MATCH path = (start:LogicNode)-[:CALLS*1..8]->(goal:LogicNode)
WHERE start.name CONTAINS 'handle_flag_content'
  AND goal.name CONTAINS 'broadcast'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Generic reachability template: replace START_NAME and GOAL_NAME
-- MATCH path = (s:LogicNode)-[:CALLS*1..8]->(g:LogicNode)
-- WHERE s.name CONTAINS 'START_NAME' AND g.name CONTAINS 'GOAL_NAME'
-- RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops

-- Shortest path between two functions (if reachable)
MATCH path = shortestPath((s:LogicNode)-[:CALLS*1..10]->(g:LogicNode))
WHERE s.name CONTAINS 'handle_process_payment'
  AND g.name CONTAINS 'generate_id'
RETURN [n IN nodes(path) | n.name] AS shortest_chain, length(path) AS hops

-- All paths between two functions (shows multiple routes through diamond deps)
MATCH path = (s:LogicNode)-[:CALLS*1..8]->(g:LogicNode)
WHERE s.name CONTAINS 'handle_onboard_user'
  AND g.name CONTAINS 'generate_id'
RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS hops
ORDER BY hops ASC

-- Reverse reachability: what entry points can reach audit_log?
MATCH path = (entry:LogicNode)-[:CALLS*1..8]->(target:LogicNode)
WHERE target.name CONTAINS 'audit_log'
  AND entry.module_path CONTAINS 'handlers'
RETURN entry.name AS reachable_from, length(path) AS hops
ORDER BY hops ASC

-- Reverse reachability: what entry points can reach format_notification?
MATCH path = (entry:LogicNode)-[:CALLS*1..8]->(target:LogicNode)
WHERE target.name CONTAINS 'format_notification'
  AND entry.module_path CONTAINS 'handlers'
RETURN entry.name AS reachable_from, length(path) AS hops
ORDER BY hops ASC
