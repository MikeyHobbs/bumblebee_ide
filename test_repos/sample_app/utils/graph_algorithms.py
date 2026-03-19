"""Graph and tree traversal algorithms."""

from __future__ import annotations

import heapq
from collections import deque


def bfs(start, goal_id: int) -> dict:
    """Breadth-first search from a start node to a node with the given goal_id.

    Args:
        start: A graph node with .id, .edges (list of neighbor nodes), and .visited attributes.
        goal_id: The .id value of the target node.

    Returns:
        A dict with keys "path" (list of node ids), "cost" (int step count),
        and "visited_count" (number of nodes explored).
    """
    queue: deque = deque()
    queue.append((start, [start.id]))
    visited: set = set()
    visited.add(start.id)
    start.visited = True
    visited_count = 1

    while len(queue) > 0:
        current, path = queue.popleft()

        if current.id == goal_id:
            return {
                "path": path,
                "cost": len(path) - 1,
                "visited_count": visited_count,
            }

        for neighbor in current.edges:
            if neighbor.id not in visited:
                visited.add(neighbor.id)
                neighbor.visited = True
                visited_count += 1
                new_path = path + [neighbor.id]
                queue.append((neighbor, new_path))

    return {"path": [], "cost": -1, "visited_count": visited_count}


def dfs(start, max_depth: int) -> dict:
    """Depth-first search from a start node up to a maximum depth.

    Args:
        start: A graph node with .id, .edges, and .visited attributes.
        max_depth: Maximum depth to traverse.

    Returns:
        A dict with keys "path" (list of visited node ids in DFS order),
        "cost" (deepest depth reached), and "visited_count".
    """
    stack: list = []
    stack.append((start, 0))
    visited: set = set()
    path: list = []
    deepest = 0

    while len(stack) > 0:
        current, depth = stack.pop()

        if current.id in visited:
            continue

        visited.add(current.id)
        current.visited = True
        path.append(current.id)

        if depth > deepest:
            deepest = depth

        if depth < max_depth:
            for neighbor in current.edges:
                if neighbor.id not in visited:
                    stack.append((neighbor, depth + 1))

    return {"path": path, "cost": deepest, "visited_count": len(visited)}


def inorder_traversal(node) -> list:
    """Perform an inorder traversal of a binary tree.

    Args:
        node: A binary tree node with .left, .right, and .value attributes.
            .left and .right may be None for leaf nodes.

    Returns:
        A list of values in inorder sequence.
    """
    result: list = []
    if node is None:
        return result
    if node.left is not None:
        result.extend(inorder_traversal(node.left))
    result.append(node.value)
    if node.right is not None:
        result.extend(inorder_traversal(node.right))
    return result


def tree_depth(node) -> int:
    """Compute the depth (height) of a binary tree.

    Args:
        node: A binary tree node with .left, .right, and .value attributes.

    Returns:
        The height of the tree (0 for a single node, -1 for None).
    """
    if node is None:
        return -1
    left_depth = tree_depth(node.left)
    right_depth = tree_depth(node.right)
    if left_depth > right_depth:
        return left_depth + 1
    return right_depth + 1


def level_order(root) -> list:
    """Perform a level-order (breadth-first) traversal of a binary tree.

    Args:
        root: A binary tree node with .left, .right, and .value attributes.

    Returns:
        A list of lists, where each inner list contains the values at that level.
    """
    if root is None:
        return []

    levels: list = []
    queue: deque = deque()
    queue.append(root)

    while len(queue) > 0:
        level_size = len(queue)
        current_level: list = []

        for _ in range(level_size):
            node = queue.popleft()
            current_level.append(node.value)

            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

        levels.append(current_level)

    return levels


def find_ancestors(node) -> list:
    """Collect all ancestors of a node by following parent pointers.

    Args:
        node: An n-ary tree node with .parent and .value attributes.
            .parent is None for the root node.

    Returns:
        A list of ancestor values from the immediate parent up to the root.
    """
    ancestors: list = []
    current = node.parent
    while current is not None:
        ancestors.append(current.value)
        current = current.parent
    return ancestors


def collect_leaves(node) -> list:
    """Collect all leaf node values in an n-ary tree.

    Args:
        node: An n-ary tree node with .children (list) and .value attributes.

    Returns:
        A list of values from all leaf nodes (those with no children).
    """
    leaves: list = []
    if node.children is None or len(node.children) == 0:
        leaves.append(node.value)
        return leaves
    for child in node.children:
        leaves.extend(collect_leaves(child))
    return leaves


def dijkstra(start, edges: list, goal_id: int) -> dict:
    """Find the shortest weighted path using Dijkstra's algorithm.

    Args:
        start: A node object with .id attribute.
        edges: A list of edge dicts, each with "source" (int), "target" (int),
            and "weight" (float) keys.
        goal_id: The target node id.

    Returns:
        A dict with "path", "cost", and "visited_count".
    """
    adjacency: dict = {}
    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        weight = edge["weight"]
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append((tgt, weight))
        if tgt not in adjacency:
            adjacency[tgt] = []
        adjacency[tgt].append((src, weight))

    dist: dict = {start.id: 0.0}
    prev: dict = {}
    visited: set = set()
    heap: list = [(0.0, start.id)]

    while len(heap) > 0:
        current_dist, current_id = heapq.heappop(heap)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id == goal_id:
            path: list = []
            node_id = goal_id
            while node_id is not None:
                path.append(node_id)
                node_id = prev.get(node_id)
            path.reverse()
            return {
                "path": path,
                "cost": current_dist,
                "visited_count": len(visited),
            }

        if current_id in adjacency:
            for neighbor_id, weight in adjacency[current_id]:
                if neighbor_id not in visited:
                    new_dist = current_dist + weight
                    if neighbor_id not in dist or new_dist < dist[neighbor_id]:
                        dist[neighbor_id] = new_dist
                        prev[neighbor_id] = current_id
                        heapq.heappush(heap, (new_dist, neighbor_id))

    return {"path": [], "cost": -1.0, "visited_count": len(visited)}


def unweighted_shortest_path(start, edges: list, goal_id: int) -> dict:
    """Find the shortest unweighted path using BFS over an edge list.

    Args:
        start: A node object with .id attribute.
        edges: A list of edge dicts with "source" and "target" keys.
        goal_id: The target node id.

    Returns:
        A dict with "path", "cost", and "visited_count".
    """
    adjacency: dict = {}
    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append(tgt)
        if tgt not in adjacency:
            adjacency[tgt] = []
        adjacency[tgt].append(src)

    visited: set = {start.id}
    queue: deque = deque()
    queue.append((start.id, [start.id]))
    visited_count = 1

    while len(queue) > 0:
        current_id, path = queue.popleft()

        if current_id == goal_id:
            return {
                "path": path,
                "cost": len(path) - 1,
                "visited_count": visited_count,
            }

        if current_id in adjacency:
            for neighbor_id in adjacency[current_id]:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    visited_count += 1
                    queue.append((neighbor_id, path + [neighbor_id]))

    return {"path": [], "cost": -1, "visited_count": visited_count}


def find_lowest_latency_path(start, connections: list, goal_id: int) -> dict:
    """Find the path with lowest total latency using Dijkstra over connection dicts.

    Args:
        start: A node object with .id attribute.
        connections: A list of connection dicts with "from" (int), "to" (int),
            "latency" (float), and "bandwidth" (float) keys.
        goal_id: The target node id.

    Returns:
        A dict with "path", "cost" (total latency), and "visited_count".
    """
    adjacency: dict = {}
    bandwidth_map: dict = {}
    for connection in connections:
        src = connection["from"]
        tgt = connection["to"]
        latency = connection["latency"]
        bw = connection["bandwidth"]
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append((tgt, latency))
        bandwidth_map[(src, tgt)] = bw
        if tgt not in adjacency:
            adjacency[tgt] = []
        adjacency[tgt].append((src, latency))
        bandwidth_map[(tgt, src)] = bw

    dist: dict = {start.id: 0.0}
    prev: dict = {}
    visited: set = set()
    heap: list = [(0.0, start.id)]

    while len(heap) > 0:
        current_latency, current_id = heapq.heappop(heap)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id == goal_id:
            path: list = []
            node_id = goal_id
            while node_id is not None:
                path.append(node_id)
                node_id = prev.get(node_id)
            path.reverse()
            return {
                "path": path,
                "cost": current_latency,
                "visited_count": len(visited),
            }

        if current_id in adjacency:
            for neighbor_id, latency in adjacency[current_id]:
                if neighbor_id not in visited:
                    new_latency = current_latency + latency
                    if neighbor_id not in dist or new_latency < dist[neighbor_id]:
                        dist[neighbor_id] = new_latency
                        prev[neighbor_id] = current_id
                        heapq.heappush(heap, (new_latency, neighbor_id))

    return {"path": [], "cost": -1.0, "visited_count": len(visited)}


def topological_sort(nodes: list) -> list:
    """Perform a topological sort on a directed acyclic graph using Kahn's algorithm.

    Args:
        nodes: A list of graph nodes with .id, .edges (outgoing neighbor nodes),
            and .visited attributes.

    Returns:
        A list of node ids in topological order. Returns an empty list if a cycle is detected.
    """
    in_degree: dict = {}
    adjacency: dict = {}

    for node in nodes:
        if node.id not in in_degree:
            in_degree[node.id] = 0
        if node.id not in adjacency:
            adjacency[node.id] = []
        for neighbor in node.edges:
            adjacency[node.id].append(neighbor.id)
            if neighbor.id not in in_degree:
                in_degree[neighbor.id] = 0
            in_degree[neighbor.id] += 1

    queue: deque = deque()
    for nid, deg in in_degree.items():
        if deg == 0:
            queue.append(nid)

    sorted_ids: list = []
    while len(queue) > 0:
        current_id = queue.popleft()
        sorted_ids.append(current_id)

        if current_id in adjacency:
            for neighbor_id in adjacency[current_id]:
                in_degree[neighbor_id] -= 1
                if in_degree[neighbor_id] == 0:
                    queue.append(neighbor_id)

    if len(sorted_ids) != len(in_degree):
        return []

    for node in nodes:
        node.visited = True

    return sorted_ids


def connected_components(nodes: list) -> list:
    """Find all connected components in an undirected graph.

    Args:
        nodes: A list of graph nodes with .id, .edges, and .visited attributes.

    Returns:
        A list of lists, where each inner list contains the node ids
        of one connected component.
    """
    visited: set = set()
    components: list = []

    node_map: dict = {}
    for node in nodes:
        node_map[node.id] = node

    for node in nodes:
        if node.id not in visited:
            component: list = []
            stack: list = [node]

            while len(stack) > 0:
                current = stack.pop()
                if current.id in visited:
                    continue
                visited.add(current.id)
                current.visited = True
                component.append(current.id)

                for neighbor in current.edges:
                    if neighbor.id not in visited:
                        stack.append(neighbor)

            components.append(component)

    return components
