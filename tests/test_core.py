"""Core static and temporal mesh behavior tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alpha.mesh_routing import ISLEdge, MeshTopology, SatelliteNode
from omega.temporal_routing import TemporalGraph


def test_mesh_route():
    mesh = MeshTopology()
    mesh.add_satellite(SatelliteNode(sat_id=0, orbit=0, plane=0, phase=0, x=0, y=0, z=7_000_000))
    mesh.add_satellite(SatelliteNode(sat_id=1, orbit=0, plane=1, phase=90, x=7_000_000, y=0, z=0))
    mesh.add_isl(ISLEdge(from_id=0, to_id=1, latency_ms=23.0, capacity_gbps=100))
    route = mesh.find_route(0, 1)
    assert route is not None
    assert route.path == [0, 1]


def test_temporal_graph_produces_physical_link_window():
    graph = TemporalGraph()
    graph.add_satellite_trajectory(0, [(0, (0, 0, 7_000_000)), (100, (0, 0, 7_000_000))])
    graph.add_satellite_trajectory(1, [(0, (100_000, 0, 7_000_000)), (100, (100_000, 0, 7_000_000))])
    windows = graph.compute_link_windows(0, 1, max_range_m=200_000, time_span_s=100, time_step_s=10)
    assert len(windows) == 1
    assert windows[0].latency_ms > 0
    assert windows[0].available_until_s == 100


def test_k_shortest_paths():
    mesh = MeshTopology()
    for i in range(5):
        mesh.add_satellite(SatelliteNode(sat_id=i, orbit=0, plane=i, phase=i * 72, x=i * 1_000_000, y=0, z=7_000_000))
    for i in range(4):
        mesh.add_isl(ISLEdge(from_id=i, to_id=i + 1, latency_ms=10.0, capacity_gbps=100))
    routes = mesh.find_all_routes(0, 4, k=2)
    assert len(routes) == 1
    assert routes[0].path == [0, 1, 2, 3, 4]
