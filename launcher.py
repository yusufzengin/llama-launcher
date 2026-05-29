import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_FILE    = Path(__file__).parent / "config.json"
LAST_USED_FILE = Path(__file__).parent / "last_used.json"

TUNABLE_FLAGS = {
    "ctx":       "-c",
    "batch":     "--batch-size",
    "ubatch":    "--ubatch-size",
    "threads":   "--threads",
    "n_cpu_moe": "--n-cpu-moe",
    "mmproj":    None,  # handled separately
}

TUNABLE_LABELS = {
    "ctx":       "Context size",
    "batch":     "Batch size",
    "ubatch":    "Ubatch size",
    "threads":   "Threads",
    "n_cpu_moe": "CPU MOE layers",
    "mmproj":    "Vision (mmproj)",
}

REQUIRED_ENV   = ["LLAMA_MODELS", "LLAMA_BIN_STABLE", "LLAMA_BIN_LATEST"]
BACK           = object()
LAST_USED      = object()


# Env / config

def load_env_file():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_last_used():
    try:
        with open(LAST_USED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_last_used(runtime_name, profile_name, model_name, tunables=None):
    with open(LAST_USED_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "runtime": runtime_name,
            "profile": profile_name,
            "model":   model_name,
            "tunables": tunables or {}
        }, f)


def check_env_vars():
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print("\n  Missing environment variables:")
        for v in missing:
            print(f"    ✗ {v}")
        print("\n  Set them in a .env file next to launcher.py:")
        print('    LLAMA_MODELS=D:\\path\\to\\models')
        print('    LLAMA_BIN_STABLE=D:\\llama\\stable\\build\\bin\\Release')
        print('    LLAMA_BIN_LATEST=D:\\llama\\latest\\build\\bin\\Release')
        print("\n  Or set them as Windows user environment variables.")
        sys.exit(1)


def validate_last_used(last, runtimes, profiles):
    if not last:
        return False
    if last["runtime"] not in runtimes:
        return False
    matched = next((p for p in profiles if p["name"] == last["profile"]), None)
    if not matched:
        return False
    if last["model"] not in matched.get("models", {}):
        return False
    return True


# Env var resolution

def resolve(value):
    return os.path.expandvars(str(value))


def resolve_args(args):
    return [resolve(a) for a in args]


# Validation

def validate(runtime_path, profile, model_variant, tunables):
    errors = []

    executable = Path(resolve(runtime_path)) / profile["executable"]
    if not executable.exists():
        errors.append(f"Executable not found: {executable}")

    model_path = resolve(model_variant["model"])
    if not Path(model_path).exists():
        errors.append(f"Model not found: {model_path}")

    if tunables.get("mmproj") and "mmproj" in model_variant:
        mmproj_path = resolve(model_variant["mmproj"])
        if not Path(mmproj_path).exists():
            errors.append(f"mmproj not found: {mmproj_path}")

    return errors


# UI helpers

def choose_option(title, options, labels=None, can_go_back=False):
    display = labels if labels else options
    while True:
        print(f"\n=== {title} ===\n")
        for i, label in enumerate(display, start=1):
            print(f"  {i}. {label}")
        print()
        if can_go_back:
            print("  B. Back")
        print("  X. Exit")

        choice = input("\nSelect: ").strip().lower()

        if choice == "x":
            sys.exit(0)
        if choice == "b" and can_go_back:
            return BACK
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("Invalid selection.")


def print_profile_info(profile, model_name, model_variant):
    tags      = profile.get("tags", [])
    notes     = profile.get("notes", [])

    if tags:
        print(f"  Tags      : {', '.join(tags)}")
    print(f"  Model     : {model_name}", end="")
    if model_variant.get("mtp"):
        print("  [MTP]", end="")
    print()
    if notes:
        print("  Notes     :")
        for note in notes:
            print(f"    - {note}")


def print_command_preview(command):
    print("\n--- Command ---\n")
    print(f"  {command[0]}\n")
    args = command[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-") and i + 1 < len(args) and not args[i + 1].startswith("-"):
            print(f"    {arg:<20} {args[i + 1]}")
            i += 2
        else:
            print(f"    {arg}")
            i += 1


# Tunables

def merge_tunables(defaults, profile_tunables):
    merged = {}
    for key in TUNABLE_FLAGS:
        if key in profile_tunables:
            merged[key] = profile_tunables[key]
        elif key in defaults:
            merged[key] = defaults[key]
    return merged


def display_tunables(tunables):
    print("\n  Current tunables:\n")
    for i, (key, value) in enumerate(tunables.items(), start=1):
        label = TUNABLE_LABELS.get(key, key)
        print(f"  {i}. {label:<25} {value}")


def edit_tunables(tunables):
    tunables = tunables.copy()
    keys = list(tunables.keys())

    while True:
        display_tunables(tunables)
        print(f"\n  {len(keys) + 1}. Done")

        choice = input("\nEdit which? ").strip()
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        choice = int(choice)
        if choice == len(keys) + 1:
            break
        if not (1 <= choice <= len(keys)):
            print("Invalid selection.")
            continue

        key     = keys[choice - 1]
        current = tunables[key]
        label   = TUNABLE_LABELS.get(key, key)

        if isinstance(current, bool):
            tunables[key] = not current
            print(f"  {label} → {tunables[key]}")
        else:
            new_val = input(f"  {label} [{current}]: ").strip()
            if new_val:
                tunables[key] = new_val

    return tunables


# Command builder

def build_args(defaults, common, tunables, fixed, model_variant, is_bench):
    args = []

    args += ["-m", resolve(model_variant["model"])]

    if model_variant.get("mtp"):
        args += model_variant.get("mtp_args", [])

    for key, value in tunables.items():
        if key == "mmproj":
            continue
        flag = TUNABLE_FLAGS.get(key)
        if flag is None:
            continue
        if isinstance(value, bool):
            if value:
                args.append(flag)
        else:
            args += [flag, str(value)]

    if not is_bench:
        args += common

    args += resolve_args(fixed)

    if not is_bench and tunables.get("mmproj") and "mmproj" in model_variant:
        args += ["--mmproj", resolve(model_variant["mmproj"])]

    if not is_bench:
        args += ["--host", defaults.get("host", "0.0.0.0")]
        args += ["--port", defaults.get("port", "8080")]

    if not is_bench and "threads" not in tunables:
        args += ["--threads", defaults.get("threads", "14")]

    return args


# Main

def main():
    load_env_file()
    check_env_vars()

    config   = load_config()
    defaults = config.get("defaults", {})
    common   = config.get("common", [])
    runtimes = {k: resolve(v) for k, v in config["runtimes"].items()}
    profiles = config["profiles"]

    last       = load_last_used()
    last_valid = validate_last_used(last, runtimes, profiles)
    last_used_tunables = None

    while True:
        # Runtime selection
        runtime_name = choose_option("Runtime", list(runtimes.keys()), can_go_back=False)

        # Profile list — pin last used as item 1 if valid and matches runtime
        profile_names  = [p["name"] for p in profiles]
        profile_labels = [
            f"{p['name']}  [{', '.join(p.get('tags', []))}]"
            for p in profiles
        ]

        if last_valid and last["runtime"] == runtime_name:
            option_values  = [LAST_USED]  + profile_names
            option_labels  = [f"★ {last['profile']}  [{last['model']}]  ← last used"] + profile_labels
        else:
            option_values  = profile_names
            option_labels  = profile_labels

        selected = choose_option("Profile", option_values, labels=option_labels, can_go_back=True)

        if selected is BACK:
            continue

        # Last used shortcut — skip model variant step
        if selected is LAST_USED:
            runtime_name  = last["runtime"]
            selected_name = last["profile"]
            model_name    = last["model"]
            last_used_tunables = last.get("tunables")
            break

        selected_name = selected
        profile       = next(p for p in profiles if p["name"] == selected_name)
        model_names   = list(profile["models"].keys())

        chosen = choose_option("Model variant", model_names, can_go_back=True)
        if chosen is BACK:
            continue

        model_name = chosen
        break

    runtime_path  = runtimes[runtime_name]
    profile       = next(p for p in profiles if p["name"] == selected_name)
    model_variant = profile["models"][model_name]
    is_bench      = profile["executable"] == "llama-bench.exe"

    # Profile info
    print(f"\n  {profile['name']}")
    print_profile_info(profile, model_name, model_variant)

    # MTP + mmproj warning
    if model_variant.get("mtp"):
        print("\n  ⚠  MTP model selected — mmproj (vision) is currently incompatible with MTP.")
        print("     mmproj will be suppressed automatically.")

    # Tunables
    tunables = merge_tunables(defaults, profile.get("tunables", {}))
    if last_used_tunables:
        for k, v in last_used_tunables.items():
            if k in tunables:
                tunables[k] = v

    if model_variant.get("mtp") and "mmproj" in tunables:
        tunables["mmproj"] = False

    # Validation
    errors = validate(runtime_path, profile, model_variant, tunables)
    if errors:
        print("\n  Validation errors:")
        for e in errors:
            print(f"    ✗ {e}")
        sys.exit(1)

    # Tweak
    if not is_bench:
        tweak = input("\nTweak parameters before launch? (y/N): ").strip().lower()
        if tweak == "y":
            tunables = edit_tunables(tunables)

    # Build and preview
    executable = str(Path(runtime_path) / profile["executable"])
    final_args = build_args(defaults, common, tunables, profile.get("fixed", []), model_variant, is_bench)
    command    = [executable] + final_args

    print_command_preview(command)

    confirm = input("\nLaunch? (Y/n): ").strip().lower()
    if confirm == "n":
        print("Aborted.")
        sys.exit(0)

    save_last_used(runtime_name, selected_name, model_name, tunables)

    print()
    try:
        subprocess.run(command)
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)