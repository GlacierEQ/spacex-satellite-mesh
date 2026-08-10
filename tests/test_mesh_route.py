"""Tests drive shipped mesh_route.shortest_path — no magic ANSWER constants."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mesh_route import shortest_path  # noqa: E402


class MeshRouteTests(unittest.TestCase):
    def test_shortest_path_linear_graph(self) -> None:
        g = {"A": {"B": 1.0}, "B": {"C": 1.0}, "C": {}}
        r = shortest_path(g, "A", "C")
        self.assertTrue(r["ok"])
        self.assertEqual(r["path"], ["A", "B", "C"])
        self.assertEqual(r["cost"], 2.0)

    def test_unreachable(self) -> None:
        g = {"A": {"B": 1.0}, "B": {}, "C": {}}
        r = shortest_path(g, "A", "C")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
