# HELIX Architecture — spacex-satellite-mesh

## Double Helix Pattern

**Alpha (What)** — Pure physics models, stateless computation
- mesh_routing

**Omega (How)** — Controllers, orchestration, stateful management  
- constellation_manager,temporal_routing

## Design Principles

- Zero external dependencies (stdlib only)
- Stateless alpha, stateful omega
- SHA-256 file integrity verification
- Shadow watchdog daemon monitoring
- Mastermind sidecar coordination

## Data Flow

```
Alpha Models → Omega Controllers → Mastermind Sidecar → Shadow Infrastructure
```
