#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

from common import load_config, load_env_file, run

REQUIRED_ENV = ["LLAMA_MODELS", "LLAMA_BIN_STABLE", "LLAMA_BIN_LATEST"]


# Platform hooks

def check_env_vars():
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print("\n  Missing environment variables:")
        for v in missing:
            print(f"    ✗ {v}")
        print("\n  Set them in a .env file next to launcher_windows.py:")
        print('    LLAMA_MODELS=D:\\path\\to\\models')
        print('    LLAMA_BIN_STABLE=D:\\llama\\stable\\build\\bin\\Release')
        print('    LLAMA_BIN_LATEST=D:\\llama\\latest\\build\\bin\\Release')
        print("\n  Or set them as Windows user environment variables.")
        sys.exit(1)


def resolve(value):
    """Expand %WINDOWS_ENV_VARS% in paths."""
    return os.path.expandvars(str(value))


def get_executable(runtime_path, profile):
    return str(Path(runtime_path) / profile["executable"])


def validate(executable, profile, model_variant, tunables):
    errors = []

    if not Path(executable).exists():
        errors.append(f"Executable not found: {executable}")

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

    config   = load_config()
    runtimes = {k: resolve(v) for k, v in config["runtimes"].items()}

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