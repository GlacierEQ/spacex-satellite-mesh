"""Constellation manager — orbit plane coordination, phasing, and slot allocation.

Manages Starlink-likeWalker constellations with slot-based coverage optimization.
Handles handoff between satellites and ground coverage requirements.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from alpha.mesh_routing import MeshTopology, SatelliteNode, ISLEdge, Route


@dataclass
class OrbitPlane:
    plane_id: int
    inclination_deg: float
    altitude_km: float
    num_satellites: int
    raan_offset_deg: float = 0.0
    phase_offset_deg: float = 0.0

    @property
    def radius_m(self) -> float:
        return 6371000 + self.altitude_km * 1000

    @property
    def period_s(self) -> float:
        mu = 3.986004418e14
        return 2 * math.pi * math.sqrt(self.radius_m ** 3 / mu)

    @property
    def orbital_velocity(self) -> float:
        mu = 3.986004418e14
        return math.sqrt(mu / self.radius_m)

    def satellite_positions(self, time_s: float) -> list[tuple[float, float, float]]:
        positions = []
        for idx in range(self.num_satellites):
            phase = self.phase_offset_deg + (360.0 / self.num_satellites) * idx
            mean_anomaly = math.radians(phase + 360.0 * time_s / self.period_s)

            inc = math.radians(self.inclination_deg)
            raan = math.radians(self.raan_offset_deg)

            x_orb = self.radius_m * math.cos(mean_anomaly)
            y_orb = self.radius_m * math.sin(mean_anomaly)

            x = x_orb * math.cos(raan) - y_orb * math.sin(raan) * math.cos(inc)
            y = x_orb * math.sin(raan) + y_orb * math.cos(raan) * math.cos(inc)
            z = y_orb * math.sin(inc)

            positions.append((x, y, z))
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

    @property
    def needs_handoff(self) -> bool:
        return self.serving_sat is not None and self.serving_sat != self.backup_sat


@dataclass
class CoverageMetrics:
    total_slots: int
    covered_slots: int
    coverage_percent: float
    average_elevation: float
    handoff_rate: float
    slot_distribution: dict = field(default_factory=dict)


class ConstellationManager:
    def __init__(self):
        self._topology = MeshTopology()
        self._planes: dict[int, OrbitPlane] = {}
        self._satellites: dict[int, SatelliteNode] = {}
        self._ground_slots: dict[int, GroundSlot] = {}
        self._coverage_log: list[dict] = []
        self._handoff_log: list[dict] = []

    @property
    def topology(self) -> MeshTopology:
        return self._topology

    def add_plane(self, plane: OrbitPlane):
        self._planes[plane.plane_id] = plane

    def add_ground_slot(self, slot: GroundSlot):
        self._ground_slots[slot.slot_id] = slot

    def initialize_constellation(self, time_s: float = 0.0):
        sat_id = 0
        for plane_id, plane in sorted(self._planes.items()):
            positions = plane.satellite_positions(time_s)
            for idx, (x, y, z) in enumerate(positions):
                node = SatelliteNode(
                    sat_id=sat_id, orbit=plane_id, plane=idx,
                    phase=idx * 360.0 / plane.num_satellites,
                    x=x, y=y, z=z,
                )
                self._topology.add_satellite(node)
                self._satellites[sat_id] = node
                sat_id += 1

        self._create_isl_mesh()

    def _create_isl_mesh(self):
        for sat_id, node in self._satellites.items():
            for other_id, other in self._satellites.items():
                if sat_id >= other_id:
                    continue
                if node.orbit == other.orbit:
                    if abs(node.plane - other.plane) <= 1:
                        self._add_isl(sat_id, other_id)
                elif node.orbit != other.orbit:
                    if node.plane == other.plane:
                        self._add_isl(sat_id, other_id)

    def _add_isl(self, sat1: int, sat2: int):
        n1 = self._satellites.get(sat1)
        n2 = self._satellites.get(sat2)
        if not n1 or not n2:
            return

        dx = n1.x - n2.x
        dy = n1.y - n2.y
        dz = n1.z - n2.z
        dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

        latency = dist / 299792458.0 * 1000
        capacity = 100.0

        self._topology.add_isl(ISLEdge(sat1, sat2, latency, capacity))

    def update_positions(self, time_s: float):
        for plane_id, plane in self._planes.items():
            positions = plane.satellite_positions(time_s)
            for idx, (x, y, z) in enumerate(positions):
                sat_id = self._find_sat_id(plane_id, idx)
                if sat_id is not None:
                    self._topology.update_satellite(sat_id, x, y, z, 0.0)

    def _find_sat_id(self, plane_id: int, idx: int) -> Optional[int]:
        for sat_id, node in self._satellites.items():
            if node.orbit == plane_id and node.plane == idx:
                return sat_id
        return None

    def allocate_coverage(self) -> CoverageMetrics:
        covered = 0
        total_elev = 0.0
        slot_dist = {}

        for slot_id, slot in self._ground_slots.items():
            best_sat = None
            best_elev = 0.0

            for sat_id, node in self._satellites.items():
                if not node.active:
                    continue
                elev = self._compute_elevation(slot, node)
                if elev > slot.elevation_min and elev > best_elev:
                    best_elev = elev
                    best_sat = sat_id

            if best_sat is not None:
                old_sat = slot.serving_sat
                slot.serving_sat = best_sat
                if old_sat and old_sat != best_sat:
                    slot.handoff_count += 1
                    self._handoff_log.append({
                        "slot": slot_id,
                        "from": old_sat,
                        "to": best_sat,
                    })
                covered += 1
                total_elev += best_elev
                bucket = int(best_elev / 10) * 10
                slot_dist[bucket] = slot_dist.get(bucket, 0) + 1

        total = len(self._ground_slots)
        avg_elev = total_elev / covered if covered > 0 else 0

        return CoverageMetrics(
            total_slots=total,
            covered_slots=covered,
            coverage_percent=100 * covered / total if total > 0 else 0,
            average_elevation=avg_elev,
            handoff_rate=len(self._handoff_log),
            slot_distribution=slot_dist,
        )

    def _compute_elevation(self, slot: GroundSlot, sat: SatelliteNode) -> float:
        lat_r = math.radians(slot.lat_deg)
        lon_r = math.radians(slot.lon_deg)

        cos_lat = math.cos(lat_r)
        sin_lat = math.sin(lat_r)
        cos_lon = math.cos(lon_r)
        sin_lon = math.sin(lon_r)

        R = 6371000
        gs_x = R * cos_lat * cos_lon
        gs_y = R * cos_lat * sin_lon
        gs_z = R * sin_lat

        dx = sat.x - gs_x
        dy = sat.y - gs_y
        dz = sat.z - gs_z
        dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

        up_x = cos_lat * cos_lon
        up_y = cos_lat * sin_lon
        up_z = sin_lat

        dot = dx * up_x + dy * up_y + dz * up_z
        elev_rad = math.asin(max(-1, min(1, dot / dist)))

        return math.degrees(elev_rad)

    def find_ground_route(
        self, src_lat: float, src_lon: float, dst_lat: float, dst_lon: float
    ) -> Optional[Route]:
        src_sat = self._find_best_sat(src_lat, src_lon)
        dst_sat = self._find_best_sat(dst_lat, dst_lon)

        if src_sat is None or dst_sat is None:
            return None

        return self._topology.find_route(src_sat, dst_sat)

    def _find_best_sat(self, lat: float, lon: float) -> Optional[int]:
        best_sat = None
        best_elev = 0.0

        for sat_id, node in self._satellites.items():
            if not node.active:
                continue
            slot = GroundSlot(0, lat, lon)
            elev = self._compute_elevation(slot, node)
            if elev > 25 and elev > best_elev:
                best_elev = elev
                best_sat = sat_id

        return best_sat

    @property
    def constellation_stats(self) -> dict:
        total_sats = len(self._satellites)
        active_sats = sum(1 for n in self._satellites.values() if n.active)
        total_isl = self._topology.edge_count
        return {
            "total_satellites": total_sats,
            "active_satellites": active_sats,
            "total_isl_links": total_isl,
            "total_planes": len(self._planes),
            "average_degree": round(self._topology.average_degree, 1),
        }
