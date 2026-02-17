"""Shared utilities for SPEC CPU benchmark runner."""

import subprocess
import sys
from pathlib import Path


def source_shrc(spec_root: Path) -> dict[str, str]:
    """Source the SPEC shrc file and return the resulting environment.

    SPEC tools (runspec, specinvoke, runcpu, etc.) require environment
    variables set by shrc. This function sources it in a subshell and
    captures the resulting env so it can be passed to subprocess calls.
    """
    shrc = spec_root / "shrc"
    cmd = f'source "{shrc}" && env -0'
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to source {shrc}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    env: dict[str, str] = {}
    for entry in result.stdout.split("\0"):
        if "=" in entry:
            key, _, val = entry.partition("=")
            env[key] = val
    return env
