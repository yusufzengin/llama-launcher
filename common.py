import json
import os
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
    "cache_type_k": "--cache-type-k",
    "cache_type_v": "--cache-type-v",
    "mmproj":    None,  # handled separately
}

TUNABLE_LABELS = {
    "ctx":       "Context size",
    "batch":     "Batch size",
    "ubatch":    "Ubatch size",
    "threads":   "Threads",
    "n_cpu_moe": "CPU MOE layers",
    "cache_type_k": "KV cache type (K)",
    "cache_type_v": "KV cache type (V)",
    "mmproj":    "Vision (mmproj)",
}

TUNABLE_ENUMS = {
    "cache_type_k": ["f16", "bf16", "q8_0", "q5_1", "q5_0", "q4_1", "q4_0", "iq4_nl"],
    "cache_type_v": ["f16", "bf16", "q8_0", "q5_1", "q5_0", "q4_1", "q4_0", "iq4_nl"],
}

BACK      = object()
LAST_USED = object()


# Config / persistence

def load_env_file():
    """Load a .env file next to the launcher into os.environ (non-destructive)."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
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
            "runtime":  runtime_name,
            "profile":  profile_name,
            "model":    model_name,
            "tunables": tunables or {},
        }, f, indent=2)


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
    tags  = profile.get("tags", [])
    notes = profile.get("notes", [])

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

def merge_tunables(defaults, profile_tunables, model_tunables= None):
    merged = {}
    for key in TUNABLE_FLAGS:
        if model_tunables and key in model_tunables:
            merged[key] = model_tunables[key]
        elif key in profile_tunables:
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
        print(f"\n  0. Done")

        choice = input("\nEdit which? ").strip()
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        choice = int(choice)
        if choice == 0:
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
        elif key in TUNABLE_ENUMS:
            options = TUNABLE_ENUMS[key]
            print(f"\n  {label} [{current}]:")
            print(f"    0. Keep current")
            for i, opt in enumerate(options, start=1):
                marker = " ←" if opt == current else ""
                print(f"    {i}. {opt}{marker}")
            choice = input("  Select: ").strip()
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(options):
                    tunables[key] = options[idx - 1] 
        else:
            new_val = input(f"  {label} [{current}]: ").strip()
            if new_val:
                tunables[key] = new_val
    return tunables


# Command builder

def build_args(defaults, common_args, tunables, fixed, model_variant, is_bench, resolve_fn):
    """
    Build the final arg list.
    resolve_fn: callable(str) -> str — platform-specific path resolver.
    Only model/mmproj values are resolved; flag strings pass through as-is.
    """
    args = []

    args.extend(["-m", resolve_fn(model_variant["model"])])

    if model_variant.get("mtp"):
        args.extend(model_variant.get("mtp_args", []))

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
            args.extend([flag, str(value)])

    if not is_bench:
        args.extend(common_args)

    args.extend(fixed)

    if not is_bench and tunables.get("mmproj") and "mmproj" in model_variant:
        args.extend(["--mmproj", resolve_fn(model_variant["mmproj"])])

    if not is_bench:
        args.extend(["--host", defaults.get("host", "0.0.0.0")])
        args.extend(["--port", defaults.get("port", "8080")])

    if not is_bench and "threads" not in tunables:
        args.extend(["--threads", defaults.get("threads", "14")])

    return args


# Main flow (platform-agnostic orchestration)

def run(config, runtimes, resolve_fn, get_executable_fn, validate_fn):
    """
    Shared main loop.

    Callers provide:
      config            - loaded config dict
      runtimes          - dict of {name: resolved_binary_dir_str}
      resolve_fn        - callable(str) -> str   resolves model/mmproj paths
      get_executable_fn - callable(runtime_path, profile) -> str
      validate_fn       - callable(executable, profile, model_variant, tunables) -> [errors]
    """
    defaults    = config.get("defaults", {})
    common_args = config.get("common", [])
    profiles    = config["profiles"]

    last       = load_last_used()
    last_valid = validate_last_used(last, runtimes, profiles)

    while True:
        # Runtime selection
        runtime_name = choose_option("Runtime", list(runtimes.keys()), can_go_back=False)

        # Profile selection
        profile_names  = [p["name"] for p in profiles]
        profile_labels = [
            f"{p['name']}  [{', '.join(p.get('tags', []))}]"
            for p in profiles
        ]

        if last_valid and last["runtime"] == runtime_name:
            option_values = [LAST_USED] + profile_names
            option_labels = [f"★ {last['profile']}  [{last['model']}]  ← last used"] + profile_labels
        else:
            option_values = profile_names
            option_labels = profile_labels

        selected = choose_option("Profile", option_values, labels=option_labels, can_go_back=True)

        if selected is BACK:
            continue

        # Last-used shortcut
        if selected is LAST_USED:
            runtime_name       = last["runtime"]
            selected_name      = last["profile"]
            model_name         = last["model"]
            last_used_tunables = last.get("tunables")
            break

        selected_name = selected
        profile       = next(p for p in profiles if p["name"] == selected_name)
        model_names   = list(profile["models"].keys())

        chosen = choose_option("Model variant", model_names, can_go_back=True)
        if chosen is BACK:
            continue

        model_name         = chosen
        last_used_tunables = None
        break

    runtime_path  = runtimes[runtime_name]
    profile       = next(p for p in profiles if p["name"] == selected_name)
    model_variant = profile["models"][model_name]
    is_bench      = profile["executable"] in ("llama-bench.exe", "llama-bench")

    # Profile info
    print(f"\n  {profile['name']}")
    print_profile_info(profile, model_name, model_variant)

    if model_variant.get("mtp"):
        print("\n  ⚠  MTP model selected — mmproj (vision) is currently incompatible with MTP.")
        print("     mmproj will be suppressed automatically.")

    # Tunables
    tunables = merge_tunables(defaults, profile.get("tunables", {}), model_variant.get("tunables"))
    if last_used_tunables:
        for k, v in last_used_tunables.items():
            if k in tunables:
                tunables[k] = v

    if model_variant.get("mtp") and "mmproj" in tunables:
        tunables["mmproj"] = False

    # Validation
    executable = get_executable_fn(runtime_path, profile)
    errors     = validate_fn(executable, profile, model_variant, tunables)
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
    final_args = build_args(defaults, common_args, tunables, profile.get("fixed", []), model_variant, is_bench, resolve_fn)
    command    = [executable] + final_args

    print("\n--- Launch Summary ---\n")
    print(f"  Runtime : {runtime_name}")
    print(f"  Profile : {profile['name']}")
    print(f"  Model   : {model_name}")

    print_command_preview(command)

    confirm = input("\nLaunch? (Y/n): ").strip().lower()
    if confirm == "n":
        print("Aborted.")
        sys.exit(0)

    save_last_used(runtime_name, selected_name, model_name, tunables)

    return command