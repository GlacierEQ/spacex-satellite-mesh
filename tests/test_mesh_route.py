import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from mesh_route import shortest_path, ANSWER

def test_path():
    g = {"A": {"B": 1}, "B": {"C": 1}, "C": {}}
    r = shortest_path(g, "A", "C")
    assert r["ok"] and r["path"]==["A","B","C"] and r["answer"]==ANSWER

if __name__=="__main__":
    test_path(); print("ok")
