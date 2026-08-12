# Satellite Mesh Routing Simulator

**Deterministic local inter-satellite routing, simplified constellation coverage, and delay-tolerant time-window routing with native Python and Rust proof.**

This is an independent GlacierEQ portfolio system. It is not affiliated with SpaceX. It does not control satellites or laser terminals, publish operational topology, guarantee message delivery, or represent a production constellation network.

## What now works

- validated in-memory satellite and inter-satellite-link topology;
- capacity-aware, active-state-aware minimum-latency routing;
- non-mutating enumeration of alternate simple paths;
- explicit bottleneck capacity and highest-load satellite reporting;
- simplified circular-orbit constellation geometry and deterministic local ISL construction;
- ground-slot coverage with primary/backup assignment and correct handoff tracking, including satellite ID `0`;
- deterministic temporal link windows computed only inside supplied trajectory coverage;
- physical nonzero propagation latency for modeled link windows;
- earliest-arrival delay-tolerant routes that can wait for a future link;
- no frozen extrapolation after the final trajectory sample;
- executable `satellite-mesh` JSON CLI for static and temporal scenarios;
- native Rust Dijkstra kernel with endpoint, link-state, capacity and latency-limit validation.

## Run it

```bash
python -m pip install -e . pytest
pytest -q
satellite-mesh demo
satellite-mesh temporal-demo

cargo check --all-targets
cargo test
```

## Architecture

```text
Satellite nodes + ISL state
          |
          v
  validated MeshTopology ----------> Rust routing kernel
          |
          +--> shortest viable route
          +--> alternate simple paths
          +--> capacity / load evidence

Simplified orbit planes
          |
          v
 constellation geometry --> coverage + handoff review

Supplied trajectories
          |
          v
 temporal link windows
          |
          v
 earliest-arrival router --> wait + propagate + deliverability result
```

## Core surfaces

| Surface | Function |
|---|---|
| `src/alpha/mesh_routing.py` | validated local topology, Dijkstra, capacity-aware routing, non-mutating alternates |
| `src/omega/constellation_manager.py` | simplified orbit-plane geometry, local ISL mesh, coverage and handoffs |
| `src/omega/temporal_routing.py` | trajectory interpolation, physical link windows and earliest-arrival routing |
| `src/satellite_mesh.py` | static/temporal JSON CLI and scenario validation |
| `src/routing_engine.rs` | native Rust route-selection kernel |
| `src/mesh_route.py` | small generic weighted-graph compatibility helper |
| `tests/test_crystallized_function.py` | routing state, saturation, handoff-zero, temporal-window, waiting and CLI tests |

## Corrected claims

The previous README advertised `src/satellite_mesh.py` and `src/routing_engine.rs`, but neither file existed. Both now exist and execute.

The previous repository also described:

- thousands-of-satellites production scaling;
- guaranteed delay-tolerant delivery;
- real laser-link behavior;
- orbital-dynamics validation sufficient for operational topology;
- a GNN traffic predictor;
- an MCP `route_query` tool;
- Mastermind/APEX live topology publication.

Those claims are not supported by the repository and are therefore not part of the crystallized contract. The current system is a deterministic **local simulation and routing toolkit** whose behavior is directly testable.

## Routing behavior

### Static mesh

A link is usable only when:

1. both endpoint satellites are active;
2. the link itself is active;
3. residual capacity is greater than zero; and
4. the candidate route stays under the requested latency ceiling.

`find_all_routes` searches simple paths without temporarily disabling nodes or links, so asking for alternatives cannot accidentally resurrect failed topology afterward.

### Temporal mesh

A trajectory is valid only over its supplied sample interval. The system interpolates inside that interval and returns no position outside it.

Link windows therefore derive only from modeled time coverage. Each window records a conservative in-window propagation latency rather than using the first out-of-range sample or a fabricated zero.

The time-expanded router selects earliest arrival and may wait at an intermediate satellite until an edge becomes available. A result means **deliverable in this supplied model horizon**, not guaranteed real-world delivery.

### Constellation geometry

`ConstellationManager` uses simplified circular-orbit planes for local simulation. It is not SGP4, a mission ephemeris service, or a digital twin of any commercial constellation. Its ISL construction is a deterministic demonstration rule: same-plane neighbors plus equal-index cross-plane peers.

## Language boundaries

```yaml
python:
  role:
    - topology and capacity state
    - constellation simulation
    - temporal routing
    - scenario orchestration
    - JSON CLI
rust:
  role:
    - native validated shortest-path kernel
    - low-overhead deterministic routing core
```

Rust exists because a compact native routing kernel is a meaningful systems boundary here. It is not decorative polyglot code.

## Machine contract

```yaml
schema: glaciereq.readme.v1
repository: GlacierEQ/spacex-satellite-mesh
purpose: deterministic local constellation mesh and temporal-routing simulation
state: FUNCTIONAL_CANDIDATE
verified_after_exact_head_ci:
  - validated static mesh routing
  - residual-capacity enforcement
  - non-mutating alternate-path enumeration
  - simplified constellation coverage and handoff simulation
  - trajectory-bounded temporal link windows
  - earliest-arrival delay-tolerant routing
  - Python static and temporal JSON CLI
  - Rust native routing kernel
promotion_requires:
  - Python 3.11 full functional proof
  - Python 3.12 full functional proof
  - Python 3.13 full functional proof
  - Rust cargo check
  - Rust unit tests
  - static and temporal CLI smoke
  - required-functional-proof
nonclaims:
  - no SpaceX affiliation
  - no spacecraft or laser-terminal authority
  - no production constellation-scale claim
  - no guaranteed delivery
  - no live MCP or APEX integration
  - no GNN traffic predictor
```

**The product is routing behavior that can be executed and disproven, not a README describing a network that does not exist.**
