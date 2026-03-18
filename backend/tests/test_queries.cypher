-- Test Cypher queries for manual smoke testing in TerminalChat
-- Paste these into the chat input to exercise query highlighting on the Sigma canvas.

-- Single node lookup (camera should zoom tight on one node)
MATCH (n:LogicNode {name: 'parse_file'}) RETURN n

-- Multiple nodes by kind (camera should frame all results)
MATCH (n:LogicNode {kind: 'function'}) RETURN n LIMIT 5

-- All classes
MATCH (n:LogicNode {kind: 'class'}) RETURN n

-- All modules
MATCH (n:Module) RETURN n

-- Functions in a specific file
MATCH (m:Module {module_path: 'app/main.py'})-[:DEFINES]->(f:LogicNode {kind: 'function'}) RETURN f

-- Call graph: who calls a specific function
MATCH (caller)-[:CALLS]->(target {name: 'parse_file'}) RETURN caller, target

-- Inheritance chain
MATCH (child)-[:INHERITS]->(parent) RETURN child, parent LIMIT 1

-- Functions that define variables
MATCH (f:LogicNode {kind: 'function'})-[:ASSIGNS]->(v:Variable) RETURN f, v LIMIT 10

-- Cross-file calls (functions calling into other modules)
MATCH (a:LogicNode)-[r:CALLS]->(b:LogicNode)
WHERE a.module_path <> b.module_path
RETURN a, b LIMIT 10

-- Nodes with high fan-out (many outgoing calls)
MATCH (n:LogicNode)-[r:CALLS]->()
WITH n, count(r) AS calls
WHERE calls > 3
RETURN n ORDER BY calls DESC LIMIT 10

-- Full neighbourhood of a node (good for Cmd+click testing)
MATCH (n {name: 'parse_file'})-[r]-(neighbor) RETURN n, neighbor LIMIT 20

-- Return just names (tests scalar string resolution)
MATCH (n:LogicNode {kind: 'function'}) RETURN n.name LIMIT 5

--List all variables in a function:
MATCH (fn:LogicNode)-[r]->(v:Variable)
WHERE fn.name CONTAINS 'create_json'
RETURN type(r) AS action, v.name, v.type_hint, v.is_parameter, v.origin_line
ORDER BY v.origin_line

--Trace a variables full lifecycle (assigns, reads, mutates, returns):
MATCH (fn:LogicNode)-[r]->(v:Variable)
RETURN type(r) AS action, fn.name AS by_function, v.origin_line
ORDER BY type(r) LIMIT 10

--Find all mutated variables in a function (the "danger" query):
MATCH (fn:LogicNode)-[:MUTATES]->(v:Variable)
WHERE fn.name CONTAINS 'your_function_name'
RETURN v.name, v.type_hint, v.origin_line

--Cross-function variable flow — which functions read a variable that another function assigns:
MATCH (writer:LogicNode)-[:ASSIGNS]->(v:Variable)<-[:READS]-(reader:LogicNode)
WHERE writer <> reader
RETURN writer.name AS writer, v.name AS variable, reader.name AS reader
LIMIT 10

--Find duplicate functions by AST hash:
MATCH (n:LogicNode)
WHERE n.status = 'active'
WITH n.ast_hash AS hash, collect(n) AS nodes
WHERE size(nodes) > 2
UNWIND nodes AS n
RETURN n

--Find duplicate functions by structural hash:
MATCH (n:LogicNode)
WHERE n.status = 'active'
WITH n.structural_hash AS hash, collect(n) AS nodes
WHERE size(nodes) > 2
UNWIND nodes AS n
RETURN n
