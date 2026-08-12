"""Deterministic local constellation geometry and coverage coordination.

This module builds a simplified circular-orbit constellation, derives a local
inter-satellite mesh, allocates review-only ground coverage, and routes between
visible satellites.  It is a simulation surface, not an operational satellite
network or a model of any specific commercial constellation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from alpha.mesh_routing import ISLEdge, MeshTopology, Route, SatelliteNode

MU_EARTH_M3_S2 = 3.986004418e14
EARTH_RADIUS_M = 6_371_000.0
LIGHT_SPEED_M_S = 299_792_458.0


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class OrbitPlane:
    plane_id: int
    inclination_deg: float
    altitude_km: float
    num_satellites: int
    raan_offset_deg: float = 0.0
    phase_offset_deg: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.plane_id, bool) or not isinstance(self.plane_id, int) or self.plane_id < 0:
            raise ValueError("plane_id must be a non-negative integer")
        inclination = _finite("inclination_deg", self.inclination_deg)
        altitude = _finite("altitude_km", self.altitude_km)
        if not 0.0 <= inclination <= 180.0:
            raise ValueError("inclination_deg must be in [0, 180]")
        if altitude <= 0.0:
            raise ValueError("altitude_km must be > 0")
        if isinstance(self.num_satellites, bool) or not isinstance(self.num_satellites, int) or self.num_satellites <= 0:
            raise ValueError("num_satellites must be a positive integer")
        _finite("raan_offset_deg", self.raan_offset_deg)
        _finite("phase_offset_deg", self.phase_offset_deg)

    @property
    def radius_m(self) -> float:
        return EARTH_RADIUS_M + self.altitude_km * 1000.0

    @property
    def period_s(self) -> float:
        return 2.0 * math.pi * math.sqrt(self.radius_m**3 / MU_EARTH_M3_S2)

    @property
    def orbital_velocity(self) -> float:
        return math.sqrt(MU_EARTH_M3_S2 / self.radius_m)

    def satellite_positions(self, time_s: float) -> list[tuple[float, float, float]]:
        time_s = _finite("time_s", time_s)
        positions = []
        inc = math.radians(self.inclination_deg)
        raan = math.radians(self.raan_offset_deg)
        for index in range(self.num_satellites):
            phase = self.phase_offset_deg + (360.0 / self.num_satellites) * index
            anomaly = math.radians(phase + 360.0 * time_s / self.period_s)
            x_orb = self.radius_m * math.cos(anomaly)
            y_orb = self.radius_m * math.sin(anomaly)
            positions.append((
                x_orb * math.cos(raan) - y_orb * math.sin(raan) * math.cos(inc),
                x_orb * math.sin(raan) + y_orb * math.cos(raan) * math.cos(inc),
                y_orb * math.sin(inc),
            ))
        return positions


@dataclass
class GroundSlot:
    slot_id: int
    lat_deg: float
    lon_deg: float
    elevation_min: float = 25.0
    serving_sat: Optional[int] = None
    backup_sat: Optional[int] = None
    handoff_count: int = 0
    last_handoff: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.slot_id, bool) or not isinstance(self.slot_id, int) or self.slot_id < 0:
            raise ValueError("slot_id must be a non-negative integer")
        self.lat_deg = _finite("lat_deg", self.lat_deg)
        self.lon_deg = _finite("lon_deg", self.lon_deg)
        self.elevation_min = _finite("elevation_min", self.elevation_min)
        if not -90.0 <= self.lat_deg <= 90.0 or not -180.0 <= self.lon_deg <= 180.0:
            raise ValueError("invalid ground latitude/longitude")
        if not -5.0 <= self.elevation_min < 90.0:
            raise ValueError("elevation_min outside supported range")

    @property
    def needs_handoff(self) -> bool:
        return self.serving_sat is not None and self.backup_sat is not None and self.serving_sat != self.backup_sat


@dataclass(frozen=True)
class CoverageMetrics:
    total_slots: int
    covered_slots: int
    coverage_percent: float
    average_elevation: float
    handoff_rate: float
    slot_distribution: dict = field(default_factory=dict)


class ConstellationManager:
    def __init__(self, *, isl_capacity_gbps: float = 100.0):
        isl_capacity_gbps = _finite("isl_capacity_gbps", isl_capacity_gbps)
        if isl_capacity_gbps <= 0.0:
            raise ValueError("isl_capacity_gbps must be > 0")
        self.isl_capacity_gbps = isl_capacity_gbps
        self._topology = MeshTopology()
        self._planes: dict[int, OrbitPlane] = {}
        self._satellites: dict[int, SatelliteNode] = {}
        self._ground_slots: dict[int, GroundSlot] = {}
        self._coverage_log: list[dict] = []
        self._handoff_log: list[dict] = []
        self._initialized = False

    @property
    def topology(self) -> MeshTopology:
        return self._topology

    def add_plane(self, plane: OrbitPlane):
        if self._initialized:
            raise RuntimeError("cannot add planes after constellation initialization")
        if plane.plane_id in self._planes:
            raise ValueError(f"duplicate plane_id: {plane.plane_id}")
        self._planes[plane.plane_id] = plane

    def add_ground_slot(self, slot: GroundSlot):
        if slot.slot_id in self._ground_slots:
            raise ValueError(f"duplicate ground slot: {slot.slot_id}")
        self._ground_slots[slot.slot_id] = slot

    def initialize_constellation(self, time_s: float = 0.0):
        if self._initialized:
            raise RuntimeError("constellation already initialized")
        sat_id = 0
        for plane_id, plane in sorted(self._planes.items()):
            positions = plane.satellite_positions(time_s)
            for index, (x, y, z) in enumerate(positions):
                node = SatelliteNode(
                    sat_id=sat_id,
                    orbit=plane_id,
                    plane=index,
                    phase=index * 360.0 / plane.num_satellites,
                    x=x,
                    y=y,
                    z=z,
                )
                self._topology.add_satellite(node)
                self._satellites[sat_id] = node
                sat_id += 1
        self._create_isl_mesh()
        self._initialized = True

    def _create_isl_mesh(self):
        """Create a deterministic local demonstration mesh.

        Neighboring satellites in the same plane are linked, plus equal-index
        satellites between planes.  This is deliberately a simulation rule,
        not a physical laser-terminal availability model.
        """
        ids = sorted(self._satellites)
        for i, sat_id in enumerate(ids):
            node = self._satellites[sat_id]
            for other_id in ids[i + 1:]:
                other = self._satellites[other_id]
                same_plane_neighbor = node.orbit == other.orbit and abs(node.plane - other.plane) == 1
                cross_plane_peer = node.orbit != other.orbit and node.plane == other.plane
                if same_plane_neighbor or cross_plane_peer:
                    self._add_isl(sat_id, other_id)

    def _add_isl(self, sat1: int, sat2: int):
        n1, n2 = self._satellites[sat1], self._satellites[sat2]
        distance = math.dist(n1.position, n2.position)
        latency_ms = distance / LIGHT_SPEED_M_S * 1000.0
        self._topology.add_isl(ISLEdge(sat1, sat2, latency_ms, self.isl_capacity_gbps))

    def update_positions(self, time_s: float):
        if not self._initialized:
            raise RuntimeError("initialize_constellation must run first")
        for plane_id, plane in self._planes.items():
            for index, (x, y, z) in enumerate(plane.satellite_positions(time_s)):
                sat_id = self._find_sat_id(plane_id, index)
                if sat_id is not None:
                    node = self._satellites[sat_id]
                    self._topology.update_satellite(sat_id, x, y, z, node.load)
        self._refresh_link_latencies()

    def _refresh_link_latencies(self) -> None:
        seen: set[tuple[int, int]] = set()
        for (u, v), edge in list(self._topology._edges.items()):
            pair = tuple(sorted((u, v)))
            if pair in seen:
                continue
            seen.add(pair)
            distance = math.dist(self._satellites[u].position, self._satellites[v].position)
            self._topology.update_edge(u, v, distance / LIGHT_SPEED_M_S * 1000.0, edge.current_load)

    def _find_sat_id(self, plane_id: int, index: int) -> Optional[int]:
        for sat_id, node in self._satellites.items():
            if node.orbit == plane_id and node.plane == index:
                return sat_id
        return None

    def allocate_coverage(self, time_s: float = 0.0) -> CoverageMetrics:
        time_s = _finite("time_s", time_s)
        covered = 0
        total_elevation = 0.0
        distribution: dict[int, int] = {}

        for slot_id, slot in sorted(self._ground_slots.items()):
            candidates = sorted(
                (
                    (self._compute_elevation(slot, node), sat_id)
                    for sat_id, node in self._satellites.items()
                    if node.active
                ),
                key=lambda item: (-item[0], item[1]),
            )
            visible = [(elevation, sat_id) for elevation, sat_id in candidates if elevation >= slot.elevation_min]
            old_sat = slot.serving_sat
            if not visible:
                slot.serving_sat = None
                slot.backup_sat = None
                continue

            best_elevation, best_sat = visible[0]
            slot.serving_sat = best_sat
            slot.backup_sat = visible[1][1] if len(visible) > 1 else None
            if old_sat is not None and old_sat != best_sat:
                slot.handoff_count += 1
                slot.last_handoff = time_s
                self._handoff_log.append({
                    "time_s": time_s,
                    "slot": slot_id,
                    "from": old_sat,
                    "to": best_sat,
                    "operational_authority": False,
                })
            covered += 1
            total_elevation += best_elevation
            bucket = int(best_elevation // 10) * 10
            distribution[bucket] = distribution.get(bucket, 0) + 1

        total = len(self._ground_slots)
        metrics = CoverageMetrics(
            total_slots=total,
            covered_slots=covered,
            coverage_percent=100.0 * covered / total if total else 0.0,
            average_elevation=total_elevation / covered if covered else 0.0,
            handoff_rate=float(len(self._handoff_log)),
            slot_distribution=distribution,
        )
        self._coverage_log.append({
            "time_s": time_s,
            "covered_slots": covered,
            "total_slots": total,
            "operational_authority": False,
        })
        return metrics

    def _compute_elevation(self, slot: GroundSlot, sat: SatelliteNode) -> float:
        lat = math.radians(slot.lat_deg)
        lon = math.radians(slot.lon_deg)
        ground = (
            EARTH_RADIUS_M * math.cos(lat) * math.cos(lon),
            EARTH_RADIUS_M * math.cos(lat) * math.sin(lon),
            EARTH_RADIUS_M * math.sin(lat),
        )
        line = (sat.x - ground[0], sat.y - ground[1], sat.z - ground[2])
        distance = math.sqrt(sum(component * component for component in line))
        if distance <= 0.0:
            raise ValueError("satellite and ground slot positions coincide")
        up = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))
        projection = sum(line[index] * up[index] for index in range(3)) / distance
        return math.degrees(math.asin(max(-1.0, min(1.0, projection))))

    def find_ground_route(self, src_lat: float, src_lon: float, dst_lat: float, dst_lon: float) -> Optional[Route]:
        src_sat = self._find_best_sat(src_lat, src_lon)
        dst_sat = self._find_best_sat(dst_lat, dst_lon)
        if src_sat is None or dst_sat is None:
            return None
        return self._topology.find_route(src_sat, dst_sat, max_latency_ms=500.0)

    def _find_best_sat(self, lat: float, lon: float) -> Optional[int]:
        slot = GroundSlot(0, lat, lon)
        candidates = [
            (self._compute_elevation(slot, node), sat_id)
            for sat_id, node in self._satellites.items()
            if node.active
        ]
        visible = [(elevation, sat_id) for elevation, sat_id in candidates if elevation >= slot.elevation_min]
        return max(visible, default=(float("-inf"), None), key=lambda item: (item[0], -1 if item[1] is None else -item[1]))[1]

    @property
    def constellation_stats(self) -> dict:
        total = len(self._satellites)
        return {
            "total_satellites": total,
            "active_satellites": sum(1 for node in self._satellites.values() if node.active),
            "total_isl_links": self._topology.edge_count,
            "total_planes": len(self._planes),
            "average_degree": round(self._topology.average_degree, 3),
            "handoffs": len(self._handoff_log),
            "operational_authority": False,
        }

    @property
    def handoff_history(self) -> list[dict]:
        return list(self._handoff_log)
