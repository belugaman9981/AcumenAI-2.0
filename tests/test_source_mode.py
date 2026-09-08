from pathlib import Path
from tempfile import TemporaryDirectory
from acumen.client import AcumenClient
from acumen.config import DEFAULTS

def test_source_toggle():
    with TemporaryDirectory() as d:
        c = AcumenClient("local", Path(d), DEFAULTS)
        sample = {
            "answer": "Example answer.",
            "sources": [{"title": "Example", "url": "https://example.com"}],
        }
        assert "Sources:" in c._format(sample)
        assert c.chat("/hide-source") == "Sources are now hidden."
        assert c._format(sample) == "Example answer."
        assert c.chat("/show-source") == "Sources are now shown."
        assert "Sources:" in c._format(sample)
