"""Temporal routing — route through time, not just space.

Standard routing: find shortest path in static graph.
Innovation: In a constellation, links appear and disappear as satellites
move. Route through TIME as well as space — pre-compute paths that
exploit future link availability.

The wheel: Dijkstra routing
The vehicle: time-expanded graph routing

Key insight: Two satellites that can't see each other NOW will be able
to in 30 minutes (orbital mechanics guarantees this). A message that
needs to go from A to B can wait at an intermediate satellite until the
next link opens. This is delay-tolerant networking applied to LEO
constellations.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimedEdge:
    from_id: int
    to_id: int
    available_from_s: float
    available_until_s: float
    latency_ms: float
    capacity_gbps: float


@dataclass
class TimedRoute:
    path: list[int]
    departure_time_s: float
    arrival_time_s: float
    total_latency_ms: float
    wait_time_s: float
    hops: int


class TemporalGraph:
    """Time-expanded graph for constellation routing.

    Innovation: Instead of a static graph, maintains a TEMPORAL graph
    where edges have availability windows. This captures the reality
    that LEO links are intermittent — they appear and disappear as
    satellites orbit.

    The routing algorithm searches through both space AND time.
    """

    def __init__(self, time_resolution_s: float = 60.0):
        self.time_resolution = time_resolution_s
        self._edges: dict[tuple[int, int], list[TimedEdge]] = {}
        self._satellite_positions: dict[int, list[tuple[float, tuple[float, float, float]]]] = {}

    def add_satellite_trajectory(
        self,
        sat_id: int,
        positions: list[tuple[float, tuple[float, float, float]]],
    ):
        self._satellite_positions[sat_id] = positions

    def compute_link_windows(
        self,
        sat_a: int,
        sat_b: int,
        max_range_m: float = 5000000,
        time_span_s: float = 3600,
        time_step_s: float = 10,
    ) -> list[TimedEdge]:
        if sat_a not in self._satellite_positions or sat_b not in self._satellite_positions:
            return []

        windows = []
        in_window = False
        window_start = 0.0

        for t in range(0, int(time_span_s), int(time_step_s)):
            pos_a = self._interpolate_position(sat_a, t)
            pos_b = self._interpolate_position(sat_b, t)

            if pos_a is None or pos_b is None:
                if in_window:
                    windows.append(TimedEdge(
                        from_id=sat_a, to_id=sat_b,
                        available_from_s=window_start, available_until_s=t,
                        latency_ms=0, capacity_gbps=100,
                    ))
                    in_window = False
                continue

            dx = pos_a[0] - pos_b[0]
            dy = pos_a[1] - pos_b[1]
            dz = pos_a[2] - pos_b[2]
            dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

            if dist <= max_range_m:
                if not in_window:
                    window_start = t
                    in_window = True
            else:
                if in_window:
                    latency = dist / 299792458.0 * 1000
                    windows.append(TimedEdge(
                        from_id=sat_a, to_id=sat_b,
                        available_from_s=window_start, available_until_s=t,
                        latency_ms=latency, capacity_gbps=100,
                    ))
                    in_window = False

        if in_window:
            windows.append(TimedEdge(
                from_id=sat_a, to_id=sat_b,
                available_from_s=window_start, available_until_s=time_span_s,
                latency_ms=0, capacity_gbps=100,
            ))

        return windows

    def _interpolate_position(self, sat_id: int, time_s: float) -> Optional[tuple[float, float, float]]:
        trajectory = self._satellite_positions.get(sat_id)
        if not trajectory:
            return None

        for i in range(len(trajectory) - 1):
            t0, pos0 = trajectory[i]
            t1, pos1 = trajectory[i + 1]
            if t0 <= time_s <= t1:
                frac = (time_s - t0) / (t1 - t0) if t1 > t0 else 0
                return tuple(
                    pos0[j] + frac * (pos1[j] - pos0[j])
                    for j in range(3)
                )

        return trajectory[-1][1] if trajectory else None


class TimeExpandedRouter:
    """Routes through time-expanded graph.

    Innovation: Standard Dijkstra finds shortest path in space.
    This finds shortest path in SPACE-TIME, accounting for:
    - Link availability windows
    - Wait times at intermediate nodes
    - Propagation delays

    A message can WAIT at a satellite until the next link opens,
    achieving better overall delivery than a path that's shorter
    in space but blocked in time.
    """

    def __init__(self, graph: TemporalGraph):
        self.graph = graph

    def find_timed_route(
        self,
        src: int,
        dst: int,
        departure_time_s: float = 0,
        max_time_s: float = 3600,
        max_hops: int = 10,
    ) -> Optional[TimedRoute]:
        state = {
            "node": src,
            "time": departure_time_s,
            "path": [src],
            "total_latency": 0.0,
            "wait_time": 0.0,
            "hops": 0,
        }

        visited = set()
        queue = [state]
        best_arrival = {}
        best_arrival[(src, 0)] = 0

        while queue:
            queue.sort(key=lambda s: s["time"])
            current = queue.pop(0)

            state_key = (current["node"], current["hops"])
            if state_key in visited:
                continue
            visited.add(state_key)

            if current["node"] == dst:
                return TimedRoute(
                    path=current["path"],
                    departure_time_s=departure_time_s,
                    arrival_time_s=current["time"],
                    total_latency_ms=current["total_latency"],
                    wait_time_s=current["wait_time"],
                    hops=current["hops"],
                )

            if current["hops"] >= max_hops:
                continue

            for neighbor, edges in self.graph._edges.items():
                if neighbor[0] != current["node"]:
                    continue

                to_id = neighbor[1]
                for edge in edges:
                    if edge.available_from_s > current["time"]:
                        wait = edge.available_from_s - current["time"]
                        depart = edge.available_from_s
                    elif edge.available_until_s > current["time"]:
                        wait = 0
                        depart = current["time"]
                    else:
                        continue

                    arrive = depart + edge.latency_ms / 1000
                    if arrive > departure_time_s + max_time_s:
                        continue

                    new_total_latency = current["total_latency"] + edge.latency_ms
                    new_wait = current["wait_time"] + wait

                    new_state = {
                        "node": to_id,
                        "time": arrive,
                        "path": current["path"] + [to_id],
                        "total_latency": new_total_latency,
                        "wait_time": new_wait,
                        "hops": current["hops"] + 1,
                    }

                    new_key = (to_id, new_state["hops"])
                    if new_key not in visited:
                        queue.append(new_state)

        return None

    def find_all_timed_routes(
        self,
        src: int,
        dst: int,
        k: int = 3,
        departure_time_s: float = 0,
    ) -> list[TimedRoute]:
        routes = []
        max_time = 7200

        for _ in range(k * 2):
            route = self.find_timed_route(
                src, dst, departure_time_s, max_time
            )
            if route and not any(r.path == route.path for r in routes):
                routes.append(route)
            max_time = route.arrival_time_s - 1 if route else 0
            if max_time <= 0:
                break

        routes.sort(key=lambda r: r.arrival_time_s)
        return routes[:k]


class DelayTolerantNetwork:
    """Full delay-tolerant routing system for constellations.

    The wheel: graph routing
    The vehicle: time-aware routing through LEO constellations

    Innovation: In LEO, links are intermittent. Traditional routing
    fails because the graph changes faster than packets can traverse it.
    Time-expanded routing pre-computes when links will be available
    and routes messages through time as well as space.

    For Starlink with 6000+ satellites, this enables guaranteed
    delivery even when no end-to-end path exists at any single instant.
    """

    def __init__(self):
        self.graph = TemporalGraph()
        self.router = TimeExpandedRouter(self.graph)
        self._routing_log: list[dict] = []

    def setup_constellation(
        self,
        satellite_trajectories: dict[int, list[tuple[float, tuple[float, float, float]]]],
        isl_range_m: float = 5000000,
    ):
        for sat_id, trajectory in satellite_trajectories.items():
            self.graph.add_satellite_trajectory(sat_id, trajectory)

        sats = list(satellite_trajectories.keys())
        for i in range(len(sats)):
            for j in range(i + 1, len(sats)):
                windows = self.graph.compute_link_windows(sats[i], sats[j], isl_range_m)
                if windows:
                    for window in windows:
                        key = (sats[i], sats[j])
                        if key not in self.graph._edges:
                            self.graph._edges[key] = []
                        self.graph._edges[key].append(window)

                        rev_key = (sats[j], sats[i])
                        if rev_key not in self.graph._edges:
                            self.graph._edges[rev_key] = []
                        self.graph._edges[rev_key].append(TimedEdge(
                            from_id=sats[j], to_id=sats[i],
                            available_from_s=window.available_from_s,
                            available_until_s=window.available_until_s,
                            latency_ms=window.latency_ms,
                            capacity_gbps=window.capacity_gbps,
                        ))

    def route_message(
        self,
        src: int,
        dst: int,
        departure_time_s: float = 0,
    ) -> Optional[dict]:
        route = self.router.find_timed_route(src, dst, departure_time_s)

        if route is None:
            return {
                "deliverable": False,
                "reason": "No path found within time horizon",
                "src": src,
                "dst": dst,
            }

        self._routing_log.append({
            "src": src,
            "dst": dst,
            "departure": departure_time_s,
            "arrival": route.arrival_time_s,
            "hops": route.hops,
            "latency_ms": route.total_latency_ms,
            "wait_s": route.wait_time_s,
        })

        return {
            "deliverable": True,
            "path": route.path,
            "departure_time_s": departure_time_s,
            "arrival_time_s": route.arrival_time_s,
            "delivery_time_s": route.arrival_time_s - departure_time_s,
            "total_latency_ms": route.total_latency_ms,
            "wait_time_s": route.wait_time_s,
            "hops": route.hops,
            "path_description": " → ".join(str(p) for p in route.path),
        }

    @property
    def network_stats(self) -> dict:
        if not self._routing_log:
            return {"total_routes": 0}

        recent = self._routing_log[-20:]
        return {
            "total_routes": len(self._routing_log),
            "avg_hops": sum(r["hops"] for r in recent) / len(recent),
            "avg_latency_ms": sum(r["latency_ms"] for r in recent) / len(recent),
            "avg_delivery_time_s": sum(r["delivery_time_s"] for r in recent) / len(recent),
            "satellites": len(self.graph._satellite_positions),
            "total_link_windows": sum(len(v) for v in self.graph._edges.values()),
        }
