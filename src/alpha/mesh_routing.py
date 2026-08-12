"""Deterministic local inter-satellite mesh routing.

The module models a bounded in-memory constellation graph.  It provides
validated link state, latency-constrained shortest paths, capacity-aware route
selection, and non-mutating k-route enumeration.  It does not model real laser
terminals or claim production constellation scale.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass
from typing import Optional


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _sat_id(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


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

    def __post_init__(self) -> None:
        self.sat_id = _sat_id("sat_id", self.sat_id)
        if isinstance(self.orbit, bool) or not isinstance(self.orbit, int):
            raise ValueError("orbit must be an integer")
        if isinstance(self.plane, bool) or not isinstance(self.plane, int):
            raise ValueError("plane must be an integer")
        self.phase = _finite("phase", self.phase)
        self.x = _finite("x", self.x)
        self.y = _finite("y", self.y)
        self.z = _finite("z", self.z)
        self.load = _finite("load", self.load)
        if self.load < 0.0:
            raise ValueError("load must be >= 0")
        self.last_update = _finite("last_update", self.last_update)

    @property
    def position(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


@dataclass
class ISLEdge:
    from_id: int
    to_id: int
    latency_ms: float
    capacity_gbps: float
    current_load: float = 0.0
    active: bool = True
    last_check: float = 0.0

    def __post_init__(self) -> None:
        self.from_id = _sat_id("from_id", self.from_id)
        self.to_id = _sat_id("to_id", self.to_id)
        if self.from_id == self.to_id:
            raise ValueError("an ISL must connect two distinct satellites")
        self.latency_ms = _finite("latency_ms", self.latency_ms)
        self.capacity_gbps = _finite("capacity_gbps", self.capacity_gbps)
        self.current_load = _finite("current_load", self.current_load)
        self.last_check = _finite("last_check", self.last_check)
        if self.latency_ms < 0.0:
            raise ValueError("latency_ms must be >= 0")
        if self.capacity_gbps <= 0.0:
            raise ValueError("capacity_gbps must be > 0")
        if self.current_load < 0.0:
            raise ValueError("current_load must be >= 0")

    @property
    def available_capacity(self) -> float:
        return max(0.0, self.capacity_gbps - self.current_load)

    @property
    def utilization(self) -> float:
        return self.current_load / self.capacity_gbps


@dataclass(frozen=True)
class Route:
    path: list[int]
    total_latency_ms: float
    total_hops: int
    min_capacity_gbps: float
    bottleneck_sat: int = -1

    @property
    def efficiency(self) -> float:
        if self.total_hops == 0:
            return float("inf") if math.isinf(self.min_capacity_gbps) else self.min_capacity_gbps
        return self.min_capacity_gbps / self.total_hops


class MeshTopology:
    """Validated undirected local mesh graph with deterministic routing."""

    def __init__(self):
        self._nodes: dict[int, SatelliteNode] = {}
        self._edges: dict[tuple[int, int], ISLEdge] = {}
        self._adjacency: dict[int, set[int]] = {}
        self._update_time: float = 0.0

    def add_satellite(self, node: SatelliteNode):
        if node.sat_id in self._nodes:
            raise ValueError(f"duplicate satellite id: {node.sat_id}")
        self._nodes[node.sat_id] = node
        self._adjacency[node.sat_id] = set()

    def add_isl(self, edge: ISLEdge):
        if edge.from_id not in self._nodes or edge.to_id not in self._nodes:
            raise KeyError("both ISL endpoints must be registered satellites")
        if (edge.from_id, edge.to_id) in self._edges:
            raise ValueError(f"duplicate ISL: {edge.from_id}<->{edge.to_id}")
        now = edge.last_check or time.time()
        forward = ISLEdge(
            edge.from_id, edge.to_id, edge.latency_ms, edge.capacity_gbps,
            edge.current_load, edge.active, now,
        )
        reverse = ISLEdge(
            edge.to_id, edge.from_id, edge.latency_ms, edge.capacity_gbps,
            edge.current_load, edge.active, now,
        )
        self._edges[(forward.from_id, forward.to_id)] = forward
        self._edges[(reverse.from_id, reverse.to_id)] = reverse
        self._adjacency[edge.from_id].add(edge.to_id)
        self._adjacency[edge.to_id].add(edge.from_id)
        self._update_time = now

    def update_satellite(self, sat_id: int, x: float, y: float, z: float, load: float):
        node = self._nodes.get(sat_id)
        if node is None:
            raise KeyError(f"unknown satellite: {sat_id}")
        x, y, z, load = _finite("x", x), _finite("y", y), _finite("z", z), _finite("load", load)
        if load < 0.0:
            raise ValueError("load must be >= 0")
        node.x, node.y, node.z, node.load = x, y, z, load
        node.last_update = time.time()
        self._update_time = node.last_update

    def set_satellite_active(self, sat_id: int, active: bool) -> None:
        if sat_id not in self._nodes:
            raise KeyError(f"unknown satellite: {sat_id}")
        self._nodes[sat_id].active = bool(active)
        self._update_time = time.time()

    def update_edge(self, from_id: int, to_id: int, latency_ms: float, load: float):
        latency_ms, load = _finite("latency_ms", latency_ms), _finite("load", load)
        if latency_ms < 0.0 or load < 0.0:
            raise ValueError("latency and load must be >= 0")
        if (from_id, to_id) not in self._edges or (to_id, from_id) not in self._edges:
            raise KeyError(f"unknown ISL: {from_id}<->{to_id}")
        now = time.time()
        for key in ((from_id, to_id), (to_id, from_id)):
            edge = self._edges[key]
            edge.latency_ms = latency_ms
            edge.current_load = load
            edge.last_check = now
        self._update_time = now

    def set_isl_active(self, from_id: int, to_id: int, active: bool) -> None:
        if (from_id, to_id) not in self._edges or (to_id, from_id) not in self._edges:
            raise KeyError(f"unknown ISL: {from_id}<->{to_id}")
        for key in ((from_id, to_id), (to_id, from_id)):
            self._edges[key].active = bool(active)
            self._edges[key].last_check = time.time()
        self._update_time = time.time()

    def get_edge(self, from_id: int, to_id: int) -> Optional[ISLEdge]:
        return self._edges.get((from_id, to_id))

    def _edge_usable(self, u: int, v: int) -> bool:
        edge = self._edges.get((u, v))
        return bool(
            edge
            and edge.active
            and edge.available_capacity > 0.0
            and self._nodes[u].active
            and self._nodes[v].active
        )

    def _route_from_path(self, path: list[int]) -> Route:
        if not path:
            raise ValueError("path cannot be empty")
        if len(path) == 1:
            return Route(path=list(path), total_latency_ms=0.0, total_hops=0, min_capacity_gbps=float("inf"), bottleneck_sat=path[0])
        edges = [self._edges[(path[i], path[i + 1])] for i in range(len(path) - 1)]
        latency = sum(edge.latency_ms for edge in edges)
        capacity = min(edge.available_capacity for edge in edges)
        bottleneck_sat = max(path, key=lambda sat_id: (self._nodes[sat_id].load, -sat_id))
        return Route(list(path), latency, len(path) - 1, capacity, bottleneck_sat)

    def find_route(self, src: int, dst: int, max_latency_ms: float = 100.0) -> Optional[Route]:
        max_latency_ms = _finite("max_latency_ms", max_latency_ms)
        if max_latency_ms < 0.0:
            raise ValueError("max_latency_ms must be >= 0")
        if src not in self._nodes or dst not in self._nodes:
            return None
        if not self._nodes[src].active or not self._nodes[dst].active:
            return None
        if src == dst:
            return self._route_from_path([src])

        dist = {src: 0.0}
        prev: dict[int, int] = {}
        pq: list[tuple[float, int, int]] = [(0.0, 0, src)]

        while pq:
            current_dist, hops, u = heapq.heappop(pq)
            if current_dist != dist.get(u):
                continue
            if u == dst:
                break
            for v in sorted(self._adjacency.get(u, set())):
                if not self._edge_usable(u, v):
                    continue
                edge = self._edges[(u, v)]
                candidate = current_dist + edge.latency_ms
                if candidate > max_latency_ms:
                    continue
                if candidate < dist.get(v, float("inf")):
                    dist[v] = candidate
                    prev[v] = u
                    heapq.heappush(pq, (candidate, hops + 1, v))

        if dst not in dist:
            return None
        path = [dst]
        while path[-1] != src:
            path.append(prev[path[-1]])
        path.reverse()
        return self._route_from_path(path)

    def find_all_routes(self, src: int, dst: int, k: int = 3, max_latency_ms: float = 200.0) -> list[Route]:
        """Return up to ``k`` lowest-latency simple paths without mutating topology.

        This bounded local enumerator intentionally favors correctness and state
        isolation over claims of hyperscale routing.
        """
        if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")
        max_latency_ms = _finite("max_latency_ms", max_latency_ms)
        if max_latency_ms < 0.0:
            raise ValueError("max_latency_ms must be >= 0")
        if src not in self._nodes or dst not in self._nodes:
            return []
        if not self._nodes[src].active or not self._nodes[dst].active:
            return []
        if src == dst:
            return [self._route_from_path([src])]

        queue: list[tuple[float, tuple[int, ...]]] = [(0.0, (src,))]
        routes: list[Route] = []
        expansions = 0
        max_expansions = max(10_000, len(self._nodes) * len(self._nodes) * 4)

        while queue and len(routes) < k and expansions < max_expansions:
            latency, path_tuple = heapq.heappop(queue)
            path = list(path_tuple)
            u = path[-1]
            if u == dst:
                routes.append(self._route_from_path(path))
                continue
            expansions += 1
            for v in sorted(self._adjacency.get(u, set())):
                if v in path or not self._edge_usable(u, v):
                    continue
                candidate = latency + self._edges[(u, v)].latency_ms
                if candidate <= max_latency_ms:
                    heapq.heappush(queue, (candidate, tuple(path + [v])))

        return routes

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
        return sum(len(adj) for adj in self._adjacency.values()) / len(self._nodes)

    @property
    def snapshot(self) -> dict:
        return {
            "nodes": self.node_count,
            "active_nodes": sum(node.active for node in self._nodes.values()),
            "links": self.edge_count,
            "active_links": sum(1 for (u, v), edge in self._edges.items() if u < v and edge.active and edge.available_capacity > 0.0),
            "updated_at": self._update_time,
            "operational_authority": False,
        }
