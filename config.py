"""Configuration for SPEC CPU benchmark runner.

To add a new allocator: append an Allocator entry to _ALLOCATOR_LIST.
To add a new SPEC version: append a SpecVersion entry to _SPEC_VERSION_LIST.
To add a new measurement tool: add an entry to TOOLS.
"""

from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()
PROJ_ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Allocator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Allocator:
    """A memory allocator that can be injected via LD_PRELOAD."""
    name: str
    # Ordered list of .so paths to inject. None = glibc baseline (no preload).
    libs: tuple[str, ...] | None = None

    @property
    def ld_preload(self) -> str | None:
        """Space-separated .so paths for LD_PRELOAD, or None."""
        return " ".join(self.libs) if self.libs else None


def _proj(*parts: str) -> str:
    return str(PROJ_ROOT.joinpath(*parts))


def _home(*parts: str) -> str:
    return str(HOME.joinpath(*parts))


_ALLOCATOR_LIST: list[Allocator] = [
    Allocator("glibc"),   # baseline: no preload, cleared environment
    Allocator("ffmalloc",   (_proj("src/vanilla-ffmalloc/libffmallocnpmt.so"),)),
    Allocator("ffmalloc+",  (_proj("src/ffmalloc+/libffmallocnpmt.so"),)),
    Allocator("lfmalloc",   (_proj("src/lfmalloc/libffmallocnpmt.so"),)),
    Allocator("msfmalloc",  (_proj("src/msfmalloc/libffmallocnpmt.so"),)),
    Allocator("mimalloc",   (_proj("src/mimalloc/build/libmimalloc.so"),)),
    Allocator("jemalloc", (
        _proj("src/minesweeper/lib/libdl.so"),
        _proj("src/minesweeper/lib/libjemalloc.so"),
    )),
    Allocator("minesweeper", (
        _proj("src/minesweeper/lib/libdl.so"),
        _proj("src/minesweeper/lib/libjemalloc.so"),
        _proj("src/minesweeper/lib/libminesweeper.so"),
    )),
    Allocator("markus", (
        _home("markus-allocator/lib/libgc.so"),
        _home("markus-allocator/lib/libgccpp.so"),
    )),
]

ALLOCATORS: dict[str, Allocator] = {a.name: a for a in _ALLOCATOR_LIST}

# Default order for `spec.py run` (no explicit allocator given)
DEFAULT_RUN_ORDER: list[str] = [
    "ffmalloc", "minesweeper", "jemalloc", "markus", "glibc", "ffmalloc+",
]


# ---------------------------------------------------------------------------
# SPEC version
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpecVersion:
    """Configuration for a specific SPEC CPU release."""
    id: str
    # Root used at run-time (shrc, specinvoke live here)
    root: Path
    # Root used for building (runspec/runcpu; may differ from root in 2006)
    build_root: Path
    # Path relative to root that contains per-benchmark directories
    bench_subdir: str
    # Suffix appended to "run_base_{size}_{config}" to form the run-dir name
    run_suffix: str
    # File listing benchmarks to process
    bench_list: Path
    # SPEC config filename (looked up in $SPEC/config/ by SPEC tools)
    config_file: str
    # Whether to strip the two trailing status-check lines from specinvoke output
    trim_tail: bool = False


_SPEC_VERSION_LIST: list[SpecVersion] = [
    SpecVersion(
        id="2006",
        root=HOME / "spec2006",
        build_root=HOME / "cpu2006/spec",
        bench_subdir="benchspec/CPU2006",
        run_suffix=".0000",
        bench_list=PROJ_ROOT / "spec2006/bench-list",
        config_file="default.cfg",
        trim_tail=False,
    ),
    SpecVersion(
        id="2017",
        root=HOME / "cpu2017",
        build_root=HOME / "cpu2017",
        bench_subdir="benchspec/CPU",
        run_suffix="-m64.0000",
        bench_list=PROJ_ROOT / "spec2017/bench-list",
        config_file="baseline.cfg",
        trim_tail=True,
    ),
]

SPEC_VERSIONS: dict[str, SpecVersion] = {v.id: v for v in _SPEC_VERSION_LIST}


# ---------------------------------------------------------------------------
# Measurement tools
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tool:
    """A measurement tool prepended to each benchmark command."""
    name: str
    # Command prefix; use {output} as placeholder for the result file path.
    prefix: str


_TOOL_LIST: list[Tool] = [
    Tool("time", "/usr/bin/time -v -o {output}"),
    # perf: extend EVENTS / options as needed
    Tool("perf",  "perf stat -o {output}"),
]

TOOLS: dict[str, Tool] = {t.name: t for t in _TOOL_LIST}
