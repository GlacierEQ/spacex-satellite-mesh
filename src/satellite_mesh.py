#!/usr/bin/env python3
"""Executable local satellite-mesh routing simulator.

The CLI exposes deterministic static and delay-tolerant routing over supplied
local topology data.  It has no laser-terminal control, spacecraft authority,
production constellation integration, or affiliation with SpaceX.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

from alpha.mesh_routing import ISLEdge, MeshTopology, SatelliteNode
from omega.temporal_routing import DelayTolerantNetwork


def _mapping_list(name: str, value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"every {name} item must be an object")
    return value  # type: ignore[return-value]


def build_topology(payload: Mapping[str, object]) -> MeshTopology:
    topology = MeshTopology()
    for raw in _mapping_list("satellites", payload.get("satellites", [])):
        topology.add_satellite(SatelliteNode(
            sat_id=int(raw["sat_id"]),
            orbit=int(raw.get("orbit", 0)),
            plane=int(raw.get("plane", 0)),
            phase=float(raw.get("phase_deg", 0.0)),
            x=float(raw.get("x_m", 0.0)),
            y=float(raw.get("y_m", 0.0)),
            z=float(raw.get("z_m", 0.0)),
            active=bool(raw.get("active", True)),
            load=float(raw.get("load", 0.0)),
        ))
    if topology.node_count == 0:
        raise ValueError("at least one satellite is required")
    for raw in _mapping_list("links", payload.get("links", [])):
        topology.add_isl(ISLEdge(
            from_id=int(raw["from"]),
            to_id=int(raw["to"]),
            latency_ms=float(raw["latency_ms"]),
            capacity_gbps=float(raw["capacity_gbps"]),
            current_load=float(raw.get("current_load_gbps", 0.0)),
            active=bool(raw.get("active", True)),
        ))
    return topology


def evaluate_static_payload(payload: Mapping[str, object]) -> dict[str, object]:
    topology = build_topology(payload)
    query = payload.get("query")
    if not isinstance(query, Mapping):
        raise ValueError("query must be an object")
    src, dst = int(query["src"]), int(query["dst"])
    max_latency_ms = float(query.get("max_latency_ms", 200.0))
    k = int(query.get("k", 1))
    if k == 1:
        route = topology.find_route(src, dst, max_latency_ms)
        routes = [] if route is None else [route]
    else:
        routes = topology.find_all_routes(src, dst, k=k, max_latency_ms=max_latency_ms)
    return {
        "schema": "glaciereq.satellite-mesh-route.v1",
        "topology": topology.snapshot,
        "routes": [asdict(route) for route in routes],
        "deliverable": bool(routes),
        "operational_authority": False,
    }


def evaluate_temporal_payload(payload: Mapping[str, object]) -> dict[str, object]:
    raw_trajectories = payload.get("trajectories")
    if not isinstance(raw_trajectories, Mapping) or len(raw_trajectories) < 2:
        raise ValueError("trajectories must be an object containing at least two satellites")
    trajectories: dict[int, list[tuple[float, tuple[float, float, float]]]] = {}
    for raw_sat_id, raw_points in raw_trajectories.items():
        points = _mapping_list(f"trajectory {raw_sat_id}", raw_points)
        parsed: list[tuple[float, tuple[float, float, float]]] = []
        for point in points:
            position = point.get("position_m")
            if not isinstance(position, list) or len(position) != 3:
                raise ValueError("position_m must contain three coordinates")
            parsed.append((
                float(point["time_s"]),
                (float(position[0]), float(position[1]), float(position[2])),
            ))
        trajectories[int(raw_sat_id)] = parsed

    query = payload.get("query")
    if not isinstance(query, Mapping):
        raise ValueError("query must be an object")
    network = DelayTolerantNetwork()
    network.setup_constellation(
        trajectories,
        isl_range_m=float(payload.get("isl_range_m", 5_000_000.0)),
        time_step_s=float(payload.get("time_step_s", 10.0)),
    )
    result = network.route_message(
        int(query["src"]),
        int(query["dst"]),
        float(query.get("departure_time_s", 0.0)),
        float(query.get("max_time_s", 3600.0)),
    )
    return {
        "schema": "glaciereq.satellite-mesh-temporal-route.v1",
        "route": result,
        "network": network.network_stats,
        "operational_authority": False,
    }


def static_demo() -> dict[str, object]:
    return {
        "satellites": [
            {"sat_id": 0, "load": 0.20},
            {"sat_id": 1, "load": 0.40},
            {"sat_id": 2, "load": 0.10},
            {"sat_id": 3, "load": 0.30},
        ],
        "links": [
            {"from": 0, "to": 1, "latency_ms": 8, "capacity_gbps": 40},
            {"from": 1, "to": 3, "latency_ms": 8, "capacity_gbps": 40},
            {"from": 0, "to": 2, "latency_ms": 11, "capacity_gbps": 80},
            {"from": 2, "to": 3, "latency_ms": 11, "capacity_gbps": 80},
        ],
        "query": {"src": 0, "dst": 3, "k": 2, "max_latency_ms": 100},
    }


def temporal_demo() -> dict[str, object]:
    return {
        "isl_range_m": 1_000_000,
        "time_step_s": 10,
        "trajectories": {
            "0": [
                {"time_s": 0, "position_m": [0, 0, 0]},
                {"time_s": 100, "position_m": [0, 0, 0]},
            ],
            "1": [
                {"time_s": 0, "position_m": [2_000_000, 0, 0]},
                {"time_s": 100, "position_m": [500_000, 0, 0]},
            ],
        },
        "query": {"src": 0, "dst": 1, "departure_time_s": 0, "max_time_s": 100},
    }


def _load_json(path: str) -> dict[str, object]:
    if path == "-":
        import sys
        value = json.load(sys.stdin)
    else:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic local satellite-mesh routing simulator")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("demo")
    route = sub.add_parser("route")
    route.add_argument("input")
    sub.add_parser("temporal-demo")
    temporal = sub.add_parser("temporal")
    temporal.add_argument("input")
    args = parser.parse_args(argv)

    if args.command in (None, "demo"):
        result = evaluate_static_payload(static_demo())
    elif args.command == "route":
        result = evaluate_static_payload(_load_json(args.input))
    elif args.command == "temporal-demo":
        result = evaluate_temporal_payload(temporal_demo())
    else:
        result = evaluate_temporal_payload(_load_json(args.input))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
