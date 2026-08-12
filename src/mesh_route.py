#!/usr/bin/env python3
"""Small weighted-graph Dijkstra compatibility surface.

For constellation-aware routing use ``alpha.mesh_routing.MeshTopology``.  This
module remains a compact generic shortest-path helper for callers that already
import ``mesh_route.shortest_path``.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Mapping


def shortest_path(graph: dict[str, dict[str, float]], src: str, dst: str) -> dict:
    """Return the minimum-cost path in a non-negative weighted directed graph."""
    if not isinstance(graph, Mapping):
        raise TypeError("graph must be a mapping")
    if not isinstance(src, str) or not src or not isinstance(dst, str) or not dst:
        raise ValueError("src and dst must be non-empty strings")

    normalized: dict[str, dict[str, float]] = {}
    vertices = set(graph)
    for node, neighbors in graph.items():
        if not isinstance(node, str) or not node:
            raise ValueError("graph node ids must be non-empty strings")
        if not isinstance(neighbors, Mapping):
            raise TypeError(f"neighbors for {node!r} must be a mapping")
        normalized[node] = {}
        for neighbor, raw_cost in neighbors.items():
            if not isinstance(neighbor, str) or not neighbor:
                raise ValueError("neighbor ids must be non-empty strings")
            if isinstance(raw_cost, bool) or not isinstance(raw_cost, (int, float)):
                raise TypeError("edge costs must be numeric")
            cost = float(raw_cost)
            if not math.isfinite(cost) or cost < 0.0:
                raise ValueError("Dijkstra edge costs must be finite and non-negative")
            normalized[node][neighbor] = cost
            vertices.add(neighbor)

    if src not in vertices or dst not in vertices:
        return {"ok": False, "path": [], "cost": None}
    if src == dst:
        return {"ok": True, "path": [src], "cost": 0.0}

    dist = {src: 0.0}
    previous: dict[str, str] = {}
    queue = [(0.0, src)]
    while queue:
        current, node = heapq.heappop(queue)
        if current != dist.get(node):
            continue
        if node == dst:
            break
        for neighbor, cost in sorted(normalized.get(node, {}).items()):
            candidate = current + cost
            if candidate < dist.get(neighbor, float("inf")):
                dist[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))

    if dst not in dist:
        return {"ok": False, "path": [], "cost": None}
    path = [dst]
    while path[-1] != src:
        path.append(previous[path[-1]])
    path.reverse()
    return {"ok": True, "path": path, "cost": round(dist[dst], 4)}


if __name__ == "__main__":
    demo = {"A": {"B": 1, "C": 4}, "B": {"C": 1, "D": 3}, "C": {"D": 1}, "D": {}}
    print(shortest_path(demo, "A", "D"))
