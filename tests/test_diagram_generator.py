from pathlib import Path
import runpy


def test_infer_kind_reads_only_the_prefix_after_leading_whitespace(tmp_path: Path, monkeypatch) -> None:
    script = Path(__file__).parents[1] / "skills" / "diagram-generator" / "scripts" / "render_diagram.py"
    infer_kind = runpy.run_path(str(script))["infer_kind"]
    source = tmp_path / "diagram.source"
    source.write_text("  digraph G {" + ("x" * 1_000_000), encoding="utf-8")

    original_open = Path.open
    readers = []

    class TrackingReader:
        def __init__(self, file):
            self.file = file
            self.requested = 0

        def read(self, size: int = -1) -> str:
            assert size >= 0
            self.requested += size
            return self.file.read(size)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            self.file.close()

    def tracking_open(path: Path, *args, **kwargs):
        reader = TrackingReader(original_open(path, *args, **kwargs))
        readers.append(reader)
        return reader

    monkeypatch.setattr(Path, "open", tracking_open)

    assert infer_kind(source) == "graphviz"
    assert readers[0].requested <= 11
