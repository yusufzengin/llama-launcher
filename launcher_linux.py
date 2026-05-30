#!/usr/bin/env python3
"""
launcher_linux.py - Linux entry point.
Model files may live on a Windows drive (D:\\...) and are accessed via /mnt/d/...
Binaries are native Linux builds pointed to by LINUX_LLAMA_BIN_STABLE / LINUX_LLAMA_BIN_LATEST.

Environment variables (set in ~/.bashrc):
  LLAMA_MODELS             - Windows or Linux path to model directory (auto-translated if Windows)
  LINUX_LLAMA_BIN_STABLE   - Linux path, e.g. /home/user/llama-stable/build/bin
  LINUX_LLAMA_BIN_LATEST   - Linux path, e.g. /home/user/llama-latest/build/bin
"""

import os
import subprocess
import sys
from pathlib import Path

from common import load_config, load_env_file, run

REQUIRED_ENV = ["LLAMA_MODELS", "LINUX_LLAMA_BIN_STABLE", "LINUX_LLAMA_BIN_LATEST"]

# Maps Windows .exe names to Linux binary names
EXECUTABLE_MAP = {
    "llama-server.exe": "llama-server",
    "llama-bench.exe":  "llama-bench",
}


# Platform hooks

def check_env_vars():
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print("\n  Missing environment variables:")
        for v in missing:
            print(f"    ✗ {v}")
        print("\n  Add them to ~/.bashrc:")
        print('    export LLAMA_MODELS="D:\\\\path\\\\to\\\\models"')
        print('    export LINUX_LLAMA_BIN_STABLE="/home/user/llama-stable/build/bin"')
        print('    export LINUX_LLAMA_BIN_LATEST="/home/user/llama-latest/build/bin"')
        print("\n  Or add them to a .env file next to launcher_linux.py.")
        sys.exit(1)


def win_to_linux(path: str) -> str:
    """
    Translate a Windows path to its /mnt/ equivalent for WSL2.
    'D:\\llama\\models' -> '/mnt/d/llama/models'
    Paths already in Unix form are returned unchanged.
    """
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        rest  = path[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return path


def resolve(value: str) -> str:
    """Expand env vars, then translate Windows paths to Linux mount paths."""
    return win_to_linux(os.path.expandvars(str(value)))


def get_executable(runtime_path, profile):
    """Map .exe name to the Linux binary name and return the full path."""
    linux_name = EXECUTABLE_MAP.get(profile["executable"], profile["executable"].replace(".exe", ""))
    return str(Path(runtime_path) / linux_name)


def validate(executable, profile, model_variant, tunables):
    errors = []

    if not Path(executable).exists():
        errors.append(f"Executable not found: {executable}")
    elif not os.access(executable, os.X_OK):
        errors.append(f"Executable is not executable: {executable}")

    model_path = resolve(model_variant["model"])
    if not Path(model_path).exists():
        errors.append(f"Model not found: {model_path}")

    if tunables.get("mmproj") and "mmproj" in model_variant:
        mmproj_path = resolve(model_variant["mmproj"])
        if not Path(mmproj_path).exists():
            errors.append(f"mmproj not found: {mmproj_path}")

    return errors


# Entry point

def main():
    load_env_file()
    check_env_vars()

    config = load_config()

    # Runtime keys come from config; values are substituted from Linux env vars
    runtimes = {k: resolve(v["linux"]) for k, v in config["runtimes"].items()}

    command = run(
        config            = config,
        runtimes          = runtimes,
        resolve_fn        = resolve,
        get_executable_fn = get_executable,
        validate_fn       = validate,
    )

    print()
    try:
        subprocess.run(command)
    except Exception as e:
        print(f"\n{type(e).__name__}: {e}")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)