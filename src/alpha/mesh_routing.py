"""Satellite mesh routing — inter-satellite link topology and pathfinding.

Implements Dijkstra over dynamic ISL (inter-satellite link) graph.
Handles topology changes from orbital motion and link failures.
Pure math + data structures, zero external dependencies.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SatelliteNode:
    sat_id: int
    orbit: int
    plane: int
    phase: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    active: bool = True
    load: float = 0.0
    last_update: float = 0.0

    @property
    def position(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class ISLEdge:
    from_id: int
    to_id: int
    latency_ms: float
    capacity_gbps: float
    current_load: float = 0.0
    active: bool = True
    last_check: float = 0.0

    @property
    def available_capacity(self) -> float:
        return max(0, self.capacity_gbps - self.current_load)

    @property
    def utilization(self) -> float:
        if self.capacity_gbps <= 0:
            return 1.0
        return self.current_load / self.capacity_gbps


@dataclass
class Route:
    path: list[int]
    total_latency_ms: float
    total_hops: int
    min_capacity_gbps: float
    bottleneck_sat: int = -1

    @property
    def efficiency(self) -> float:
        if self.total_hops == 0:
            return 0.0
        return self.min_capacity_gbps / self.total_hops


class MeshTopology:
    def __init__(self):
        self._nodes: dict[int, SatelliteNode] = {}
        self._edges: dict[tuple[int, int], ISLEdge] = {}
        self._adjacency: dict[int, list[int]] = {}
        self._update_time: float = 0.0

    def add_satellite(self, node: SatelliteNode):
        self._nodes[node.sat_id] = node
        self._adjacency.setdefault(node.sat_id, [])

    def add_isl(self, edge: ISLEdge):
        self._edges[(edge.from_id, edge.to_id)] = edge
        self._edges[(edge.to_id, edge.from_id)] = ISLEdge(
            from_id=edge.to_id, to_id=edge.from_id,
            latency_ms=edge.latency_ms, capacity_gbps=edge.capacity_gbps,
            current_load=edge.current_load, active=edge.active,
        )
        self._adjacency.setdefault(edge.from_id, [])
        self._adjacency.setdefault(edge.to_id, [])
        if edge.to_id not in self._adjacency[edge.from_id]:
            self._adjacency[edge.from_id].append(edge.to_id)
        if edge.from_id not in self._adjacency[edge.to_id]:
            self._adjacency[edge.to_id].append(edge.from_id)

    def update_satellite(self, sat_id: int, x: float, y: float, z: float, load: float):
        node = self._nodes.get(sat_id)
        if node:
            node.x, node.y, node.z = x, y, z
            node.load = load
            node.last_update = time.time()
        self._update_time = time.time()

    def update_edge(self, from_id: int, to_id: int, latency_ms: float, load: float):
        key = (from_id, to_id)
        if key in self._edges:
            self._edges[key].latency_ms = latency_ms
            self._edges[key].current_load = load
            self._edges[key].last_check = time.time()

        rev = (to_id, from_id)
        if rev in self._edges:
            self._edges[rev].latency_ms = latency_ms
            self._edges[rev].current_load = load

    def get_edge(self, from_id: int, to_id: int) -> Optional[ISLEdge]:
        return self._edges.get((from_id, to_id))

    def find_route(
        self, src: int, dst: int, max_latency_ms: float = 100.0
    ) -> Optional[Route]:
        if src not in self._nodes or dst not in self._nodes:
            return None
        if src == dst:
            return Route(path=[src], total_latency_ms=0, total_hops=0, min_capacity_gbps=float("inf"))

        dist = {src: 0.0}
        capacity = {src: float("inf")}
        prev = {src: -1}
        visited = set()
        pq = [(0.0, src)]

        while pq:
            pq.sort()
            d, u = pq.pop(0)

            if u in visited:
                continue
            visited.add(u)

            if u == dst:
                break

            for v in self._adjacency.get(u, []):
                if v in visited:
                    continue

                edge = self._edges.get((u, v))
                if not edge or not edge.active:
                    continue
                if not self._nodes.get(v, SatelliteNode(0, 0, 0, 0)).active:
                    continue

                new_dist = d + edge.latency_ms
                if new_dist > max_latency_ms:
                    continue

                new_cap = min(capacity.get(u, float("inf")), edge.available_capacity)

                if v not in dist or new_dist < dist[v]:
                    dist[v] = new_dist
                    capacity[v] = new_cap
                    prev[v] = u
                    pq.append((new_dist, v))

        if dst not in prev:
            return None

        path = []
        node = dst
        while node != -1:
            path.append(node)
            node = prev.get(node, -1)
        path.reverse()

        bottleneck = min(
            self._edges.get((path[i], path[i + 1]), ISLEdge(0, 0, 0, 0)).available_capacity
            for i in range(len(path) - 1)
        ) if len(path) > 1 else float("inf")

        min_cap_sat = min(path, key=lambda s: self._nodes.get(s, SatelliteNode(0, 0, 0, 0)).load)

        return Route(
            path=path,
            total_latency_ms=dist.get(dst, 0),
            total_hops=len(path) - 1,
            min_capacity_gbps=bottleneck,
            bottleneck_sat=min_cap_sat,
        )

    def find_all_routes(
        self, src: int, dst: int, k: int = 3, max_latency_ms: float = 200.0
    ) -> list[Route]:
        """K-shortest paths via Yen's algorithm."""
        routes = []
        first = self.find_route(src, dst, max_latency_ms)
        if not first:
            return []
        routes.append(first)

        for _ in range(k - 1):
            for i in range(len(routes[-1].path) - 1):
                spur_node = routes[-1].path[i]
                root_path = routes[-1].path[:i + 1]

                removed_edges = []
                for route in routes:
                    if route.path[:i + 1] == root_path and len(route.path) > i + 1:
                        e = (route.path[i], route.path[i + 1])
                        if e in self._edges:
                            self._edges[e].active = False
                            removed_edges.append(e)

                for node_id in root_path[:-1]:
                    self._nodes[node_id].active = False

                spur_route = self.find_route(spur_node, dst, max_latency_ms)

                for e_from, e_to in removed_edges:
                    self._edges[(e_from, e_to)].active = True
                for node_id in root_path[:-1]:
                    self._nodes[node_id].active = True

                if spur_route:
                    total_path = root_path[:-1] + spur_route.path
                    total_lat = sum(
                        self._edges.get((total_path[j], total_path[j + 1]), ISLEdge(0, 0, 0, 0)).latency_ms
                        for j in range(len(total_path) - 1)
                    )
                    candidate = Route(
                        path=total_path,
                        total_latency_ms=total_lat,
                        total_hops=len(total_path) - 1,
                        min_capacity_gbps=spur_route.min_capacity_gbps,
                    )
                    if not any(r.path == candidate.path for r in routes):
                        routes.append(candidate)

            if len(routes) >= k:
                break

        routes.sort(key=lambda r: r.total_latency_ms)
        return routes[:k]

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges) // 2

    @property
    def average_degree(self) -> float:
        if not self._nodes:
            return 0.0
        total = sum(len(adj) for adj in self._adjacency.values())
        return total / len(self._nodes)
