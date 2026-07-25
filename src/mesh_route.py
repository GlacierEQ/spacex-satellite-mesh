#!/usr/bin/env python3
"""Satellite mesh routing — multi-hop shortest path on link graph (portfolio)."""
from __future__ import annotations
import heapq


def shortest_path(graph: dict[str, dict[str, float]], src: str, dst: str) -> dict:
    """Dijkstra; graph[u][v] = cost."""
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w in graph.get(u, {}).items():
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return {"ok": False, "path": [], "cost": None}
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    return {"ok": True, "path": path, "cost": round(dist[dst], 4)}

if __name__ == "__main__":
    g = {"A": {"B": 1, "C": 4}, "B": {"C": 1, "D": 3}, "C": {"D": 1}, "D": {}}
    print(shortest_path(g, "A", "D"))
