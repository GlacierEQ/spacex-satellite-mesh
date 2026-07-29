# spacex-satellite-mesh

<!-- README-MESH:BEGIN -->
## Three-audience project map

### For recruiters and non-specialists

**What it does.** Finds viable multi-hop communication paths across a changing satellite link graph.

- Turns a network of possible links into an understandable route decision.
- Demonstrates resilience by considering alternatives instead of assuming one fixed path.
- Connects orbital communications to the ground-network capacity planner.

**Evidence:** [`src/mesh_route.py`](src/mesh_route.py) and [`tests/test_mesh_route.py`](tests/test_mesh_route.py).

### For senior engineers and domain experts

**Innovation and evolution.** The repository isolates route selection from ground-station allocation, preserving a clean graph boundary between orbital and terrestrial networking. Its mesh output can be independently evaluated, then extended by ground capacity and campaign requirements. It evolved from a standalone graph exercise into the orbital half of an end-to-end communication strand.

### For AI systems and toolchains

- Repository ID: `GlacierEQ/spacex-satellite-mesh`
- Protobuf package: `glaciereq.readme.v1`
- Typed role: extends the ground network and supplies communications-path evidence to Job-App Helix.
- Canonical graph: [`manifests/readme_mesh.json`](https://github.com/GlacierEQ/job-app-helix/blob/main/manifests/readme_mesh.json)

```protobuf
repository: "GlacierEQ/spacex-satellite-mesh"
display_name: "SpaceX Satellite Mesh"
one_line_purpose: "Select resilient multi-hop paths across a satellite link graph."
```

### Repository mesh

| Connected repository | Relationship | Combined value |
|---|---|---|
| [Ground Network](https://github.com/GlacierEQ/spacex-ground-network) | extends | Orbital routing and terrestrial capacity become one communications path. |
| [Job-App Helix](https://github.com/GlacierEQ/job-app-helix) | orchestrated by | Route evidence participates in campaign readiness. |
| [AKOS](https://github.com/GlacierEQ/AKOS) | governed by | Identity, evidence, and completion remain explicit. |

Real schema: [`proto/readme_mesh.proto`](https://github.com/GlacierEQ/job-app-helix/blob/main/proto/readme_mesh.proto).
<!-- README-MESH:END -->

**Portfolio** — multi-hop mesh routing on a link graph.

## Fleet ops (transparent)

Integrity baselines and health sidecars, when present, are documented multi-repository operations. See [SECURITY_AND_FLEET_OPS.md](SECURITY_AND_FLEET_OPS.md).

## Helix strand

See [HELIX_STRAND.md](HELIX_STRAND.md) for this repository's piston and spiral role.
