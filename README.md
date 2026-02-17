# SPEC CPU 2006/2017 Benchmark Runner

A unified Python toolkit for running SPEC CPU 2006 and 2017 benchmarks with custom memory allocators injected via `LD_PRELOAD`.

## File Structure

```
SPEC_CPU/
├── spec.py              # Unified CLI (setup / run / build / parse)
├── config.py            # Allocator, SPEC version, and tool definitions
├── utils.py             # Shared helpers (SPEC environment loader)
├── scripts/
│   └── cpu-setting.sh   # Set CPU scaling governor to performance
├── spec2006/
│   ├── bench-list       # Benchmarks to run for SPEC CPU 2006
│   └── default.cfg      # SPEC 2006 compiler/run configuration
└── spec2017/
    ├── bench-list       # Benchmarks to run for SPEC CPU 2017
    └── baseline.cfg     # SPEC 2017 compiler/run configuration
```

## Prerequisites

- SPEC CPU 2006 installed at `~/spec2006` (runtime) and `~/cpu2006/spec` (build)
- SPEC CPU 2017 installed at `~/cpu2017`
- Allocator `.so` files built under `src/` (see `config.py` for expected paths)

## Quick Start

### 1. Build benchmarks (first time only)

```bash
python3 spec.py build 2006
python3 spec.py build 2017
```

### 2. Generate invocation scripts

For each allocator you want to test, generate the benchmark shell scripts:

```bash
python3 spec.py setup <version> <size> <allocator> <tool>
```

| Argument    | Values |
|-------------|--------|
| `version`   | `2006`, `2017` |
| `size`      | `ref`, `refspeed`, `train`, `test` |
| `allocator` | `glibc`, `ffmalloc`, `ffmalloc+`, `lfmalloc`, `msfmalloc`, `mimalloc`, `jemalloc`, `minesweeper`, `markus` |
| `tool`      | `time`, `perf` |

Examples:

```bash
python3 spec.py setup 2006 ref glibc time
python3 spec.py setup 2017 refspeed markus time
```

This creates `<allocator>/bench-script/` in the current directory, with one executable shell script per benchmark.

### 3. Run benchmarks

Run a specific allocator:

```bash
python3 spec.py run ffmalloc
```

Run multiple allocators in one go:

```bash
python3 spec.py run ffmalloc markus glibc
```

Run all allocators in the default order (`ffmalloc`, `minesweeper`, `jemalloc`, `markus`, `glibc`, `ffmalloc+`):

```bash
python3 spec.py run
```

### 4. Parse results

After running, parse the `/usr/bin/time -v` result files:

```bash
python3 spec.py parse <allocator-dir>
```

Example:

```bash
python3 spec.py parse glibc
```

Output (tab-separated):

```
<benchmark>    <wall_time_seconds>    <max_rss_kb>
```

## Configuration

All allocator paths, SPEC version settings, and measurement tools are defined in `config.py`.

**Adding a new allocator** — append one line to `_ALLOCATOR_LIST`:

```python
Allocator("myalloc", (_proj("src/myalloc/libmyalloc.so"),)),
```

**Adding a new SPEC version** — append one entry to `_SPEC_VERSION_LIST`:

```python
SpecVersion(
    id="2021",
    root=HOME / "cpu2021",
    build_root=HOME / "cpu2021",
    bench_subdir="benchspec/CPU",
    run_suffix="-m64.0000",
    bench_list=PROJ_ROOT / "spec2021/bench-list",
    config_file="baseline.cfg",
    trim_tail=True,
),
```

**Adding a new measurement tool** — append one entry to `_TOOL_LIST`:

```python
Tool("vtune", "vtune -collect hotspots -result-dir {output}"),
```
