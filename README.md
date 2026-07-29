# SpaceX Satellite Mesh — Constellation Network Routing & Inter-Satellite Links 🛰️

> **Distributed mesh networking for LEO satellite constellations with inter-satellite laser links.**

[![Python](https://img.shields.io/badge/Python-3.9+-blue)]()
[![Rust](https://img.shields.io/badge/Rust-Routing%20Engine-orange)]()
[![Domain](https://img.shields.io/badge/Domain-Constellation%20Networking-red)]()

---

## 🎯 For Recruiters & Hiring Managers

This repository implements a **satellite constellation mesh network** — the routing layer that enables thousands of satellites to communicate via laser inter-satellite links (ISLs) with dynamic topology. It demonstrates:

- **Dynamic graph routing** on a constantly-changing network topology as satellites orbit
- **Shortest-path algorithms** optimized for light-speed propagation delay constraints
- **Topology management** handling satellite handoffs, eclipse periods, and link failures
- **Load balancing** across multiple ISL paths with latency-aware traffic engineering

**Why this matters**: Satellite mesh networking is the **hardest networking problem on Earth (and in space)** — combining distributed systems, graph algorithms, and real-time topology changes at global scale. These skills directly apply to SDN, 5G network slicing, and data center fabric engineering.

---

## 🔬 For Engineers & Technical Reviewers

### Architecture

```
Satellite A ──ISL──→ Satellite B ──ISL──→ Satellite C
     │                    │                    │
  Ground              Routing               Ground
  Gateway             Engine                Gateway
     │                    │                    │
  User ←──── End-to-End Path ────→ Internet
```

### Core Components

| Component | Language | Purpose |
|---|---|---|
| `src/satellite_mesh.py` | Python | Constellation topology, ISL management, path computation |
| `src/routing_engine.rs` | Rust | High-performance Dijkstra/A* routing with safety guarantees |
| `tests/` | Python | Constellation simulation with orbital dynamics |

---

## 🤖 ML/AI & Programmatic Mesh Integration

- **MCP Tool**: `route_query(src, dst)` — optimal path computation queryable by agents
- **Mastermind Sidecar**: Publishes topology changes to APEX Highway mesh
- **AI Extension**: GNN-based traffic prediction for proactive route pre-computation

```python
route = await mcp_client.call_tool("satellite-mesh", "compute_route", {"src": "NYC", "dst": "TKY"})
```

---

## ⚡ Quick Start

```bash
python3 src/satellite_mesh.py
python3 tests/test_satellite_mesh.py
```
