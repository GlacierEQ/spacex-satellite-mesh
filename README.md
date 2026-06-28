# SpaceX Satellite Mesh

Starlink constellation mesh networking — routing, topology, and coverage management.

## Architecture

**Double Helix (Alpha + Omega)**

- **Alpha** (`src/alpha/mesh_routing.py`): Dijkstra pathfinding over dynamic ISL graph, K-shortest paths, capacity-aware routing.
- **Omega** (`src/omega/constellation_manager.py`): Walker constellation configuration, ground coverage allocation, satellite handoff.

## Features

- Dynamic ISL topology with latency and capacity
- Dijkstra shortest-path routing
- Yen's K-shortest paths for redundancy
- Walker constellation configuration
- Ground slot coverage allocation
- Satellite handoff management
- Zero external dependencies
