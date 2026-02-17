"""Shared utilities for SPEC CPU benchmark runner."""

import shutil
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
    # shrc checks for bin/runspec relative to CWD, so we must cd into spec_root
    # first — mirroring the original `pushd $SPEC_ROOT && source shrc` pattern.
    # Redirect shrc's own stdout/stderr to /dev/null so that warning messages
    # (e.g. "benchmark tree not yet installed") do not corrupt the env -0 output
    # that we parse below.
    cmd = f'cd "{spec_root}" && source "{shrc}" >/dev/null 2>&1 && env -0'
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


def check_spec_install(spec_root: Path, install_marker: str) -> None:
    """Abort with a clear message if install.sh has not been run.

    SPEC tools (runspec, specinvoke) require a one-time install step that
    unpacks platform-specific binaries.  Without it every tool invocation
    fails with a cryptic 'No such file or directory' on the shebang line.

    install_marker is a path relative to spec_root that only exists after
    install.sh completes (e.g. 'bin/specinvoke' for 2006, 'bin/specperl'
    for 2017).
    """
    marker = spec_root / install_marker
    if not marker.exists():
        print(
            f"SPEC at '{spec_root}' has not been installed yet.\n"
            f"  Please run:  cd {spec_root} && sh install.sh",
            file=sys.stderr,
        )
        sys.exit(1)


def spec_run(
    cmd: list[str],
    env: dict[str, str],
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run a SPEC tool, resolving its path via the SPEC environment's PATH.

    When subprocess.run receives an explicit env dict it uses execve internally,
    which does NOT search PATH — the executable must be an absolute path.
    This wrapper resolves the bare tool name (e.g. 'runspec', 'specinvoke')
    through the PATH captured from shrc before handing off to subprocess.run.
    """
    exe = shutil.which(cmd[0], path=env.get("PATH", ""))
    if exe is None:
        print(
            f"'{cmd[0]}' not found in SPEC PATH.\n"
            f"  PATH={env.get('PATH')}",
            file=sys.stderr,
        )
        sys.exit(1)
    return subprocess.run([exe, *cmd[1:]], env=env, **kwargs)
