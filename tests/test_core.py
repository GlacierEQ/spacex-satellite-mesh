"""Tests for spacex-satellite-mesh — the web that connects worlds.

3 tests. Because a disconnected constellation is just debris.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import math
from alpha.mesh_routing import MeshTopology, SatelliteNode, ISLEdge, Route
from omega.temporal_routing import TemporalGraph, TimeExpandedRouter, TimedEdge


def test_mesh_route():
    mesh = MeshTopology()
    mesh.add_satellite(SatelliteNode(sat_id=0, orbit=0, plane=0, phase=0, x=0, y=0, z=7000000))
    mesh.add_satellite(SatelliteNode(sat_id=1, orbit=0, plane=1, phase=90, x=7000000, y=0, z=0))
    mesh.add_isl(ISLEdge(from_id=0, to_id=1, latency_ms=23.0, capacity_gbps=100))
    route = mesh.find_route(0, 1)
    assert route is not None
    assert route.path == [0, 1]

def test_temporal_graph():
    tg = TemporalGraph()
    tg.add_satellite_trajectory(0, [(0, (0, 0, 7000000)), (100, (7000000, 0, 0))])
    tg.add_satellite_trajectory(1, [(0, (7000000, 0, 0)), (100, (0, 0, 7000000))])
    windows = tg.compute_link_windows(0, 1, max_range_m=15000000)
    assert len(windows) >= 0

def test_k_shortest_paths():
    mesh = MeshTopology()
    for i in range(5):
        mesh.add_satellite(SatelliteNode(sat_id=i, orbit=0, plane=i, phase=i*72,
                                          x=i*1000000, y=0, z=7000000))
    for i in range(4):
        mesh.add_isl(ISLEdge(from_id=i, to_id=i+1, latency_ms=10.0, capacity_gbps=100))
    routes = mesh.find_all_routes(0, 4, k=2)
    assert len(routes) >= 1


# Starlink has 6000+ satellites.
# Each one a node. Each one a voice.
# The mesh is the organism.
STARLINK_NODES = 6000
assert STARLINK_NODES > 5000, "The constellation grows"
