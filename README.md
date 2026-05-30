# llama.cpp Launcher

A lightweight Python launcher for llama.cpp built for local LLM workflows and experimentation.

## Features

- multiple runtimes (`stable` / `latest`)
- multiple model variants per profile
- multimodal (`mmproj`) and MTP/speculative decoding support
- runtime-tunable parameters with interactive editor
- validation before launch, command preview, last-used quick launch
- profile tags and notes
- Windows and Linux / WSL2 support

## File structure

```
launcher/
├── config.json          # profiles, models, tunables, runtime paths
├── common.py            # shared logic
├── launcher_windows.py  # Windows entry point
└── launcher_linux.py    # Linux / WSL2 entry point
```

## Setup

### Windows

Add to your environment variables or a `.env` file next to the launcher:

```
LLAMA_MODELS=D:\path\to\models
LLAMA_BIN_STABLE=D:\llama\stable\build\bin\Release
LLAMA_BIN_LATEST=D:\llama\latest\build\bin\Release
```

Add a `llama.bat` to your PATH for quick access:

```bat
@echo off
python D:\llama\launcher\launcher_windows.py %*
```

### Linux / WSL2

Add to `~/.bashrc`:

```bash
export LLAMA_MODELS="D:\\path\\to\\models"   # Windows path, auto-translated to /mnt/...
export LINUX_LLAMA_BIN_STABLE="/path/to/llama-stable/build/bin"
export LINUX_LLAMA_BIN_LATEST="/path/to/llama-latest/build/bin"

llama() { python3 /path/to/launcher_linux.py "$@"; }
```

If models are on a native Linux path, use that directly — no translation needed.

Reload: `source ~/.bashrc`

## Configuration

Profiles are defined in `config.json`. Each profile specifies models, tunables (editable at launch), fixed args, and optional tags/notes.

Runtimes are defined per platform — adding a new runtime requires only a config change:

```json
"runtimes": {
  "Stable": {
    "windows": "$LLAMA_BIN_STABLE",
    "linux":   "$LINUX_LLAMA_BIN_STABLE"
  },
  "Latest": {
    "windows": "$LLAMA_BIN_LATEST",
    "linux":   "$LINUX_LLAMA_BIN_LATEST"
  }
}
```