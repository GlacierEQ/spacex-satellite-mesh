"""Deterministic delay-tolerant routing over scheduled link windows.

The temporal graph represents future link availability supplied by local
trajectories.  Routing computes earliest-arrival paths that may wait at
intermediate nodes until a later link opens.  The model is bounded and local;
it does not guarantee delivery or claim operational constellation ephemerides.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Optional

LIGHT_SPEED_M_S = 299_792_458.0


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class TimedEdge:
    from_id: int
    to_id: int
    available_from_s: float
    available_until_s: float
    latency_ms: float
    capacity_gbps: float

    def __post_init__(self) -> None:
        if isinstance(self.from_id, bool) or not isinstance(self.from_id, int) or self.from_id < 0:
            raise ValueError("from_id must be a non-negative integer")
        if isinstance(self.to_id, bool) or not isinstance(self.to_id, int) or self.to_id < 0 or self.to_id == self.from_id:
            raise ValueError("to_id must be a distinct non-negative integer")
        start = _finite("available_from_s", self.available_from_s)
        end = _finite("available_until_s", self.available_until_s)
        latency = _finite("latency_ms", self.latency_ms)
        capacity = _finite("capacity_gbps", self.capacity_gbps)
        if start < 0.0 or end < start:
            raise ValueError("invalid availability window")
        if latency < 0.0 or capacity <= 0.0:
            raise ValueError("latency must be >= 0 and capacity > 0")


@dataclass(frozen=True)
class TimedRoute:
    path: list[int]
    departure_time_s: float
    arrival_time_s: float
    total_latency_ms: float
    wait_time_s: float
    hops: int

    @property
    def delivery_time_s(self) -> float:
        return self.arrival_time_s - self.departure_time_s


class TemporalGraph:
    def __init__(self, time_resolution_s: float = 60.0):
        self.time_resolution = _finite("time_resolution_s", time_resolution_s)
        if self.time_resolution <= 0.0:
            raise ValueError("time_resolution_s must be > 0")
        self._edges: dict[tuple[int, int], list[TimedEdge]] = {}
        self._satellite_positions: dict[int, list[tuple[float, tuple[float, float, float]]]] = {}

    def add_satellite_trajectory(self, sat_id: int, positions: list[tuple[float, tuple[float, float, float]]]):
        if isinstance(sat_id, bool) or not isinstance(sat_id, int) or sat_id < 0:
            raise ValueError("sat_id must be a non-negative integer")
        if not positions:
            raise ValueError("trajectory cannot be empty")
        normalized: list[tuple[float, tuple[float, float, float]]] = []
        previous_time = -1.0
        for timestamp, position in positions:
            timestamp = _finite("trajectory time", timestamp)
            if timestamp < 0.0 or timestamp <= previous_time:
                raise ValueError("trajectory times must be strictly increasing and >= 0")
            if len(position) != 3:
                raise ValueError("trajectory positions must have three coordinates")
            coords = tuple(_finite(f"position[{index}]", value) for index, value in enumerate(position))
            normalized.append((timestamp, coords))
            previous_time = timestamp
        self._satellite_positions[sat_id] = normalized

    def add_link_window(self, edge: TimedEdge, *, bidirectional: bool = True) -> None:
        self._edges.setdefault((edge.from_id, edge.to_id), []).append(edge)
        self._edges[(edge.from_id, edge.to_id)].sort(key=lambda item: (item.available_from_s, item.available_until_s))
        if bidirectional:
            reverse = TimedEdge(
                edge.to_id,
                edge.from_id,
                edge.available_from_s,
                edge.available_until_s,
                edge.latency_ms,
                edge.capacity_gbps,
            )
            self._edges.setdefault((reverse.from_id, reverse.to_id), []).append(reverse)
            self._edges[(reverse.from_id, reverse.to_id)].sort(key=lambda item: (item.available_from_s, item.available_until_s))

    def compute_link_windows(
        self,
        sat_a: int,
        sat_b: int,
        max_range_m: float = 5_000_000.0,
        time_span_s: float = 3600.0,
        time_step_s: float = 10.0,
        capacity_gbps: float = 100.0,
    ) -> list[TimedEdge]:
        max_range_m = _finite("max_range_m", max_range_m)
        time_span_s = _finite("time_span_s", time_span_s)
        time_step_s = _finite("time_step_s", time_step_s)
        capacity_gbps = _finite("capacity_gbps", capacity_gbps)
        if max_range_m <= 0.0 or time_span_s < 0.0 or time_step_s <= 0.0 or capacity_gbps <= 0.0:
            raise ValueError("range, step and capacity must be positive; time span must be non-negative")
        if sat_a not in self._satellite_positions or sat_b not in self._satellite_positions:
            return []

        windows: list[TimedEdge] = []
        window_start: float | None = None
        last_visible_time: float | None = None
        latencies: list[float] = []
        t = 0.0
        epsilon = time_step_s * 1e-9

        while t <= time_span_s + epsilon:
            pos_a = self._interpolate_position(sat_a, t)
            pos_b = self._interpolate_position(sat_b, t)
            visible = False
            latency_ms = 0.0
            if pos_a is not None and pos_b is not None:
                distance = math.dist(pos_a, pos_b)
                visible = distance <= max_range_m
                latency_ms = distance / LIGHT_SPEED_M_S * 1000.0

            if visible:
                if window_start is None:
                    window_start = t
                    latencies = []
                last_visible_time = t
                latencies.append(latency_ms)
            elif window_start is not None and last_visible_time is not None:
                windows.append(TimedEdge(
                    sat_a,
                    sat_b,
                    window_start,
                    last_visible_time,
                    max(latencies),
                    capacity_gbps,
                ))
                window_start = None
                last_visible_time = None
                latencies = []
            t += time_step_s

        if window_start is not None and last_visible_time is not None:
            windows.append(TimedEdge(
                sat_a,
                sat_b,
                window_start,
                last_visible_time,
                max(latencies),
                capacity_gbps,
            ))
        return windows

    def _interpolate_position(self, sat_id: int, time_s: float) -> Optional[tuple[float, float, float]]:
        time_s = _finite("time_s", time_s)
        trajectory = self._satellite_positions.get(sat_id)
        if not trajectory or time_s < trajectory[0][0] or time_s > trajectory[-1][0]:
            return None
        if time_s == trajectory[-1][0]:
            return trajectory[-1][1]
        for index in range(len(trajectory) - 1):
            t0, pos0 = trajectory[index]
            t1, pos1 = trajectory[index + 1]
            if t0 <= time_s <= t1:
                fraction = (time_s - t0) / (t1 - t0)
                return tuple(pos0[axis] + fraction * (pos1[axis] - pos0[axis]) for axis in range(3))
        return None

    @property
    def link_window_count(self) -> int:
        return sum(len(edges) for edges in self._edges.values()) // 2


class TimeExpandedRouter:
    """Earliest-arrival routing across scheduled link windows."""

    def __init__(self, graph: TemporalGraph):
        self.graph = graph

    def _search(
        self,
        src: int,
        dst: int,
        departure_time_s: float,
        max_time_s: float,
        max_hops: int,
        k: int,
    ) -> list[TimedRoute]:
        departure_time_s = _finite("departure_time_s", departure_time_s)
        max_time_s = _finite("max_time_s", max_time_s)
        if departure_time_s < 0.0 or max_time_s < 0.0:
            raise ValueError("departure_time_s and max_time_s must be >= 0")
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or max_hops < 0:
            raise ValueError("max_hops must be a non-negative integer")
        if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")
        if src == dst:
            return [TimedRoute([src], departure_time_s, departure_time_s, 0.0, 0.0, 0)]

        horizon = departure_time_s + max_time_s
        queue: list[tuple[float, float, int, tuple[int, ...], float]] = [
            (departure_time_s, 0.0, 0, (src,), 0.0)
        ]
        results: list[TimedRoute] = []
        best: dict[tuple[int, int, tuple[int, ...]], float] = {}

        while queue and len(results) < k:
            current_time, wait_time, hops, path_tuple, propagation_ms = heapq.heappop(queue)
            node = path_tuple[-1]
            if node == dst:
                results.append(TimedRoute(
                    list(path_tuple),
                    departure_time_s,
                    current_time,
                    propagation_ms,
                    wait_time,
                    hops,
                ))
                continue
            if hops >= max_hops:
                continue

            outgoing = sorted(
                ((to_id, edges) for (from_id, to_id), edges in self.graph._edges.items() if from_id == node),
                key=lambda item: item[0],
            )
            for to_id, edges in outgoing:
                if to_id in path_tuple:
                    continue
                for edge in edges:
                    if current_time > edge.available_until_s:
                        continue
                    depart = max(current_time, edge.available_from_s)
                    if depart > edge.available_until_s:
                        continue
                    arrival = depart + edge.latency_ms / 1000.0
                    if arrival > horizon:
                        continue
                    new_path = path_tuple + (to_id,)
                    new_wait = wait_time + max(0.0, depart - current_time)
                    new_propagation = propagation_ms + edge.latency_ms
                    key = (to_id, hops + 1, new_path)
                    if arrival < best.get(key, float("inf")):
                        best[key] = arrival
                        heapq.heappush(queue, (arrival, new_wait, hops + 1, new_path, new_propagation))
        return results

    def find_timed_route(
        self,
        src: int,
        dst: int,
        departure_time_s: float = 0.0,
        max_time_s: float = 3600.0,
        max_hops: int = 10,
    ) -> Optional[TimedRoute]:
        routes = self._search(src, dst, departure_time_s, max_time_s, max_hops, 1)
        return routes[0] if routes else None

    def find_all_timed_routes(
        self,
        src: int,
        dst: int,
        k: int = 3,
        departure_time_s: float = 0.0,
        max_time_s: float = 7200.0,
        max_hops: int = 10,
    ) -> list[TimedRoute]:
        return self._search(src, dst, departure_time_s, max_time_s, max_hops, k)


class DelayTolerantNetwork:
    """Local delay-tolerant constellation routing simulation."""

    def __init__(self):
        self.graph = TemporalGraph()
        self.router = TimeExpandedRouter(self.graph)
        self._routing_log: list[dict] = []

    def setup_constellation(
        self,
        satellite_trajectories: dict[int, list[tuple[float, tuple[float, float, float]]]],
        isl_range_m: float = 5_000_000.0,
        time_step_s: float = 10.0,
    ):
        if len(satellite_trajectories) < 2:
            raise ValueError("at least two satellite trajectories are required")
        for sat_id, trajectory in satellite_trajectories.items():
            self.graph.add_satellite_trajectory(sat_id, trajectory)

        ids = sorted(satellite_trajectories)
        maximum_time = min(trajectory[-1][0] for trajectory in self.graph._satellite_positions.values())
        for index, sat_a in enumerate(ids):
            for sat_b in ids[index + 1:]:
                for window in self.graph.compute_link_windows(
                    sat_a,
                    sat_b,
                    isl_range_m,
                    maximum_time,
                    time_step_s,
                ):
                    self.graph.add_link_window(window, bidirectional=True)

    def route_message(self, src: int, dst: int, departure_time_s: float = 0.0, max_time_s: float = 3600.0) -> dict:
        route = self.router.find_timed_route(src, dst, departure_time_s, max_time_s)
        if route is None:
            return {
                "deliverable": False,
                "reason": "no path found within modeled availability horizon",
                "src": src,
                "dst": dst,
                "operational_authority": False,
            }
        record = {
            "src": src,
            "dst": dst,
            "departure_time_s": departure_time_s,
            "arrival_time_s": route.arrival_time_s,
            "delivery_time_s": route.delivery_time_s,
            "hops": route.hops,
            "latency_ms": route.total_latency_ms,
            "wait_time_s": route.wait_time_s,
        }
        self._routing_log.append(record)
        return {
            "deliverable": True,
            "path": route.path,
            **record,
            "path_description": " -> ".join(str(node) for node in route.path),
            "operational_authority": False,
        }

    @property
    def network_stats(self) -> dict:
        if not self._routing_log:
            return {
                "total_routes": 0,
                "satellites": len(self.graph._satellite_positions),
                "link_windows": self.graph.link_window_count,
                "operational_authority": False,
            }
        recent = self._routing_log[-20:]
        return {
            "total_routes": len(self._routing_log),
            "avg_hops": sum(record["hops"] for record in recent) / len(recent),
            "avg_latency_ms": sum(record["latency_ms"] for record in recent) / len(recent),
            "avg_delivery_time_s": sum(record["delivery_time_s"] for record in recent) / len(recent),
            "satellites": len(self.graph._satellite_positions),
            "link_windows": self.graph.link_window_count,
            "operational_authority": False,
        }
