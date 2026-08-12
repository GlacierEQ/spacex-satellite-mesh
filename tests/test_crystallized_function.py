from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alpha.mesh_routing import ISLEdge, MeshTopology, SatelliteNode
from omega.constellation_manager import ConstellationManager, GroundSlot, OrbitPlane
from omega.temporal_routing import TemporalGraph, TimedEdge, TimeExpandedRouter
from satellite_mesh import evaluate_static_payload


def node(sat_id: int, *, active: bool = True, load: float = 0.0) -> SatelliteNode:
    return SatelliteNode(sat_id, 0, sat_id, sat_id * 10.0, active=active, load=load)


def test_static_router_uses_lowest_latency_viable_path():
    mesh = MeshTopology()
    for sat_id in range(4):
        mesh.add_satellite(node(sat_id))
    mesh.add_isl(ISLEdge(0, 1, 5.0, 20.0))
    mesh.add_isl(ISLEdge(1, 3, 5.0, 20.0))
    mesh.add_isl(ISLEdge(0, 2, 8.0, 100.0))
    mesh.add_isl(ISLEdge(2, 3, 8.0, 100.0))
    route = mesh.find_route(0, 3)
    assert route is not None
    assert route.path == [0, 1, 3]
    assert route.total_latency_ms == 10.0
    assert route.min_capacity_gbps == 20.0


def test_saturated_and_inactive_paths_are_rejected():
    mesh = MeshTopology()
    mesh.add_satellite(node(0))
    mesh.add_satellite(node(1))
    mesh.add_isl(ISLEdge(0, 1, 2.0, 10.0, current_load=10.0))
    assert mesh.find_route(0, 1) is None
    mesh.update_edge(0, 1, 2.0, 0.0)
    mesh.set_satellite_active(0, False)
    assert mesh.find_route(0, 1) is None


def test_k_route_search_does_not_reactivate_failed_links():
    mesh = MeshTopology()
    for sat_id in range(4):
        mesh.add_satellite(node(sat_id))
    mesh.add_isl(ISLEdge(0, 1, 1.0, 10.0))
    mesh.add_isl(ISLEdge(1, 3, 1.0, 10.0))
    mesh.add_isl(ISLEdge(0, 2, 2.0, 10.0))
    mesh.add_isl(ISLEdge(2, 3, 2.0, 10.0))
    mesh.set_isl_active(0, 1, False)
    before = mesh.get_edge(0, 1).active
    routes = mesh.find_all_routes(0, 3, k=3)
    after = mesh.get_edge(0, 1).active
    assert before is False and after is False
    assert [route.path for route in routes] == [[0, 2, 3]]


def test_bottleneck_satellite_is_highest_load_not_lowest():
    mesh = MeshTopology()
    mesh.add_satellite(node(0, load=0.1))
    mesh.add_satellite(node(1, load=0.9))
    mesh.add_satellite(node(2, load=0.2))
    mesh.add_isl(ISLEdge(0, 1, 1.0, 10.0))
    mesh.add_isl(ISLEdge(1, 2, 1.0, 10.0))
    route = mesh.find_route(0, 2)
    assert route is not None
    assert route.bottleneck_sat == 1


def test_constellation_records_handoff_from_satellite_zero():
    manager = ConstellationManager()
    manager.add_plane(OrbitPlane(0, 0.0, 550.0, 4, raan_offset_deg=0.0))
    manager.add_plane(OrbitPlane(1, 0.0, 550.0, 4, raan_offset_deg=0.0))
    manager.initialize_constellation()
    manager.add_ground_slot(GroundSlot(0, 0.0, 0.0, elevation_min=20.0))
    first = manager.allocate_coverage(time_s=0.0)
    assert first.covered_slots == 1
    slot = manager._ground_slots[0]
    assert slot.serving_sat == 0
    assert slot.backup_sat == 4
    manager.topology.set_satellite_active(0, False)
    second = manager.allocate_coverage(time_s=1.0)
    assert second.covered_slots == 1
    assert slot.serving_sat == 4
    assert slot.handoff_count == 1
    assert manager.handoff_history[-1]["from"] == 0


def test_temporal_windows_use_in_window_physical_latency():
    graph = TemporalGraph()
    graph.add_satellite_trajectory(0, [(0, (0, 0, 0)), (20, (0, 0, 0))])
    graph.add_satellite_trajectory(1, [(0, (1000, 0, 0)), (20, (1000, 0, 0))])
    windows = graph.compute_link_windows(0, 1, max_range_m=2000, time_span_s=20, time_step_s=10)
    assert len(windows) == 1
    assert windows[0].available_from_s == 0
    assert windows[0].available_until_s == 20
    assert windows[0].latency_ms == pytest.approx(1000 / 299_792_458 * 1000)
    assert windows[0].latency_ms > 0


def test_trajectory_does_not_freeze_forever_after_last_sample():
    graph = TemporalGraph()
    graph.add_satellite_trajectory(0, [(0, (0, 0, 0)), (10, (10, 0, 0))])
    assert graph._interpolate_position(0, 10) == (10.0, 0.0, 0.0)
    assert graph._interpolate_position(0, 11) is None


def test_timed_router_waits_for_future_link_window():
    graph = TemporalGraph()
    graph.add_link_window(TimedEdge(0, 1, 10.0, 20.0, 1000.0, 10.0))
    route = TimeExpandedRouter(graph).find_timed_route(0, 1, departure_time_s=0, max_time_s=30)
    assert route is not None
    assert route.path == [0, 1]
    assert route.wait_time_s == 10.0
    assert route.arrival_time_s == pytest.approx(11.0)
    assert route.total_latency_ms == 1000.0


def test_static_payload_and_cli_emit_truth_boundary():
    payload = {
        "satellites": [{"sat_id": 0}, {"sat_id": 1}],
        "links": [{"from": 0, "to": 1, "latency_ms": 3, "capacity_gbps": 20}],
        "query": {"src": 0, "dst": 1},
    }
    result = evaluate_static_payload(payload)
    assert result["schema"] == "glaciereq.satellite-mesh-route.v1"
    assert result["deliverable"] is True
    assert result["operational_authority"] is False

    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "satellite_mesh.py"), "demo"],
        check=True,
        capture_output=True,
        text=True,
    )
    cli = json.loads(proc.stdout)
    assert cli["schema"] == "glaciereq.satellite-mesh-route.v1"
    assert cli["operational_authority"] is False


def test_invalid_edge_and_negative_generic_cost_fail_closed():
    mesh = MeshTopology()
    mesh.add_satellite(node(0))
    with pytest.raises(KeyError):
        mesh.add_isl(ISLEdge(0, 1, 1.0, 10.0))

    from mesh_route import shortest_path
    with pytest.raises(ValueError):
        shortest_path({"A": {"B": -1.0}}, "A", "B")
