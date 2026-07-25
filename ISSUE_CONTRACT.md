# Issue Contract — `spacex-satellite-mesh`

## Pain
Need multi-hop path on ISL graph when direct link missing.

## Claim
Dijkstra shortest_path finds path when connected; ok=false when not.

## Proof
```bash
python3 job-app/helix/proofs/proof_mesh_route.py
```

## Done when
Proof exits 0. Architecture (strand/integrity/helix) is **not** a substitute for this proof.

## Anti-claim
Not constellation flight software.
