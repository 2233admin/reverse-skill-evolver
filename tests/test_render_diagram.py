import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def renderer():
    """Load the standalone diagram renderer as an isolated module for each test."""
    script = Path(__file__).resolve().parents[1] / "skills/diagram-generator/scripts/render_diagram.py"
    spec = importlib.util.spec_from_file_location("render_diagram", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _track_source_reads(monkeypatch, source: Path) -> list[int]:
    """Keep real decoding/newline handling, but reject source-sized reads."""
    original_open = Path.open
    reads = []

    def tracked_open(path, mode="r", *args, **kwargs):
        """Wrap source reads for size tracking while leaving other file operations intact."""
        stream = original_open(path, mode, *args, **kwargs)
        if path == source and "r" in mode:
            original_read = stream.read

            def bounded_read(size=-1):
                """Reject unbounded or oversized reads and record each decoded chunk length."""
                assert 0 < size <= 64 * 1024, "source must be read in bounded chunks"
                data = original_read(size)
                reads.append(len(data))
                return data

            monkeypatch.setattr(stream, "read", bounded_read)
        return stream

    monkeypatch.setattr(Path, "open", tracked_open)
    return reads


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("@startuml", "plantuml"), ("digraph", "graphviz"), ("graph", "graphviz"),
     ("<svg", "svg"), ("sequenceDiagram", "mermaid")],
)
def test_infer_kind_stops_after_decisive_prefix(renderer, tmp_path, monkeypatch, prefix, expected):
    """Verify a decisive prefix avoids reading the remainder of a large source."""
    source = tmp_path / "diagram.unknown"
    source.write_text(prefix + "x" * (1024 * 1024), encoding="utf-8")
    reads = _track_source_reads(monkeypatch, source)

    assert renderer.infer_kind(source) == expected
    assert 0 < sum(reads) < source.stat().st_size


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("\u2003 \t\r\n" * 20000 + "@startuml", "plantuml"),
        (" " * 4093 + "digraph", "graphviz"),
        (" " * 4095 + "graph", "graphviz"),
        (" " * 4094 + "<svg", "svg"),
        (" \n\t" * 20000, "mermaid"),
        ("", "mermaid"),
        ("@startum", "mermaid"),
        ("Graph", "mermaid"),
        ("\ufeff@startuml", "mermaid"),
    ],
    ids=[
        "unicode-whitespace",
        "near-limit-digraph",
        "near-limit-graph",
        "near-limit-svg",
        "whitespace-only",
        "empty",
        "incomplete-plantuml",
        "case-sensitive-graph",
        "bom-fallback",
    ],
)
def test_infer_kind_preserves_whitespace_and_fallback(renderer, tmp_path, monkeypatch, content, expected):
    """Verify chunk boundaries, leading whitespace, and unrecognized prefixes preserve detection."""
    source = tmp_path / "diagram.unknown"
    source.write_text(content, encoding="utf-8", newline="")
    _track_source_reads(monkeypatch, source)

    assert renderer.infer_kind(source) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"\xff@startuml", "mermaid"), (b"@startuml\xff", "plantuml"),
     (b" \xc2", "mermaid"), (b"\n<svg\xff", "svg")],
)
def test_infer_kind_replaces_malformed_utf8(renderer, tmp_path, content, expected):
    """Verify malformed UTF-8 is replaced during prefix detection instead of raising."""
    source = tmp_path / "diagram.unknown"
    source.write_bytes(content)

    assert renderer.infer_kind(source) == expected


def test_infer_kind_known_extension_does_not_open_source(renderer, tmp_path, monkeypatch):
    """Verify a recognized extension selects the renderer without opening the source."""
    source = tmp_path / "diagram.PUML"

    def unexpected_open(*args, **kwargs):
        """Fail if extension-based detection attempts to read source content."""
        raise AssertionError("known extensions must not inspect content")

    monkeypatch.setattr(Path, "open", unexpected_open)
    assert renderer.infer_kind(source) == "plantuml"


def _select_plantuml_backend(renderer, tmp_path, monkeypatch, backend):
    """Stub CLI or Java JAR discovery and return the expected command prefix."""
    jar = tmp_path / "plantuml.jar"
    jar.touch()
    monkeypatch.setenv("PLANTUML_JAR", str(jar))
    monkeypatch.setattr(
        renderer.shutil, "which",
        lambda name: name if name == "java" or (name == "plantuml" and backend == "cli") else None,
    )
    return ["plantuml"] if backend == "cli" else ["java", "-jar", str(jar)]


@pytest.mark.parametrize("backend", ["cli", "jar"])
@pytest.mark.parametrize("alternate_output", [False, True])
def test_plantuml_streams_validated_normalized_source_and_copies_output(
    renderer, tmp_path, monkeypatch, backend, alternate_output,
):
    """Verify bounded source staging, newline normalization, output copying, and temporary cleanup."""
    source = tmp_path / "diagram.puml"
    source.write_bytes(b"@startuml\r\n" + ("Alice -> Bob: caf\u00e9\r" * 10000).encode("utf-8") + b"@enduml\n")
    expected = ("@startuml\n" + "Alice -> Bob: caf\u00e9\n" * 10000 + "@enduml\n").replace("\n", os.linesep).encode("utf-8")
    out = tmp_path / "rendered.svg"
    command_prefix = _select_plantuml_backend(renderer, tmp_path, monkeypatch, backend)
    reads = _track_source_reads(monkeypatch, source)
    staged_paths = []

    def render(cmd, cwd=None):
        """Check the staged command and normalized source, then create a synthetic renderer output."""
        staged = Path(cmd[-1])
        staged_paths.append(staged)
        assert cmd == command_prefix + ["-tsvg", str(staged)]
        assert cwd == staged.parent
        assert staged.name == source.name
        assert staged.parent != source.parent
        assert staged.read_bytes() == expected
        assert len(reads) > 1
        produced = staged.parent / "alternate.svg" if alternate_output else staged.with_suffix(".svg")
        produced.write_bytes(b"<svg>rendered</svg>")

    monkeypatch.setattr(renderer, "run", render)
    renderer.render_plantuml(source, out, "svg")

    assert out.read_bytes() == b"<svg>rendered</svg>"
    assert len(staged_paths) == 1
    assert not staged_paths[0].parent.exists()


@pytest.mark.parametrize("backend", ["cli", "jar"])
def test_plantuml_rejects_malformed_utf8_before_invoking_renderer(renderer, tmp_path, monkeypatch, backend):
    """Verify invalid source encoding prevents rendering and preserves existing output."""
    source = tmp_path / "diagram.puml"
    source.write_bytes(b"@startuml\n" + b"x" * (128 * 1024) + b"\xff")
    out = tmp_path / "rendered.svg"
    out.write_bytes(b"existing output")
    _select_plantuml_backend(renderer, tmp_path, monkeypatch, backend)
    _track_source_reads(monkeypatch, source)

    def unexpected_render(*args, **kwargs):
        """Fail if malformed source reaches the external renderer."""
        raise AssertionError("malformed UTF-8 must not reach the renderer")

    monkeypatch.setattr(renderer, "run", unexpected_render)
    with pytest.raises(UnicodeDecodeError):
        renderer.render_plantuml(source, out, "svg")
    assert out.read_bytes() == b"existing output"
