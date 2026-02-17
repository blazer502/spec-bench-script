#!/usr/bin/env python3
"""Unified SPEC CPU 2006/2017 benchmark runner.

Subcommands
-----------
  setup   Generate per-benchmark invocation scripts injected with a
          measurement tool and (optionally) an allocator via LD_PRELOAD.

  run     Execute previously generated scripts for one or more allocators.
          Omitting the allocator argument runs all in DEFAULT_RUN_ORDER.

  build   Build SPEC benchmarks using runspec/runcpu (--action runsetup).

  parse   Parse /usr/bin/time -v result files and print a TSV summary.

Examples
--------
  python3 spec.py setup 2006 ref glibc time
  python3 spec.py setup 2017 refspeed markus time
  python3 spec.py run ffmalloc markus
  python3 spec.py run                     # all allocators in default order
  python3 spec.py build 2006
  python3 spec.py parse glibc
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from config import (
    ALLOCATORS, DEFAULT_RUN_ORDER, SPEC_VERSIONS, TOOLS,
    Allocator, SpecVersion, Tool,
)
from utils import check_spec_install, source_shrc, spec_run

SCRIPTS_DIR = Path(__file__).parent / "scripts"
BENCH_CONFIG = "baseline"


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def _inject_commands(
    outfile: Path,
    allocator: Allocator,
    size: str,
    tool: Tool,
    work_dir: Path,
) -> None:
    """Rewrite outfile, prepending tool + allocator injection to each benchmark command.

    specinvoke -nn emits line pairs:
        cd /absolute/path/to/run/dir
        ./binary [args] > stdout 2> stderr

    We locate every 'cd /' line and modify the immediately following command line.
    Using `^cd /` (rather than the original `cd /home`) makes this independent of
    the SPEC install path.
    """
    lines = outfile.read_text().splitlines()
    bench_name = outfile.stem.split("-")[0]  # "473.astar" from "473.astar-ref-baseline"

    cd_indices = [i for i, ln in enumerate(lines) if re.match(r"^cd /", ln)]
    print(f"  {bench_name}: {len(cd_indices)} invocation(s)")

    for run_idx, cd_idx in enumerate(cd_indices, start=1):
        cmd_idx = cd_idx + 1
        if cmd_idx >= len(lines):
            continue

        cmd = lines[cmd_idx]
        res_dir = work_dir / allocator.name / bench_name / "result"
        res_dir.mkdir(parents=True, exist_ok=True)
        res_file = res_dir / f"{bench_name}-{run_idx}-{size}-{BENCH_CONFIG}.res"

        tool_prefix = tool.prefix.format(output=res_file)

        if allocator.ld_preload:
            lines[cmd_idx] = f'{tool_prefix} env LD_PRELOAD="{allocator.ld_preload}" {cmd}'
        else:
            # glibc baseline: clear environment to prevent accidental preloads
            lines[cmd_idx] = f"{tool_prefix} env -i {cmd}"

    outfile.write_text("\n".join(lines) + "\n")
    outfile.chmod(outfile.stat().st_mode | 0o111)


def cmd_setup(args: argparse.Namespace) -> None:
    spec: SpecVersion = SPEC_VERSIONS[args.version]
    check_spec_install(spec.root, spec.install_marker)
    allocator: Allocator = ALLOCATORS[args.allocator]
    tool: Tool = TOOLS[args.tool]
    size: str = args.size

    benchmarks = [
        ln.strip()
        for ln in spec.bench_list.read_text().splitlines()
        if ln.strip()
    ]

    scripts_dir = Path(f"{allocator.name}/bench-script")
    scripts_dir.mkdir(parents=True, exist_ok=True)
    print(f"bench-script dir: {scripts_dir}")

    env = source_shrc(spec.root)
    work_dir = Path.cwd()

    for bench in benchmarks:
        run_dir = (
            spec.root / spec.bench_subdir / bench / "run"
            / f"run_base_{size}_{BENCH_CONFIG}{spec.run_suffix}"
        )
        outfile = work_dir / scripts_dir / f"{bench}-{size}-{BENCH_CONFIG}.sh"

        print(f"{bench}...")

        result = spec_run(
            ["specinvoke", "-nn"],
            env=env,
            cwd=run_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  specinvoke failed:\n{result.stderr}", file=sys.stderr)
            continue

        outfile.write_text(result.stdout + "\n")

        if spec.trim_tail:
            # spec2017: specinvoke appends two trailing status-check lines
            lines = outfile.read_text().splitlines()
            while lines and not lines[-1].strip():
                lines.pop()
            lines = lines[:-2] if len(lines) >= 2 else lines
            outfile.write_text("\n".join(lines) + "\n")

        _inject_commands(outfile, allocator, size, tool, work_dir)
        print(f"{bench}...done")


# ---------------------------------------------------------------------------
# run  (subsumes run_all: omitting allocators runs the full default list)
# ---------------------------------------------------------------------------

def _set_cpu_performance() -> None:
    subprocess.run([str(SCRIPTS_DIR / "cpu-setting.sh")], capture_output=True)


def _run_one(name: str) -> None:
    bench_dir = Path(f"{name}/bench-script")
    if not bench_dir.exists():
        print(f"  missing bench-script dir: {bench_dir}", file=sys.stderr)
        return

    scripts = sorted(bench_dir.glob("*.sh"))
    if not scripts:
        print(f"  no scripts in {bench_dir}", file=sys.stderr)
        return

    print(f"\n=== {name} ===")
    for script in scripts:
        print(script.name)
        _set_cpu_performance()
        subprocess.run([str(script)], cwd=bench_dir)


def cmd_run(args: argparse.Namespace) -> None:
    targets = args.allocators if args.allocators else DEFAULT_RUN_ORDER
    for name in targets:
        if name not in ALLOCATORS:
            print(f"Unknown allocator '{name}'", file=sys.stderr)
            continue
        _run_one(name)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> None:
    spec: SpecVersion = SPEC_VERSIONS[args.version]
    check_spec_install(spec.build_root, spec.install_marker)
    env = source_shrc(spec.build_root)
    spec_run(
        [
            "runspec",
            f"--config={spec.config_file}",
            "--size=train",
            "--copies=1",
            "--noreportable",
            "--iterations=1",
            "--action", "runsetup",
            "--tune", "all",
            "int", "fp",
        ],
        env=env,
        cwd=spec.build_root,
        check=True,
    )


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def _parse_time_output(lines: list[str]) -> tuple[float, int, bool]:
    """Parse /usr/bin/time -v output. Returns (wall_seconds, max_rss_kb, signaled)."""
    total_time = 0.0
    vm_rss = 0

    for line in lines:
        if "signal" in line:
            return total_time, vm_rss, True
        if "Maximum resident set size" in line:
            vm_rss += int(line.split(":")[-1])
        if "Elapsed (wall clock) time" in line:
            parts = line.split()[-1].strip().split(":")
            if len(parts) == 3:
                h, mm, ss = parts
                total_time += float(h) * 3600 + float(mm) * 60 + float(ss)
            else:
                mm, ss = parts
                total_time += float(mm) * 60 + float(ss)

    return total_time, vm_rss, False


def cmd_parse(args: argparse.Namespace) -> None:
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    bench_dirs = sorted(d for d in root.iterdir() if d.is_dir() and d.name != "bench-script")

    for bench_dir in bench_dirs:
        result_dir = bench_dir / "result"
        if not result_dir.exists():
            continue

        total_time = 0.0
        vm_rss = 0
        is_signal = False

        for res_file in sorted(result_dir.iterdir()):
            t, r, sig = _parse_time_output(res_file.read_text().splitlines())
            if sig:
                is_signal = True
                break
            total_time += t
            vm_rss += r

        print(f"{bench_dir.name}\t{total_time}\t{vm_rss}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _version_choices() -> str:
    return " | ".join(SPEC_VERSIONS)


def _allocator_choices() -> str:
    return " | ".join(ALLOCATORS)


def _tool_choices() -> str:
    return " | ".join(TOOLS)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spec",
        description="SPEC CPU 2006/2017 benchmark runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="<subcommand>")

    # --- setup ---
    p = sub.add_parser("setup", help="generate benchmark invocation scripts")
    p.add_argument("version",   choices=SPEC_VERSIONS, metavar="version",
                   help=f"SPEC version ({_version_choices()})")
    p.add_argument("size",      metavar="size",
                   help="input size (ref | refspeed | train | test)")
    p.add_argument("allocator", choices=ALLOCATORS, metavar="allocator",
                   help=f"allocator ({_allocator_choices()})")
    p.add_argument("tool",      choices=TOOLS, metavar="tool",
                   help=f"measurement tool ({_tool_choices()})")
    p.set_defaults(func=cmd_setup)

    # --- run ---
    p = sub.add_parser(
        "run",
        help="run benchmark scripts (no allocator = all in default order)",
    )
    p.add_argument("allocators", nargs="*", metavar="allocator",
                   help="allocator(s) to run; omit to run all in default order")
    p.set_defaults(func=cmd_run)

    # --- build ---
    p = sub.add_parser("build", help="build SPEC benchmarks (runsetup)")
    p.add_argument("version", nargs="?", default="2006",
                   choices=SPEC_VERSIONS, metavar="version",
                   help=f"SPEC version (default: 2006; {_version_choices()})")
    p.set_defaults(func=cmd_build)

    # --- parse ---
    p = sub.add_parser("parse", help="parse time -v result files, print TSV summary")
    p.add_argument("path", help="allocator result directory (e.g. glibc/ or ffmalloc/)")
    p.set_defaults(func=cmd_parse)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
