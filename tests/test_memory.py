from pathlib import Path
from acumen.memory import MemoryStore

def test_memory_search(tmp_path: Path):
    m = MemoryStore(tmp_path)
    m.add("Ottawa is the capital of Canada.", confidence=0.9)
    results = m.search("capital Canada")
    assert results
    assert "Ottawa" in results[0]["text"]
