"""Satellite mesh and constellation tests."""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alpha.mesh_routing import MeshTopology, SatelliteNode, ISLEdge, Route
from omega.constellation_manager import (
    OrbitPlane, GroundSlot, ConstellationManager, CoverageMetrics,
)


def test_mesh_basic():
    m = MeshTopology()
    m.add_satellite(SatelliteNode(0, 0, 0, 0, 0, 0, 7000000))
    m.add_satellite(SatelliteNode(1, 0, 0, 90, 7000000, 0, 0))
    m.add_isl(ISLEdge(0, 1, 20.0, 100.0))

    route = m.find_route(0, 1)
    assert route is not None
    assert route.path == [0, 1]
    assert route.total_hops == 1


def test_mesh_multi_hop():
    m = MeshTopology()
    for i in range(5):
        m.add_satellite(SatelliteNode(i, 0, i, i * 90, i * 7000000, 0, 0))
    for i in range(4):
        m.add_isl(ISLEdge(i, i + 1, 10.0, 100.0))

    route = m.find_route(0, 4)
    assert route is not None
    assert route.total_hops == 4


def test_mesh_no_route():
    m = MeshTopology()
    m.add_satellite(SatelliteNode(0, 0, 0, 0))
    m.add_satellite(SatelliteNode(1, 0, 1, 90))
    route = m.find_route(0, 1)
    assert route is None


def test_mesh_capacity():
    m = MeshTopology()
    m.add_satellite(SatelliteNode(0, 0, 0, 0))
    m.add_satellite(SatelliteNode(1, 0, 1, 90))
    m.add_isl(ISLEdge(0, 1, 10.0, 100.0))

    route = m.find_route(0, 1)
    assert route.min_capacity_gbps == 100.0


def test_mesh_k_routes():
    m = MeshTopology()
    for i in range(6):
        m.add_satellite(SatelliteNode(i, 0, i, i * 60, i * 5000000, 0, 0))
    m.add_isl(ISLEdge(0, 1, 10.0, 100.0))
    m.add_isl(ISLEdge(1, 2, 10.0, 100.0))
    m.add_isl(ISLEdge(0, 3, 15.0, 100.0))
    m.add_isl(ISLEdge(3, 2, 15.0, 100.0))

    routes = m.find_all_routes(0, 2, k=3)
    assert len(routes) >= 2


def test_orbit_plane_period():
    plane = OrbitPlane(0, 53.0, 550, 22)
    assert plane.period_s > 5000
    assert plane.period_s < 6000
    assert plane.orbital_velocity > 7000


def test_constellation_init():
    cm = ConstellationManager()
    cm.add_plane(OrbitPlane(0, 53.0, 550, 4))
    cm.add_plane(OrbitPlane(1, 53.0, 550, 4, raan_offset_deg=45))
    cm.initialize_constellation()

    assert cm.constellation_stats["total_satellites"] == 8
    assert cm.constellation_stats["total_isl_links"] > 0


def test_coverage_allocation():
    cm = ConstellationManager()
    cm.add_plane(OrbitPlane(0, 53.0, 550, 12))
    cm.initialize_constellation()

    for i in range(10):
        cm.add_ground_slot(GroundSlot(i, 0, i * 36 - 180))

    metrics = cm.allocate_coverage()
    assert metrics.total_slots == 10
    assert metrics.coverage_percent > 0


def test_ground_route():
    cm = ConstellationManager()
    cm.add_plane(OrbitPlane(0, 53.0, 550, 8))
    cm.initialize_constellation()

    route = cm.find_ground_route(0, 0, 0, 90)
    assert route is None or isinstance(route, Route)


def test_topology_stats():
    m = MeshTopology()
    for i in range(10):
        m.add_satellite(SatelliteNode(i, 0, i, i * 36))
    for i in range(9):
        m.add_isl(ISLEdge(i, i + 1, 10.0, 100.0))

    assert m.node_count == 10
    assert m.edge_count == 9
    assert m.average_degree == 1.8


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
